from __future__ import annotations

from decimal import Decimal

from app.extensions import db
from app.models import Account, ReconciliationSession, Transaction, User
from app.utils.audit import record_audit
from app.utils.enums import ExpenseStatus, ReconciliationStatus, RevenueStatus, TransactionType
from app.utils.exceptions import ServiceError
from app.utils.time import utcnow


def reconciliation_accounts() -> list[tuple[int, str]]:
    return [(item.id, item.name) for item in Account.query.filter_by(is_active=True).order_by(Account.name.asc()).all()]


def _system_balance(account: Account, period_end) -> Decimal:
    inflows = sum(
        Decimal(item.received_amount or 0)
        for item in Transaction.query.filter_by(account_id=account.id, transaction_type=TransactionType.REVENUE.value)
        .filter(
            Transaction.transaction_date <= period_end,
            Transaction.deleted_at.is_(None),
            Transaction.status.in_([RevenueStatus.PARTIALLY_RECEIVED.value, RevenueStatus.RECEIVED.value]),
        )
        .all()
    )
    outflows = sum(
        Decimal(item.amount or 0)
        for item in Transaction.query.filter_by(account_id=account.id, transaction_type=TransactionType.EXPENSE.value)
        .filter(
            Transaction.transaction_date <= period_end,
            Transaction.deleted_at.is_(None),
            Transaction.status.in_([ExpenseStatus.PAID.value, ExpenseStatus.REIMBURSED.value]),
        )
        .all()
    )
    return Decimal(account.opening_balance or 0) + inflows - outflows


def create_session_from_form(*, form, actor: User) -> ReconciliationSession:
    if form.period_end.data < form.period_start.data:
        raise ServiceError("The period end cannot be earlier than the period start.")
    account = db.session.get(Account, form.account_id.data)
    if not account:
        raise ServiceError("Account not found.")
    system_balance = _system_balance(account, form.period_end.data)
    session = ReconciliationSession(
        account_id=account.id,
        period_start=form.period_start.data,
        period_end=form.period_end.data,
        statement_ending_balance=form.statement_ending_balance.data,
        system_balance=system_balance,
        difference=Decimal(form.statement_ending_balance.data) - system_balance,
        notes=form.notes.data,
    )
    db.session.add(session)
    db.session.flush()
    record_audit(user_id=actor.id, entity_type="reconciliation", entity_id=session.id, action="start")
    return session


def get_session_or_404(session_id: int) -> ReconciliationSession:
    session = db.session.get(ReconciliationSession, session_id)
    if not session:
        raise ServiceError("Reconciliation session not found.")
    return session


def reconciliation_transactions(session: ReconciliationSession):
    return (
        Transaction.query.filter(
            Transaction.account_id == session.account_id,
            Transaction.transaction_date >= session.period_start,
            Transaction.transaction_date <= session.period_end,
            Transaction.deleted_at.is_(None),
        )
        .order_by(Transaction.transaction_date.asc())
        .all()
    )


def finalize_session(*, session: ReconciliationSession, actor: User, selected_transaction_ids: list[int]) -> None:
    if not actor.is_admin:
        raise ServiceError("Only admins can finalize reconciliation.")
    session.status = ReconciliationStatus.FINALIZED.value
    session.completed_by_id = actor.id
    session.selected_transaction_ids = selected_transaction_ids
    for transaction in Transaction.query.filter(Transaction.id.in_(selected_transaction_ids)).all():
        transaction.is_reconciled = True
        transaction.reconciled_at = utcnow()
    record_audit(user_id=actor.id, entity_type="reconciliation", entity_id=session.id, action="finalize")
