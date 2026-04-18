from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TypeVar

from flask import current_app
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Account, Category, PaymentMethod, Transaction, User
from app.utils.audit import record_audit
from app.utils.exceptions import ServiceError
from app.utils.enums import AccountType, CategoryType, ExpenseStatus, RevenueStatus, Role, TransactionType


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


def seed_demo_data() -> None:
    if not current_app.config["ALLOW_DEMO_SEED"]:
        raise ServiceError("Demo seed data is disabled outside development and testing.")
    if User.query.filter_by(email="admin@vynfy.internal").first():
        return
    admin = User(full_name="Vynfy Admin", email="admin@vynfy.internal", role=Role.ADMIN.value, email_verified=True, can_create_revenue=True)
    admin.set_password("LedgerAdmin123")
    staff_one = User(full_name="Ama Mensah", email="ama@vynfy.internal", role=Role.STAFF.value, email_verified=True)
    staff_one.set_password("AmaStaff1234")
    staff_two = User(full_name="Kojo Arthur", email="kojo@vynfy.internal", role=Role.STAFF.value, email_verified=True, can_create_revenue=True)
    staff_two.set_password("KojoRevenue123")
    db.session.add_all([admin, staff_one, staff_two])
    db.session.flush()

    revenue_categories = [
        Category(name="Client Retainers", type=CategoryType.REVENUE.value, color="#15803d"),
        Category(name="Campaign Delivery", type=CategoryType.REVENUE.value, color="#166534"),
    ]
    expense_categories = [
        Category(name="Marketing", type=CategoryType.EXPENSE.value, color="#dc2626"),
        Category(name="Operations", type=CategoryType.EXPENSE.value, color="#b45309"),
        Category(name="Travel", type=CategoryType.EXPENSE.value, color="#ea580c"),
    ]
    accounts = [
        Account(
            name="Main Bank",
            type=AccountType.BANK.value,
            opening_balance=Decimal("150000.00"),
            current_balance_cached=Decimal("150000.00"),
            currency_code="GHS",
        ),
        Account(
            name="Mobile Money",
            type=AccountType.MOBILE_MONEY.value,
            opening_balance=Decimal("12000.00"),
            current_balance_cached=Decimal("12000.00"),
            currency_code="GHS",
        ),
    ]
    methods = [PaymentMethod(name="Bank Transfer"), PaymentMethod(name="Mobile Money"), PaymentMethod(name="Cash")]
    db.session.add_all(revenue_categories + expense_categories + accounts + methods)
    db.session.flush()

    db.session.add_all(
        [
            Transaction(
                transaction_type=TransactionType.REVENUE.value,
                title="March retainer",
                counterparty="Acme Health",
                category_id=revenue_categories[0].id,
                account_id=accounts[0].id,
                payment_method_id=methods[0].id,
                amount=Decimal("35000.00"),
                expected_amount=Decimal("35000.00"),
                received_amount=Decimal("35000.00"),
                transaction_date=date.today() - timedelta(days=18),
                settled_date=date.today() - timedelta(days=14),
                status=RevenueStatus.RECEIVED.value,
                submitted_by_id=admin.id,
            ),
            Transaction(
                transaction_type=TransactionType.EXPENSE.value,
                title="Team transport",
                counterparty="Bolt Business",
                category_id=expense_categories[2].id,
                account_id=accounts[1].id,
                payment_method_id=methods[1].id,
                amount=Decimal("850.00"),
                transaction_date=date.today() - timedelta(days=6),
                due_date=date.today() - timedelta(days=2),
                status=ExpenseStatus.SUBMITTED.value,
                submitted_by_id=staff_one.id,
            ),
            Transaction(
                transaction_type=TransactionType.EXPENSE.value,
                title="Studio rent",
                counterparty="Spintex Plaza",
                category_id=expense_categories[1].id,
                account_id=accounts[0].id,
                payment_method_id=methods[0].id,
                amount=Decimal("4200.00"),
                transaction_date=date.today() - timedelta(days=12),
                settled_date=date.today() - timedelta(days=8),
                status=ExpenseStatus.PAID.value,
                submitted_by_id=staff_two.id,
                approved_by_id=admin.id,
            ),
        ]
    )
    db.session.commit()
