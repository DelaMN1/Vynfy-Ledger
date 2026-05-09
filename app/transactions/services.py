from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal
from pathlib import Path

from flask import abort, current_app, request
from flask_sqlalchemy.pagination import Pagination
from sqlalchemy import func, or_
from sqlalchemy.orm import Query, joinedload

from app.extensions import db
from app.models import (
    Account,
    AccountingMapping,
    Attachment,
    Budget,
    Category,
    PaymentMethod,
    SpendPolicy,
    Transaction,
    TransactionComment,
    TransactionStatusHistory,
    User,
)
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


BUDGET_EXCLUDED_STATUSES = frozenset(
    {
        ExpenseStatus.DRAFT.value,
        ExpenseStatus.REJECTED.value,
        ExpenseStatus.RETURNED.value,
        RevenueStatus.DRAFT.value,
        RevenueStatus.CANCELLED.value,
    }
)


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


def _resolve_default_category_id(transaction_type: str) -> int:
    item = Category.query.filter_by(type=transaction_type, is_active=True).order_by(Category.name.asc(), Category.id.asc()).first()
    if not item:
        label = "revenue" if transaction_type == TransactionType.REVENUE.value else "expense"
        raise ServiceError(f"No active {label} category is configured.")
    return int(item.id)


def _resolve_default_account_id() -> int:
    item = Account.query.filter_by(is_active=True).order_by(Account.name.asc(), Account.id.asc()).first()
    if not item:
        raise ServiceError("No active account is configured.")
    return int(item.id)


def assign_form_choices(form: TransactionChoiceForm, transaction_type: str) -> None:
    form.category_id.choices = _active_categories(transaction_type)
    form.account_id.choices = _active_accounts()
    form.payment_method_id.choices = _active_payment_methods()


def assign_simple_entry_choices(form) -> None:
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


def _transaction_display_options():
    return (
        joinedload(Transaction.category),
        joinedload(Transaction.account),
        joinedload(Transaction.payment_method),
        joinedload(Transaction.submitted_by),
    )


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
    query = (
        visible_transactions_query(user, transaction_type)
        .options(*_transaction_display_options())
        .order_by(Transaction.transaction_date.desc(), Transaction.created_at.desc())
    )
    query = apply_filters(query, filters or TransactionFilters())
    return query.paginate(page=current_page(), per_page=page_size(), error_out=False)


def get_transaction_or_404(transaction_id: int, *, user: User, transaction_type: str | None = None) -> Transaction:
    item = Transaction.query.options(*_transaction_display_options()).filter(Transaction.id == transaction_id).first()
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


def _normalize_optional_text(value: str | None) -> str | None:
    return (value or "").strip() or None


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


def _transaction_amount(item: Transaction) -> Decimal:
    if item.transaction_type == TransactionType.REVENUE.value:
        return Decimal(item.expected_amount or item.amount or 0)
    return Decimal(item.amount or 0)


def _matching_score(*, transaction_type: str | None, category_id: int | None, account_id: int | None, payment_method_id: int | None = None, owner_id: int | None = None) -> int:
    return sum(value is not None for value in (transaction_type, category_id, account_id, payment_method_id, owner_id))


def _resolve_spend_policy(transaction: Transaction) -> SpendPolicy | None:
    best_policy = None
    best_score = -1
    for policy in SpendPolicy.query.filter_by(is_active=True).all():
        if policy.transaction_type and policy.transaction_type != transaction.transaction_type:
            continue
        if policy.category_id and policy.category_id != transaction.category_id:
            continue
        if policy.account_id and policy.account_id != transaction.account_id:
            continue
        if policy.payment_method_id and policy.payment_method_id != transaction.payment_method_id:
            continue
        score = _matching_score(
            transaction_type=policy.transaction_type,
            category_id=policy.category_id,
            account_id=policy.account_id,
            payment_method_id=policy.payment_method_id,
        )
        if score > best_score:
            best_policy = policy
            best_score = score
    return best_policy


def _resolve_budget(transaction: Transaction) -> Budget | None:
    best_budget = None
    best_score = -1
    for budget in Budget.query.filter_by(is_active=True).all():
        if budget.transaction_type and budget.transaction_type != transaction.transaction_type:
            continue
        if budget.category_id and budget.category_id != transaction.category_id:
            continue
        if budget.account_id and budget.account_id != transaction.account_id:
            continue
        if budget.owner_id and budget.owner_id != transaction.submitted_by_id:
            continue
        score = _matching_score(
            transaction_type=budget.transaction_type,
            category_id=budget.category_id,
            account_id=budget.account_id,
            owner_id=budget.owner_id,
        )
        if score > best_score:
            best_budget = budget
            best_score = score
    return best_budget


def _resolve_accounting_mapping(transaction: Transaction) -> AccountingMapping | None:
    best_mapping = None
    best_score = -1
    for mapping in AccountingMapping.query.filter_by(is_active=True).all():
        if mapping.transaction_type and mapping.transaction_type != transaction.transaction_type:
            continue
        if mapping.category_id and mapping.category_id != transaction.category_id:
            continue
        if mapping.account_id and mapping.account_id != transaction.account_id:
            continue
        if mapping.payment_method_id and mapping.payment_method_id != transaction.payment_method_id:
            continue
        score = _matching_score(
            transaction_type=mapping.transaction_type,
            category_id=mapping.category_id,
            account_id=mapping.account_id,
            payment_method_id=mapping.payment_method_id,
        )
        if score > best_score:
            best_mapping = mapping
            best_score = score
    return best_mapping


def _month_bounds(period_date: date) -> tuple[date, date]:
    start = period_date.replace(day=1)
    if period_date.month == 12:
        end = date(period_date.year + 1, 1, 1)
    else:
        end = date(period_date.year, period_date.month + 1, 1)
    return start, end


def budget_snapshot_for_budget(
    budget: Budget,
    *,
    period_date: date,
    exclude_transaction_id: int | None = None,
    proposed_amount: Decimal = Decimal("0"),
) -> dict[str, object]:
    period_start, next_month_start = _month_bounds(period_date)
    query = Transaction.query.filter(
        Transaction.deleted_at.is_(None),
        Transaction.transaction_date >= period_start,
        Transaction.transaction_date < next_month_start,
        ~Transaction.status.in_(BUDGET_EXCLUDED_STATUSES),
    )
    if budget.transaction_type:
        query = query.filter(Transaction.transaction_type == budget.transaction_type)
    if budget.category_id:
        query = query.filter(Transaction.category_id == budget.category_id)
    if budget.account_id:
        query = query.filter(Transaction.account_id == budget.account_id)
    if budget.owner_id:
        query = query.filter(Transaction.submitted_by_id == budget.owner_id)
    if exclude_transaction_id:
        query = query.filter(Transaction.id != exclude_transaction_id)

    actual = sum((_transaction_amount(item) for item in query.all()), Decimal("0"))
    projected_total = actual + Decimal(proposed_amount or 0)
    budget_amount = Decimal(budget.amount or 0)
    utilization_percent = int((projected_total / budget_amount) * 100) if budget_amount else 0
    return {
        "budget": budget,
        "period_start": period_start,
        "period_end": next_month_start,
        "budget_amount": budget_amount,
        "actual": actual,
        "projected_total": projected_total,
        "remaining": budget_amount - projected_total,
        "utilization_percent": utilization_percent,
        "alert_triggered": bool(budget_amount and utilization_percent >= int(budget.alert_percent or 0)),
        "over_budget": bool(budget_amount and projected_total > budget_amount),
    }


def budget_snapshot_for_transaction(transaction: Transaction, *, exclude_current: bool = False) -> dict[str, object] | None:
    budget = transaction.budget or _resolve_budget(transaction)
    if not budget:
        return None
    proposed_amount = _transaction_amount(transaction)
    exclude_transaction_id = transaction.id if exclude_current else None
    if not exclude_current:
        proposed_amount = Decimal("0")
    return budget_snapshot_for_budget(
        budget,
        period_date=transaction.transaction_date,
        exclude_transaction_id=exclude_transaction_id,
        proposed_amount=proposed_amount,
    )


def transaction_exception_messages(transaction: Transaction) -> list[str]:
    messages: list[str] = []
    policy = transaction.spend_policy or _resolve_spend_policy(transaction)
    if policy and policy.require_attachment and not transaction.attachment_count:
        messages.append("Missing required attachment.")
    if policy and policy.require_note and not _normalize_optional_text(transaction.note):
        messages.append("Missing required internal note.")
    if policy and policy.max_amount and _transaction_amount(transaction) > Decimal(policy.max_amount):
        messages.append(f"Exceeds policy cap of {Decimal(policy.max_amount):,.2f}.")
    budget_snapshot = budget_snapshot_for_transaction(transaction)
    if budget_snapshot and budget_snapshot["over_budget"]:
        messages.append("Projected spend is over the matched budget.")
    duplicate_count = sum(1 for attachment in transaction.attachments if attachment.duplicate_of_attachment_id)
    if duplicate_count:
        suffix = "es" if duplicate_count != 1 else ""
        messages.append(f"{duplicate_count} duplicate receipt match{suffix} detected.")
    return messages


def _record_history(
    transaction: Transaction,
    *,
    actor: User,
    action: str,
    from_status: str | None = None,
    to_status: str | None = None,
    note: str | None = None,
    metadata: dict[str, object] | None = None,
) -> None:
    db.session.add(
        TransactionStatusHistory(
            transaction=transaction,
            changed_by_id=actor.id,
            action=action,
            from_status=from_status,
            to_status=to_status,
            note=note,
            metadata_json=metadata or None,
        )
    )


def _save_attachments(transaction: Transaction, actor: User) -> None:
    saved = 0
    upload_dir = Path(current_app.config["UPLOAD_FOLDER"])
    for file in request.files.getlist("attachments"):
        if not file or not file.filename:
            continue
        errors = validate_upload(file)
        if errors:
            raise ServiceError(" ".join(errors))
        original_filename, stored_name, sha256_hash = store_upload(file)
        stored_path = upload_dir / stored_name
        duplicate = (
            Attachment.query.filter(Attachment.sha256_hash == sha256_hash, Attachment.transaction_id != transaction.id)
            .order_by(Attachment.id.asc())
            .first()
        )
        attachment = Attachment(
            transaction=transaction,
            original_filename=original_filename,
            stored_filename=stored_name,
            file_path=f"instance/uploads/{stored_name}",
            mime_type=file.mimetype or "application/octet-stream",
            file_size=stored_path.stat().st_size,
            sha256_hash=sha256_hash,
            duplicate_of_attachment_id=duplicate.id if duplicate else None,
            uploaded_by_id=actor.id,
        )
        db.session.add(attachment)
        db.session.flush()
        saved += 1
    if saved:
        transaction.attachment_count = (transaction.attachment_count or 0) + saved


def _apply_transaction_controls(transaction: Transaction, *, strict: bool) -> dict[str, object] | None:
    transaction.spend_policy = _resolve_spend_policy(transaction)
    transaction.budget = _resolve_budget(transaction)
    transaction.accounting_mapping = _resolve_accounting_mapping(transaction)

    if transaction.accounting_mapping:
        transaction.accounting_gl_code = transaction.accounting_mapping.gl_code
        transaction.accounting_cost_center = transaction.accounting_mapping.cost_center
        transaction.accounting_project_code = transaction.accounting_mapping.project_code
    else:
        transaction.accounting_gl_code = None
        transaction.accounting_cost_center = None
        transaction.accounting_project_code = None

    budget_snapshot = None
    if transaction.budget:
        budget_snapshot = budget_snapshot_for_budget(
            transaction.budget,
            period_date=transaction.transaction_date,
            exclude_transaction_id=transaction.id,
            proposed_amount=_transaction_amount(transaction),
        )

    if not strict:
        return budget_snapshot

    policy = transaction.spend_policy
    if policy and policy.require_attachment and not transaction.attachment_count:
        raise ServiceError("This transaction requires at least one attachment before submission.")
    if policy and policy.require_note and not _normalize_optional_text(transaction.note):
        raise ServiceError("This transaction requires an internal note before submission.")
    if policy and policy.max_amount and _transaction_amount(transaction) > Decimal(policy.max_amount):
        raise ServiceError(f"This transaction exceeds the policy limit of {Decimal(policy.max_amount):,.2f}.")
    if policy and policy.block_on_over_budget and budget_snapshot and budget_snapshot["over_budget"]:
        raise ServiceError(f"This transaction would exceed the matched budget '{transaction.budget.name}'.")
    return budget_snapshot


def _can_edit(item: Transaction, actor: User) -> bool:
    if actor.is_admin:
        return True
    if item.submitted_by_id != actor.id:
        return False
    if item.transaction_type == TransactionType.EXPENSE.value:
        return item.status in EXPENSE_EDITABLE_STATUSES
    return item.status in REVENUE_EDITABLE_STATUSES


def can_edit_transaction(item: Transaction, actor: User) -> bool:
    return _can_edit(item, actor)


def expense_action_state(transaction: Transaction, actor: User) -> dict[str, bool]:
    is_expense = transaction.transaction_type == TransactionType.EXPENSE.value
    is_owner_or_admin = transaction.submitted_by_id == actor.id or actor.is_admin
    return {
        "show_submit": bool(is_expense and is_owner_or_admin and transaction.status == ExpenseStatus.DRAFT.value),
        "show_approve": bool(actor.is_admin and transaction.status == ExpenseStatus.SUBMITTED.value),
        "show_reject": bool(actor.is_admin and transaction.status == ExpenseStatus.SUBMITTED.value),
        "show_return": bool(actor.is_admin and transaction.status == ExpenseStatus.SUBMITTED.value),
        "show_mark_paid": bool(actor.is_admin and transaction.status == ExpenseStatus.APPROVED.value),
        "show_delete_draft": bool(
            is_expense
            and transaction.status == ExpenseStatus.DRAFT.value
            and is_owner_or_admin
        )
        or bool(
            transaction.transaction_type == TransactionType.REVENUE.value
            and transaction.status == RevenueStatus.DRAFT.value
            and is_owner_or_admin
        ),
    }


def create_transaction_from_form(*, form: TransactionFormLike, transaction_type: str, actor: User) -> Transaction:
    _validate_dates(form.transaction_date.data, form.due_date.data, form.settled_date.data)
    item = Transaction(
        transaction_type=transaction_type,
        title=form.title.data.strip(),
        description=_normalize_optional_text(form.description.data),
        counterparty=_normalize_optional_text(form.counterparty.data),
        category_id=form.category_id.data,
        account_id=form.account_id.data,
        payment_method_id=form.payment_method_id.data or None,
        transaction_date=form.transaction_date.data,
        due_date=form.due_date.data,
        settled_date=form.settled_date.data,
        reference_number=_normalize_optional_text(form.reference_number.data),
        note=_normalize_optional_text(form.note.data),
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
    budget_snapshot = _apply_transaction_controls(item, strict=transaction_type == TransactionType.REVENUE.value or not form.save_draft.data)
    _sync_account_balance(item.account_id)
    _record_history(
        item,
        actor=actor,
        action="create",
        to_status=item.status,
        metadata={
            "budget": item.budget.name if item.budget else None,
            "policy": item.spend_policy.name if item.spend_policy else None,
            "mapping": item.accounting_mapping.name if item.accounting_mapping else None,
            "over_budget": bool(budget_snapshot and budget_snapshot["over_budget"]),
        },
    )
    record_audit(user_id=actor.id, entity_type="transaction", entity_id=item.id, action="create", new_values=_serialize(item))
    return item


def create_simple_revenue(
    *,
    company_name: str,
    amount: Decimal,
    transaction_date: date,
    payment_method_id: int | None,
    reference_number: str | None,
    note: str | None,
    actor: User,
) -> Transaction:
    normalized_company = _normalize_optional_text(company_name)
    if not normalized_company:
        raise ServiceError("Company name is required.")

    resolved_amount = Decimal(amount)
    if resolved_amount <= 0:
        raise ServiceError("Amount must be greater than zero.")

    item = Transaction(
        transaction_type=TransactionType.REVENUE.value,
        title=f"Revenue from {normalized_company}"[:160],
        counterparty=normalized_company,
        category_id=_resolve_default_category_id(TransactionType.REVENUE.value),
        account_id=_resolve_default_account_id(),
        payment_method_id=payment_method_id or None,
        amount=resolved_amount,
        expected_amount=resolved_amount,
        received_amount=resolved_amount,
        transaction_date=transaction_date,
        settled_date=transaction_date,
        reference_number=_normalize_optional_text(reference_number),
        note=_normalize_optional_text(note),
        status=RevenueStatus.RECEIVED.value,
        submitted_by_id=actor.id,
    )
    db.session.add(item)
    db.session.flush()
    _sync_account_balance(item.account_id)
    _record_history(item, actor=actor, action="create", to_status=item.status)
    record_audit(user_id=actor.id, entity_type="transaction", entity_id=item.id, action="create", new_values=_serialize(item))
    return item


def create_simple_expense(
    *,
    title: str,
    amount: Decimal,
    transaction_date: date,
    payment_method_id: int | None,
    reference_number: str | None,
    note: str | None,
    actor: User,
) -> Transaction:
    normalized_title = _normalize_optional_text(title)
    if not normalized_title:
        raise ServiceError("Expense description is required.")

    resolved_amount = Decimal(amount)
    if resolved_amount <= 0:
        raise ServiceError("Amount must be greater than zero.")

    item = Transaction(
        transaction_type=TransactionType.EXPENSE.value,
        title=normalized_title[:160],
        category_id=_resolve_default_category_id(TransactionType.EXPENSE.value),
        account_id=_resolve_default_account_id(),
        payment_method_id=payment_method_id or None,
        amount=resolved_amount,
        transaction_date=transaction_date,
        settled_date=transaction_date,
        reference_number=_normalize_optional_text(reference_number),
        note=_normalize_optional_text(note),
        status=ExpenseStatus.PAID.value,
        submitted_by_id=actor.id,
    )
    db.session.add(item)
    db.session.flush()
    _sync_account_balance(item.account_id)
    _record_history(item, actor=actor, action="create", to_status=item.status)
    record_audit(user_id=actor.id, entity_type="transaction", entity_id=item.id, action="create", new_values=_serialize(item))
    return item


def update_transaction_from_form(*, transaction: Transaction, form: TransactionFormLike, actor: User) -> Transaction:
    if not _can_edit(transaction, actor):
        raise ServiceError("You cannot edit this record in its current state.")
    _validate_dates(form.transaction_date.data, form.due_date.data, form.settled_date.data)
    previous = _serialize(transaction)
    previous_status = transaction.status
    previous_account_id = transaction.account_id
    transaction.title = form.title.data.strip()
    transaction.description = _normalize_optional_text(form.description.data)
    transaction.counterparty = _normalize_optional_text(form.counterparty.data)
    transaction.category_id = form.category_id.data
    transaction.account_id = form.account_id.data
    transaction.payment_method_id = form.payment_method_id.data or None
    transaction.transaction_date = form.transaction_date.data
    transaction.due_date = form.due_date.data
    transaction.settled_date = form.settled_date.data
    transaction.reference_number = _normalize_optional_text(form.reference_number.data)
    transaction.note = _normalize_optional_text(form.note.data)
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
        if actor.is_admin and form.status.data:
            transaction.status = form.status.data
        elif form.save_draft.data:
            transaction.status = ExpenseStatus.DRAFT.value
    _save_attachments(transaction, actor)
    budget_snapshot = _apply_transaction_controls(
        transaction,
        strict=transaction.transaction_type == TransactionType.REVENUE.value or not form.save_draft.data,
    )
    _sync_account_balance(previous_account_id)
    if transaction.account_id != previous_account_id:
        _sync_account_balance(transaction.account_id)
    _record_history(
        transaction,
        actor=actor,
        action="update",
        from_status=previous_status,
        to_status=transaction.status,
        metadata={
            "budget": transaction.budget.name if transaction.budget else None,
            "policy": transaction.spend_policy.name if transaction.spend_policy else None,
            "mapping": transaction.accounting_mapping.name if transaction.accounting_mapping else None,
            "over_budget": bool(budget_snapshot and budget_snapshot["over_budget"]),
        },
    )
    record_audit(user_id=actor.id, entity_type="transaction", entity_id=transaction.id, action="update", old_values=previous, new_values=_serialize(transaction))
    return transaction


def add_transaction_comment(transaction: Transaction, actor: User, body: str) -> TransactionComment:
    normalized_body = _normalize_optional_text(body)
    if not normalized_body:
        raise ServiceError("Comment cannot be empty.")
    comment = TransactionComment(transaction=transaction, user_id=actor.id, body=normalized_body)
    db.session.add(comment)
    _record_history(transaction, actor=actor, action="comment", note=normalized_body)
    record_audit(user_id=actor.id, entity_type="transaction", entity_id=transaction.id, action="comment")
    return comment


def submit_expense(transaction: Transaction, actor: User) -> None:
    if transaction.transaction_type != TransactionType.EXPENSE.value:
        raise ServiceError("Only expenses can be submitted.")
    if transaction.submitted_by_id != actor.id and not actor.is_admin:
        raise ServiceError("You can only submit your own expense draft.")
    if transaction.status == ExpenseStatus.SUBMITTED.value:
        return
    validate_status_transition(transaction.transaction_type, transaction.status, ExpenseStatus.SUBMITTED.value, override=actor.is_admin)
    _apply_transaction_controls(transaction, strict=True)
    previous = _serialize(transaction)
    previous_status = transaction.status
    transaction.status = ExpenseStatus.SUBMITTED.value
    _record_history(transaction, actor=actor, action="submit", from_status=previous_status, to_status=transaction.status)
    record_audit(user_id=actor.id, entity_type="transaction", entity_id=transaction.id, action="submit", old_values=previous, new_values=_serialize(transaction))


def approve_expense(transaction: Transaction, actor: User) -> None:
    if transaction.status == ExpenseStatus.APPROVED.value:
        if transaction.approved_by_id == actor.id:
            return
        raise ServiceError("Expense is already approved.")
    validate_status_transition(transaction.transaction_type, transaction.status, ExpenseStatus.APPROVED.value)
    previous = _serialize(transaction)
    previous_status = transaction.status
    transaction.status = ExpenseStatus.APPROVED.value
    transaction.approved_by_id = actor.id
    _record_history(transaction, actor=actor, action="approve", from_status=previous_status, to_status=transaction.status)
    record_audit(user_id=actor.id, entity_type="transaction", entity_id=transaction.id, action="approve", old_values=previous, new_values=_serialize(transaction))


def reject_expense(transaction: Transaction, actor: User, note: str) -> None:
    normalized_note = _normalize_optional_text(note)
    if not normalized_note:
        raise ServiceError("Rejection requires a reason.")
    if transaction.status == ExpenseStatus.REJECTED.value:
        if transaction.approved_by_id == actor.id and (transaction.note or "") == normalized_note:
            return
        raise ServiceError("Expense is already rejected.")
    validate_status_transition(transaction.transaction_type, transaction.status, ExpenseStatus.REJECTED.value)
    previous = _serialize(transaction)
    previous_status = transaction.status
    transaction.status = ExpenseStatus.REJECTED.value
    transaction.approved_by_id = actor.id
    transaction.note = normalized_note
    _record_history(transaction, actor=actor, action="reject", from_status=previous_status, to_status=transaction.status, note=normalized_note)
    record_audit(user_id=actor.id, entity_type="transaction", entity_id=transaction.id, action="reject", old_values=previous, new_values=_serialize(transaction))


def return_expense_for_edit(transaction: Transaction, actor: User, note: str) -> None:
    normalized_note = _normalize_optional_text(note)
    if not normalized_note:
        raise ServiceError("Returning an expense requires a note.")
    if transaction.status == ExpenseStatus.RETURNED.value:
        if transaction.approved_by_id == actor.id and (transaction.note or "") == normalized_note:
            return
        raise ServiceError("Expense has already been returned for edit.")
    validate_status_transition(transaction.transaction_type, transaction.status, ExpenseStatus.RETURNED.value)
    previous = _serialize(transaction)
    previous_status = transaction.status
    transaction.status = ExpenseStatus.RETURNED.value
    transaction.approved_by_id = actor.id
    transaction.note = normalized_note
    _record_history(transaction, actor=actor, action="return", from_status=previous_status, to_status=transaction.status, note=normalized_note)
    record_audit(user_id=actor.id, entity_type="transaction", entity_id=transaction.id, action="return", old_values=previous, new_values=_serialize(transaction))


def mark_expense_paid(transaction: Transaction, actor: User, settled_date: date | None) -> None:
    resolved_settled_date = settled_date or date.today()
    if transaction.status == ExpenseStatus.PAID.value:
        if transaction.approved_by_id == actor.id and transaction.settled_date == resolved_settled_date:
            return
        raise ServiceError("Expense is already marked paid.")
    validate_status_transition(transaction.transaction_type, transaction.status, ExpenseStatus.PAID.value)
    previous = _serialize(transaction)
    previous_status = transaction.status
    transaction.status = ExpenseStatus.PAID.value
    transaction.settled_date = resolved_settled_date
    transaction.approved_by_id = actor.id
    _sync_account_balance(transaction.account_id)
    _record_history(transaction, actor=actor, action="mark_paid", from_status=previous_status, to_status=transaction.status)
    record_audit(user_id=actor.id, entity_type="transaction", entity_id=transaction.id, action="mark_paid", old_values=previous, new_values=_serialize(transaction))


def mark_revenue_received(transaction: Transaction, actor: User, amount: Decimal | None, settled_date: date | None) -> None:
    expected = Decimal(transaction.expected_amount or transaction.amount or 0)
    received = Decimal(amount or expected)
    if received > expected and not actor.is_admin:
        raise ServiceError("Received amount cannot exceed expected amount without admin override.")
    previous = _serialize(transaction)
    previous_status = transaction.status
    transaction.received_amount = received
    transaction.settled_date = settled_date or date.today()
    transaction.status = derive_revenue_status(expected, received, transaction.due_date, date.today())
    _sync_account_balance(transaction.account_id)
    _record_history(transaction, actor=actor, action="mark_received", from_status=previous_status, to_status=transaction.status)
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
    _record_history(transaction, actor=actor, action="delete", from_status=transaction.status, note="Draft deleted")
    record_audit(user_id=actor.id, entity_type="transaction", entity_id=transaction.id, action="delete", old_values=previous)


def recent_transactions(user: User, limit: int = 8) -> list[Transaction]:
    return (
        visible_transactions_query(user)
        .options(*_transaction_display_options())
        .order_by(Transaction.transaction_date.desc(), Transaction.created_at.desc())
        .limit(limit)
        .all()
    )


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
    writer.writerow(
        [
            "ID",
            "Type",
            "Title",
            "Counterparty",
            "Status",
            "Amount",
            "Expected Amount",
            "Received Amount",
            "Transaction Date",
            "Due Date",
            "Settled Date",
            "Policy",
            "Budget",
            "GL Code",
            "Cost Center",
            "Project Code",
        ]
    )
    for item in items:
        writer.writerow(
            [
                item.id,
                item.transaction_type,
                item.title,
                item.counterparty or "",
                item.status,
                item.amount,
                item.expected_amount or "",
                item.received_amount or "",
                item.transaction_date,
                item.due_date or "",
                item.settled_date or "",
                item.spend_policy.name if item.spend_policy else "",
                item.budget.name if item.budget else "",
                item.accounting_gl_code or "",
                item.accounting_cost_center or "",
                item.accounting_project_code or "",
            ]
        )
    return buffer.getvalue()
