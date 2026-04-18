from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal
from pathlib import Path

from flask import abort, current_app, request
from flask_sqlalchemy.pagination import Pagination
from sqlalchemy import func, or_
from sqlalchemy.orm import Query

from app.extensions import db
from app.models import Account, Attachment, Category, PaymentMethod, Transaction, User
from app.transactions.validators import derive_revenue_status, validate_status_transition
from app.utils.audit import record_audit
from app.utils.enums import (
    EXPENSE_EDITABLE_STATUSES,
    EXPENSE_SETTLED_STATUSES,
    REVENUE_EDITABLE_STATUSES,
    REVENUE_SETTLED_STATUSES,
    TRANSACTION_STATUS_VALUES,
    ExpenseStatus,
    RevenueStatus,
    TransactionType,
)
from app.utils.exceptions import ServiceError
from app.utils.files import store_upload, validate_upload
from app.utils.pagination import current_page, page_size
from app.utils.time import utcnow
from app.utils.types import ChoiceOptions, TransactionChoiceForm, TransactionFilterChoiceForm, TransactionFilters, TransactionFormLike, TransactionSnapshot


def _choices_from_items(items, *, placeholder: tuple[int, str] | None = None) -> ChoiceOptions:
    choices = [(item.id, item.name) for item in items]
    return ([placeholder] if placeholder else []) + choices


def _active_categories(transaction_type: str) -> ChoiceOptions:
    items = Category.query.filter_by(type=transaction_type, is_active=True).order_by(Category.name.asc()).all()
    return _choices_from_items(items)


def _active_accounts() -> ChoiceOptions:
    items = Account.query.filter_by(is_active=True).order_by(Account.name.asc()).all()
    return _choices_from_items(items)


def _active_payment_methods() -> ChoiceOptions:
    items = PaymentMethod.query.filter_by(is_active=True).order_by(PaymentMethod.name.asc()).all()
    return _choices_from_items(items, placeholder=(0, "Select payment method"))


def assign_form_choices(form: TransactionChoiceForm, transaction_type: str) -> None:
    form.category_id.choices = _active_categories(transaction_type)
    form.account_id.choices = _active_accounts()
    form.payment_method_id.choices = _active_payment_methods()


def assign_filter_choices(form: TransactionFilterChoiceForm, *, user: User, transaction_type: str | None = None) -> None:
    categories = [(0, "All categories")]
    if transaction_type:
        categories += _active_categories(transaction_type)
    else:
        categories += _active_categories(TransactionType.REVENUE.value) + _active_categories(TransactionType.EXPENSE.value)
    form.category_id.choices = categories
    form.account_id.choices = [(0, "All accounts")] + _active_accounts()
    form.owner_id.choices = (
        [(0, "All owners")] + [(item.id, item.full_name) for item in User.query.order_by(User.full_name.asc()).all()]
        if user.is_admin
        else [(0, "My records")]
    )
    status_values = set(TRANSACTION_STATUS_VALUES[TransactionType.REVENUE.value]) | set(TRANSACTION_STATUS_VALUES[TransactionType.EXPENSE.value])
    if transaction_type in TRANSACTION_STATUS_VALUES:
        status_values = set(TRANSACTION_STATUS_VALUES[transaction_type])
    form.status.choices = [("", "All statuses")] + [(value, value) for value in sorted(status_values)]


def visible_transactions_query(user: User, transaction_type: str | None = None) -> Query[Transaction]:
    query = Transaction.query.filter(Transaction.deleted_at.is_(None))
    if transaction_type:
        query = query.filter(Transaction.transaction_type == transaction_type)
    if not user.is_admin:
        query = query.filter(Transaction.submitted_by_id == user.id)
    return query


def apply_filters(query: Query[Transaction], filters: TransactionFilters) -> Query[Transaction]:
    if filters.q:
        like = f"%{filters.q.strip()}%"
        query = query.filter(
            or_(
                Transaction.title.ilike(like),
                Transaction.counterparty.ilike(like),
                Transaction.reference_number.ilike(like),
            )
        )
    if filters.status:
        query = query.filter(Transaction.status == filters.status)
    if filters.category_id:
        query = query.filter(Transaction.category_id == filters.category_id)
    if filters.account_id:
        query = query.filter(Transaction.account_id == filters.account_id)
    if filters.owner_id:
        query = query.filter(Transaction.submitted_by_id == filters.owner_id)
    if filters.start_date:
        query = query.filter(Transaction.transaction_date >= filters.start_date)
    if filters.end_date:
        query = query.filter(Transaction.transaction_date <= filters.end_date)
    return query


def list_transactions(*, user: User, transaction_type: str | None = None, filters: TransactionFilters | None = None) -> Pagination:
    query = visible_transactions_query(user, transaction_type).order_by(Transaction.transaction_date.desc(), Transaction.created_at.desc())
    query = apply_filters(query, filters or TransactionFilters())
    return query.paginate(page=current_page(), per_page=page_size(), error_out=False)


def get_transaction_or_404(transaction_id: int, *, user: User, transaction_type: str | None = None) -> Transaction:
    item = db.session.get(Transaction, transaction_id)
    if not item or item.deleted_at is not None:
        abort(404)
    if transaction_type and item.transaction_type != transaction_type:
        abort(404)
    if not user.is_admin and item.submitted_by_id != user.id:
        abort(403)
    return item


def _serialize(item: Transaction) -> TransactionSnapshot:
    return {
        "title": item.title,
        "status": item.status,
        "amount": float(item.amount or 0),
        "expected_amount": float(item.expected_amount or 0),
        "received_amount": float(item.received_amount or 0),
        "account_id": item.account_id,
        "category_id": item.category_id,
    }


def _validate_dates(transaction_date, due_date, settled_date) -> None:
    if due_date and due_date < transaction_date:
        raise ServiceError("Due date cannot be earlier than the transaction date.")
    if settled_date and settled_date < transaction_date:
        raise ServiceError("Settlement date cannot be earlier than the transaction date.")


def _sync_account_balance(account_id: int) -> None:
    account = db.session.get(Account, account_id)
    if not account:
        return
    revenue_total = (
        db.session.query(func.coalesce(func.sum(Transaction.received_amount), 0))
        .filter(
            Transaction.account_id == account_id,
            Transaction.transaction_type == TransactionType.REVENUE.value,
            Transaction.status.in_(REVENUE_SETTLED_STATUSES),
            Transaction.deleted_at.is_(None),
        )
        .scalar()
    )
    expense_total = (
        db.session.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(
            Transaction.account_id == account_id,
            Transaction.transaction_type == TransactionType.EXPENSE.value,
            Transaction.status.in_(EXPENSE_SETTLED_STATUSES),
            Transaction.deleted_at.is_(None),
        )
        .scalar()
    )
    account.current_balance_cached = Decimal(account.opening_balance or 0) + Decimal(revenue_total or 0) - Decimal(expense_total or 0)


def _save_attachments(transaction: Transaction, actor: User) -> None:
    saved = 0
    upload_dir = Path(current_app.config["UPLOAD_FOLDER"])
    for file in request.files.getlist("attachments"):
        if not file or not file.filename:
            continue
        errors = validate_upload(file)
        if errors:
            raise ServiceError(" ".join(errors))
        original_filename, stored_name = store_upload(file)
        stored_path = upload_dir / stored_name
        db.session.add(
            Attachment(
                transaction=transaction,
                original_filename=original_filename,
                stored_filename=stored_name,
                file_path=f"instance/uploads/{stored_name}",
                mime_type=file.mimetype or "application/octet-stream",
                file_size=stored_path.stat().st_size,
                uploaded_by_id=actor.id,
            )
        )
        saved += 1
    if saved:
        transaction.attachment_count = (transaction.attachment_count or 0) + saved


def _can_edit(item: Transaction, actor: User) -> bool:
    if actor.is_admin:
        return True
    if item.submitted_by_id != actor.id:
        return False
    if item.transaction_type == TransactionType.EXPENSE.value:
        return item.status in EXPENSE_EDITABLE_STATUSES
    return item.status in REVENUE_EDITABLE_STATUSES


def create_transaction_from_form(*, form: TransactionFormLike, transaction_type: str, actor: User) -> Transaction:
    _validate_dates(form.transaction_date.data, form.due_date.data, form.settled_date.data)
    item = Transaction(
        transaction_type=transaction_type,
        title=form.title.data,
        description=form.description.data,
        counterparty=form.counterparty.data,
        category_id=form.category_id.data,
        account_id=form.account_id.data,
        payment_method_id=form.payment_method_id.data or None,
        transaction_date=form.transaction_date.data,
        due_date=form.due_date.data,
        settled_date=form.settled_date.data,
        reference_number=form.reference_number.data,
        note=form.note.data,
        submitted_by_id=actor.id,
    )
    if transaction_type == TransactionType.REVENUE.value:
        expected = Decimal(form.expected_amount.data)
        received = Decimal(form.received_amount.data or 0)
        if received > expected and not actor.is_admin:
            raise ServiceError("Received amount cannot exceed expected amount without admin override.")
        item.amount = expected
        item.expected_amount = expected
        item.received_amount = received or None
        item.status = RevenueStatus.DRAFT.value if form.save_draft.data else derive_revenue_status(expected, received, form.due_date.data, date.today())
    else:
        item.amount = Decimal(form.amount.data)
        item.reimbursable = form.reimbursable.data
        item.status = ExpenseStatus.DRAFT.value if form.save_draft.data else ExpenseStatus.SUBMITTED.value
    db.session.add(item)
    db.session.flush()
    _save_attachments(item, actor)
    _sync_account_balance(item.account_id)
    record_audit(user_id=actor.id, entity_type="transaction", entity_id=item.id, action="create", new_values=_serialize(item))
    return item


def update_transaction_from_form(*, transaction: Transaction, form: TransactionFormLike, actor: User) -> Transaction:
    if not _can_edit(transaction, actor):
        raise ServiceError("You cannot edit this record in its current state.")
    _validate_dates(form.transaction_date.data, form.due_date.data, form.settled_date.data)
    previous = _serialize(transaction)
    transaction.title = form.title.data
    transaction.description = form.description.data
    transaction.counterparty = form.counterparty.data
    transaction.category_id = form.category_id.data
    transaction.account_id = form.account_id.data
    transaction.payment_method_id = form.payment_method_id.data or None
    transaction.transaction_date = form.transaction_date.data
    transaction.due_date = form.due_date.data
    transaction.settled_date = form.settled_date.data
    transaction.reference_number = form.reference_number.data
    transaction.note = form.note.data
    if transaction.transaction_type == TransactionType.REVENUE.value:
        expected = Decimal(form.expected_amount.data)
        received = Decimal(form.received_amount.data or 0)
        if received > expected and not actor.is_admin:
            raise ServiceError("Received amount cannot exceed expected amount without admin override.")
        transaction.amount = expected
        transaction.expected_amount = expected
        transaction.received_amount = received or None
        transaction.status = RevenueStatus.DRAFT.value if form.save_draft.data else derive_revenue_status(expected, received, form.due_date.data, date.today())
    else:
        transaction.amount = Decimal(form.amount.data)
        transaction.reimbursable = form.reimbursable.data
        if actor.is_admin:
            transaction.status = form.status.data
        elif form.save_draft.data:
            transaction.status = ExpenseStatus.DRAFT.value
    _save_attachments(transaction, actor)
    _sync_account_balance(transaction.account_id)
    record_audit(user_id=actor.id, entity_type="transaction", entity_id=transaction.id, action="update", old_values=previous, new_values=_serialize(transaction))
    return transaction


def submit_expense(transaction: Transaction, actor: User) -> None:
    if transaction.transaction_type != TransactionType.EXPENSE.value:
        raise ServiceError("Only expenses can be submitted.")
    if transaction.submitted_by_id != actor.id and not actor.is_admin:
        raise ServiceError("You can only submit your own expense draft.")
    if transaction.status == ExpenseStatus.SUBMITTED.value:
        return
    validate_status_transition(transaction.transaction_type, transaction.status, ExpenseStatus.SUBMITTED.value, override=actor.is_admin)
    previous = _serialize(transaction)
    transaction.status = ExpenseStatus.SUBMITTED.value
    record_audit(user_id=actor.id, entity_type="transaction", entity_id=transaction.id, action="submit", old_values=previous, new_values=_serialize(transaction))


def approve_expense(transaction: Transaction, actor: User) -> None:
    if transaction.status == ExpenseStatus.APPROVED.value:
        if transaction.approved_by_id == actor.id:
            return
        raise ServiceError("Expense is already approved.")
    validate_status_transition(transaction.transaction_type, transaction.status, ExpenseStatus.APPROVED.value)
    previous = _serialize(transaction)
    transaction.status = ExpenseStatus.APPROVED.value
    transaction.approved_by_id = actor.id
    record_audit(user_id=actor.id, entity_type="transaction", entity_id=transaction.id, action="approve", old_values=previous, new_values=_serialize(transaction))


def reject_expense(transaction: Transaction, actor: User, note: str) -> None:
    normalized_note = note.strip()
    if not normalized_note:
        raise ServiceError("Rejection requires a reason.")
    if transaction.status == ExpenseStatus.REJECTED.value:
        if transaction.approved_by_id == actor.id and (transaction.note or "") == normalized_note:
            return
        raise ServiceError("Expense is already rejected.")
    validate_status_transition(transaction.transaction_type, transaction.status, ExpenseStatus.REJECTED.value)
    previous = _serialize(transaction)
    transaction.status = ExpenseStatus.REJECTED.value
    transaction.approved_by_id = actor.id
    transaction.note = normalized_note
    record_audit(user_id=actor.id, entity_type="transaction", entity_id=transaction.id, action="reject", old_values=previous, new_values=_serialize(transaction))


def return_expense_for_edit(transaction: Transaction, actor: User, note: str) -> None:
    normalized_note = note.strip()
    if not normalized_note:
        raise ServiceError("Returning an expense requires a note.")
    if transaction.status == ExpenseStatus.RETURNED.value:
        if transaction.approved_by_id == actor.id and (transaction.note or "") == normalized_note:
            return
        raise ServiceError("Expense has already been returned for edit.")
    validate_status_transition(transaction.transaction_type, transaction.status, ExpenseStatus.RETURNED.value)
    previous = _serialize(transaction)
    transaction.status = ExpenseStatus.RETURNED.value
    transaction.approved_by_id = actor.id
    transaction.note = normalized_note
    record_audit(user_id=actor.id, entity_type="transaction", entity_id=transaction.id, action="return", old_values=previous, new_values=_serialize(transaction))


def mark_expense_paid(transaction: Transaction, actor: User, settled_date: date | None) -> None:
    resolved_settled_date = settled_date or date.today()
    if transaction.status == ExpenseStatus.PAID.value:
        if transaction.approved_by_id == actor.id and transaction.settled_date == resolved_settled_date:
            return
        raise ServiceError("Expense is already marked paid.")
    validate_status_transition(transaction.transaction_type, transaction.status, ExpenseStatus.PAID.value)
    previous = _serialize(transaction)
    transaction.status = ExpenseStatus.PAID.value
    transaction.settled_date = resolved_settled_date
    transaction.approved_by_id = actor.id
    _sync_account_balance(transaction.account_id)
    record_audit(user_id=actor.id, entity_type="transaction", entity_id=transaction.id, action="mark_paid", old_values=previous, new_values=_serialize(transaction))


def mark_revenue_received(transaction: Transaction, actor: User, amount: Decimal | None, settled_date: date | None) -> None:
    expected = Decimal(transaction.expected_amount or transaction.amount or 0)
    received = Decimal(amount or expected)
    if received > expected and not actor.is_admin:
        raise ServiceError("Received amount cannot exceed expected amount without admin override.")
    previous = _serialize(transaction)
    transaction.received_amount = received
    transaction.settled_date = settled_date or date.today()
    transaction.status = derive_revenue_status(expected, received, transaction.due_date, date.today())
    _sync_account_balance(transaction.account_id)
    record_audit(user_id=actor.id, entity_type="transaction", entity_id=transaction.id, action="mark_received", old_values=previous, new_values=_serialize(transaction))


def soft_delete_draft(transaction: Transaction, actor: User) -> None:
    if transaction.submitted_by_id != actor.id and not actor.is_admin:
        raise ServiceError("You can only delete your own draft.")
    if transaction.transaction_type == TransactionType.EXPENSE.value and transaction.status != ExpenseStatus.DRAFT.value:
        raise ServiceError("Only draft expenses can be deleted.")
    if transaction.transaction_type == TransactionType.REVENUE.value and transaction.status != RevenueStatus.DRAFT.value:
        raise ServiceError("Only draft revenue can be deleted.")
    previous = _serialize(transaction)
    transaction.deleted_at = utcnow()
    record_audit(user_id=actor.id, entity_type="transaction", entity_id=transaction.id, action="delete", old_values=previous)


def recent_transactions(user: User, limit: int = 8) -> list[Transaction]:
    return visible_transactions_query(user).order_by(Transaction.transaction_date.desc(), Transaction.created_at.desc()).limit(limit).all()


def pending_approvals() -> list[Transaction]:
    return (
        Transaction.query.filter(
            Transaction.transaction_type == TransactionType.EXPENSE.value,
            Transaction.status == ExpenseStatus.SUBMITTED.value,
            Transaction.deleted_at.is_(None),
        )
        .order_by(Transaction.created_at.asc())
        .all()
    )


def export_transactions_csv(*, user: User, transaction_type: str | None = None, filters: TransactionFilters | None = None) -> str:
    items = apply_filters(visible_transactions_query(user, transaction_type), filters or TransactionFilters()).order_by(Transaction.transaction_date.desc()).all()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["ID", "Type", "Title", "Counterparty", "Status", "Amount", "Expected Amount", "Received Amount", "Transaction Date", "Due Date", "Settled Date"])
    for item in items:
        writer.writerow([item.id, item.transaction_type, item.title, item.counterparty or "", item.status, item.amount, item.expected_amount or "", item.received_amount or "", item.transaction_date, item.due_date or "", item.settled_date or ""])
    return buffer.getvalue()
