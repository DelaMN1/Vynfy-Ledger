from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.extensions import db
from app.reconciliation.forms import ReconciliationForm
from app.models import Account, ReconciliationSession, Transaction, User
from app.utils.audit import record_audit
from app.utils.enums import EXPENSE_SETTLED_STATUSES, REVENUE_SETTLED_STATUSES, ReconciliationStatus, TransactionType
from app.utils.exceptions import ServiceError
from app.utils.time import utcnow
from app.utils.types import ChoiceOptions


def reconciliation_accounts() -> ChoiceOptions:
    return [(item.id, item.name) for item in Account.query.filter_by(is_active=True).order_by(Account.name.asc()).all()]


def _system_balance(account: Account, period_end: date) -> Decimal:
    inflows = sum(
        Decimal(item.received_amount or 0)
        for item in Transaction.query.filter_by(account_id=account.id, transaction_type=TransactionType.REVENUE.value)
        .filter(
            Transaction.transaction_date <= period_end,
            Transaction.deleted_at.is_(None),
            Transaction.status.in_(REVENUE_SETTLED_STATUSES),
        )
        .all()
    )
    outflows = sum(
        Decimal(item.amount or 0)
        for item in Transaction.query.filter_by(account_id=account.id, transaction_type=TransactionType.EXPENSE.value)
        .filter(
            Transaction.transaction_date <= period_end,
            Transaction.deleted_at.is_(None),
            Transaction.status.in_(EXPENSE_SETTLED_STATUSES),
        )
        .all()
    )
    return Decimal(account.opening_balance or 0) + inflows - outflows


def create_session_from_form(*, form: ReconciliationForm, actor: User) -> ReconciliationSession:
    if form.period_end.data < form.period_start.data:
        raise ServiceError("The period end cannot be earlier than the period start.")
    account = db.session.get(Account, form.account_id.data)
    if not account:
        raise ServiceError("Account not found.")
    system_balance = _system_balance(account, form.period_end.data)
    normalized_notes = (form.notes.data or "").strip() or None
    existing = (
        ReconciliationSession.query.filter_by(
            account_id=account.id,
            period_start=form.period_start.data,
            period_end=form.period_end.data,
            statement_ending_balance=form.statement_ending_balance.data,
            system_balance=system_balance,
            difference=Decimal(form.statement_ending_balance.data) - system_balance,
            notes=normalized_notes,
            status=ReconciliationStatus.DRAFT.value,
        )
        .order_by(ReconciliationSession.id.desc())
        .first()
    )
    if existing:
        return existing

    session = ReconciliationSession(
        account_id=account.id,
        period_start=form.period_start.data,
        period_end=form.period_end.data,
        statement_ending_balance=form.statement_ending_balance.data,
        system_balance=system_balance,
        difference=Decimal(form.statement_ending_balance.data) - system_balance,
        notes=normalized_notes,
    )
    db.session.add(session)
    db.session.flush()
    record_audit(user_id=actor.id, entity_type="reconciliation", entity_id=session.id, action="start")
    return session


def get_session_or_404(session_id: int, *, actor: User) -> ReconciliationSession:
    if not actor.is_admin:
        raise ServiceError("Only admins can access reconciliation sessions.")
    session = db.session.get(ReconciliationSession, session_id)
    if not session:
        raise ServiceError("Reconciliation session not found.")
    return session


def reconciliation_transactions(session: ReconciliationSession) -> list[Transaction]:
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
    normalized_ids = sorted(set(selected_transaction_ids))
    allowed_ids = {item.id for item in reconciliation_transactions(session)}
    if any(item_id not in allowed_ids for item_id in normalized_ids):
        raise ServiceError("Selected transactions must belong to the reconciliation account and period.")
    if session.status == ReconciliationStatus.FINALIZED.value:
        if session.completed_by_id == actor.id and (session.selected_transaction_ids or []) == normalized_ids:
            return
        raise ServiceError("This reconciliation session has already been finalized.")
    session.status = ReconciliationStatus.FINALIZED.value
    session.completed_by_id = actor.id
    session.selected_transaction_ids = normalized_ids
    for transaction in Transaction.query.filter(Transaction.id.in_(normalized_ids)).all():
        transaction.is_reconciled = True
        transaction.reconciled_at = utcnow()
    record_audit(user_id=actor.id, entity_type="reconciliation", entity_id=session.id, action="finalize")
