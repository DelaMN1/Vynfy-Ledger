from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.extensions import db
from app.models import Account, Category, PaymentMethod, Transaction, User
from app.utils.audit import record_audit
from app.utils.enums import CategoryType, ExpenseStatus, RevenueStatus, Role, TransactionType


def create_category(*, name: str, category_type: str, color: str, description: str, actor: User) -> Category:
    category = Category(name=name.strip(), type=category_type, color=color, description=description)
    db.session.add(category)
    db.session.flush()
    record_audit(user_id=actor.id, entity_type="category", entity_id=category.id, action="create")
    return category


def create_account(*, name: str, account_type: str, opening_balance, currency_code: str, actor: User) -> Account:
    account = Account(name=name.strip(), type=account_type, opening_balance=opening_balance, current_balance_cached=opening_balance, currency_code=currency_code)
    db.session.add(account)
    db.session.flush()
    record_audit(user_id=actor.id, entity_type="account", entity_id=account.id, action="create")
    return account


def create_payment_method(*, name: str, actor: User) -> PaymentMethod:
    method = PaymentMethod(name=name.strip())
    db.session.add(method)
    db.session.flush()
    record_audit(user_id=actor.id, entity_type="payment_method", entity_id=method.id, action="create")
    return method


def seed_demo_data() -> None:
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
        Account(name="Main Bank", type="bank", opening_balance=Decimal("150000.00"), current_balance_cached=Decimal("150000.00"), currency_code="GHS"),
        Account(name="Mobile Money", type="mobile_money", opening_balance=Decimal("12000.00"), current_balance_cached=Decimal("12000.00"), currency_code="GHS"),
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
