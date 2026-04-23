from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TypeVar

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Account, AccountingMapping, Budget, Category, PaymentMethod, SpendPolicy, Transaction, User
from app.utils.audit import record_audit
from app.utils.exceptions import ServiceError
from app.utils.enums import AccountType


NamedModelT = TypeVar("NamedModelT", Account, Category, PaymentMethod)


def _normalized_name(value: str) -> str:
    return value.strip()


def _find_named_item(model: type[NamedModelT], name: str) -> NamedModelT | None:
    normalized_name = _normalized_name(name)
    return model.query.filter(func.lower(model.name) == normalized_name.lower()).first()


def _persist_named_item(item: NamedModelT, *, actor: User, entity_type: str, conflict_message: str) -> NamedModelT:
    db.session.add(item)
    try:
        db.session.flush()
    except IntegrityError as exc:
        raise ServiceError(conflict_message) from exc
    record_audit(user_id=actor.id, entity_type=entity_type, entity_id=item.id, action="create")
    return item


def create_category(*, name: str, category_type: str, color: str, description: str | None, actor: User) -> Category:
    normalized_name = _normalized_name(name)
    normalized_description = (description or "").strip() or None
    existing = _find_named_item(Category, normalized_name)
    if existing:
        if existing.type == category_type and existing.color == color and (existing.description or None) == normalized_description:
            return existing
        raise ServiceError("A category with that name already exists.")

    category = Category(name=normalized_name, type=category_type, color=color, description=normalized_description)
    return _persist_named_item(category, actor=actor, entity_type="category", conflict_message="A category with that name already exists.")


def create_account(
    *,
    name: str,
    account_type: str,
    opening_balance: Decimal | int | str,
    currency_code: str,
    actor: User,
) -> Account:
    normalized_name = _normalized_name(name)
    normalized_currency = currency_code.strip().upper()
    opening = Decimal(opening_balance)
    existing = _find_named_item(Account, normalized_name)
    if existing:
        if existing.type == account_type and Decimal(existing.opening_balance or 0) == opening and existing.currency_code == normalized_currency:
            return existing
        raise ServiceError("An account with that name already exists.")

    account = Account(
        name=normalized_name,
        type=account_type,
        opening_balance=opening,
        current_balance_cached=opening,
        currency_code=normalized_currency,
    )
    return _persist_named_item(account, actor=actor, entity_type="account", conflict_message="An account with that name already exists.")


def create_payment_method(*, name: str, actor: User) -> PaymentMethod:
    normalized_name = _normalized_name(name)
    existing = _find_named_item(PaymentMethod, normalized_name)
    if existing:
        return existing

    method = PaymentMethod(name=normalized_name)
    return _persist_named_item(method, actor=actor, entity_type="payment_method", conflict_message="A payment method with that name already exists.")


def create_budget(
    *,
    name: str,
    transaction_type: str | None,
    category_id: int | None,
    account_id: int | None,
    owner_id: int | None,
    amount: Decimal | int | str,
    alert_percent: int,
    actor: User,
) -> Budget:
    normalized_name = _normalized_name(name)
    budget_amount = Decimal(amount)
    existing = Budget.query.filter(func.lower(Budget.name) == normalized_name.lower()).first()
    if existing:
        if (
            existing.transaction_type == (transaction_type or None)
            and existing.category_id == category_id
            and existing.account_id == account_id
            and existing.owner_id == owner_id
            and Decimal(existing.amount or 0) == budget_amount
            and existing.alert_percent == alert_percent
            and existing.is_active
        ):
            return existing
        raise ServiceError("A budget with that name already exists.")

    budget = Budget(
        name=normalized_name,
        transaction_type=transaction_type or None,
        category_id=category_id,
        account_id=account_id,
        owner_id=owner_id,
        amount=budget_amount,
        alert_percent=alert_percent,
    )
    db.session.add(budget)
    try:
        db.session.flush()
    except IntegrityError as exc:
        raise ServiceError("A budget with that name already exists.") from exc
    record_audit(user_id=actor.id, entity_type="budget", entity_id=budget.id, action="create")
    return budget


def create_spend_policy(
    *,
    name: str,
    transaction_type: str | None,
    category_id: int | None,
    account_id: int | None,
    payment_method_id: int | None,
    max_amount: Decimal | int | str | None,
    require_attachment: bool,
    require_note: bool,
    block_on_over_budget: bool,
    description: str | None,
    actor: User,
) -> SpendPolicy:
    normalized_name = _normalized_name(name)
    normalized_description = (description or "").strip() or None
    max_value = Decimal(max_amount) if max_amount is not None else None
    existing = SpendPolicy.query.filter(func.lower(SpendPolicy.name) == normalized_name.lower()).first()
    if existing:
        if (
            existing.transaction_type == (transaction_type or None)
            and existing.category_id == category_id
            and existing.account_id == account_id
            and existing.payment_method_id == payment_method_id
            and Decimal(existing.max_amount or 0) == Decimal(max_value or 0)
            and existing.require_attachment == require_attachment
            and existing.require_note == require_note
            and existing.block_on_over_budget == block_on_over_budget
            and (existing.description or None) == normalized_description
            and existing.is_active
        ):
            return existing
        raise ServiceError("A spend policy with that name already exists.")

    policy = SpendPolicy(
        name=normalized_name,
        transaction_type=transaction_type or None,
        category_id=category_id,
        account_id=account_id,
        payment_method_id=payment_method_id,
        max_amount=max_value,
        require_attachment=require_attachment,
        require_note=require_note,
        block_on_over_budget=block_on_over_budget,
        description=normalized_description,
    )
    db.session.add(policy)
    try:
        db.session.flush()
    except IntegrityError as exc:
        raise ServiceError("A spend policy with that name already exists.") from exc
    record_audit(user_id=actor.id, entity_type="spend_policy", entity_id=policy.id, action="create")
    return policy


def create_accounting_mapping(
    *,
    name: str,
    transaction_type: str | None,
    category_id: int | None,
    account_id: int | None,
    payment_method_id: int | None,
    gl_code: str,
    cost_center: str | None,
    project_code: str | None,
    actor: User,
) -> AccountingMapping:
    normalized_name = _normalized_name(name)
    normalized_gl_code = gl_code.strip().upper()
    normalized_cost_center = (cost_center or "").strip().upper() or None
    normalized_project_code = (project_code or "").strip().upper() or None
    existing = AccountingMapping.query.filter(func.lower(AccountingMapping.name) == normalized_name.lower()).first()
    if existing:
        if (
            existing.transaction_type == (transaction_type or None)
            and existing.category_id == category_id
            and existing.account_id == account_id
            and existing.payment_method_id == payment_method_id
            and existing.gl_code == normalized_gl_code
            and existing.cost_center == normalized_cost_center
            and existing.project_code == normalized_project_code
            and existing.is_active
        ):
            return existing
        raise ServiceError("An accounting mapping with that name already exists.")

    mapping = AccountingMapping(
        name=normalized_name,
        transaction_type=transaction_type or None,
        category_id=category_id,
        account_id=account_id,
        payment_method_id=payment_method_id,
        gl_code=normalized_gl_code,
        cost_center=normalized_cost_center,
        project_code=normalized_project_code,
    )
    db.session.add(mapping)
    try:
        db.session.flush()
    except IntegrityError as exc:
        raise ServiceError("An accounting mapping with that name already exists.") from exc
    record_audit(user_id=actor.id, entity_type="accounting_mapping", entity_id=mapping.id, action="create")
    return mapping
