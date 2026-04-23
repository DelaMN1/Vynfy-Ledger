from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Protocol, TypedDict
from uuid import uuid4

import pytest
from flask import Response

from app import create_app
from app.extensions import db
from app.models import Account, Category, PaymentMethod, Transaction, User
from app.utils.enums import AccountType, CategoryType, ExpenseStatus, RevenueStatus, Role, TransactionType


class SampleData(TypedDict):
    admin_id: int
    staff_id: int
    revenue_staff_id: int
    outsider_id: int
    draft_expense_id: int
    submitted_expense_id: int
    revenue_id: int
    account_id: int
    expense_category_id: int
    revenue_category_id: int
    payment_method_id: int


class LoginHelper(Protocol):
    def __call__(self, email: str, password: str, *, finish: bool = True) -> Response: ...


@pytest.fixture
def app():
    tmp_path = Path.cwd() / ".tmp-tests" / uuid4().hex
    tmp_path.mkdir(parents=True, exist_ok=True)
    app = create_app("testing")
    app.config.update(
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        UPLOAD_FOLDER=str(tmp_path / "uploads"),
        OUTBOX_FOLDER=str(tmp_path / "outbox"),
        SENDGRID_API_KEY=None,
        SMTP_HOST=None,
        SMTP_USERNAME=None,
        SMTP_PASSWORD=None,
        MAX_FAILED_LOGINS=10,
        LOGIN_LOCKOUT_BASE_MINUTES=1,
        MAX_LOGIN_LOCKOUT_MINUTES=60,
        PASSWORD_RESET_MINUTES=30,
        ADMIN_STEP_UP_MINUTES=15,
        RATELIMIT_ENABLED=False,
        TESTING=True,
    )
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def sample_data(app) -> SampleData:
    with app.app_context():
        admin = User(full_name="Admin User", email="admin@example.com", role=Role.ADMIN.value, email_verified=True, can_create_revenue=True)
        admin.set_password("AdminPassword123")
        staff = User(full_name="Staff User", email="staff@example.com", role=Role.STAFF.value, email_verified=True)
        staff.set_password("StaffPassword123")
        revenue_staff = User(full_name="Revenue Staff", email="revenue@example.com", role=Role.STAFF.value, email_verified=True, can_create_revenue=True)
        revenue_staff.set_password("RevenuePassword123")
        outsider = User(full_name="Other User", email="other@example.com", role=Role.STAFF.value, email_verified=True)
        outsider.set_password("OtherPassword123")
        db.session.add_all([admin, staff, revenue_staff, outsider])
        db.session.flush()

        rev_category = Category(name="Consulting", type=CategoryType.REVENUE.value, color="#15803d")
        exp_category = Category(name="Operations", type=CategoryType.EXPENSE.value, color="#dc2626")
        account = Account(
            name="Main Account",
            type=AccountType.BANK.value,
            opening_balance=Decimal("1000.00"),
            current_balance_cached=Decimal("1000.00"),
            currency_code="GHS",
        )
        payment_method = PaymentMethod(name="Bank Transfer")
        db.session.add_all([rev_category, exp_category, account, payment_method])
        db.session.flush()

        draft_expense = Transaction(
            transaction_type=TransactionType.EXPENSE.value,
            title="Draft expense",
            counterparty="Vendor A",
            category_id=exp_category.id,
            account_id=account.id,
            payment_method_id=payment_method.id,
            amount=Decimal("120.00"),
            transaction_date=date.today(),
            status=ExpenseStatus.DRAFT.value,
            submitted_by_id=staff.id,
        )
        submitted_expense = Transaction(
            transaction_type=TransactionType.EXPENSE.value,
            title="Submitted expense",
            counterparty="Vendor B",
            category_id=exp_category.id,
            account_id=account.id,
            payment_method_id=payment_method.id,
            amount=Decimal("300.00"),
            transaction_date=date.today() - timedelta(days=2),
            due_date=date.today() - timedelta(days=1),
            status=ExpenseStatus.SUBMITTED.value,
            submitted_by_id=staff.id,
        )
        revenue_item = Transaction(
            transaction_type=TransactionType.REVENUE.value,
            title="Client retainer",
            counterparty="Client X",
            category_id=rev_category.id,
            account_id=account.id,
            payment_method_id=payment_method.id,
            amount=Decimal("1000.00"),
            expected_amount=Decimal("1000.00"),
            received_amount=Decimal("1000.00"),
            transaction_date=date.today() - timedelta(days=5),
            settled_date=date.today() - timedelta(days=3),
            status=RevenueStatus.RECEIVED.value,
            submitted_by_id=admin.id,
        )
        db.session.add_all([draft_expense, submitted_expense, revenue_item])
        db.session.commit()
        return {
            "admin_id": admin.id,
            "staff_id": staff.id,
            "revenue_staff_id": revenue_staff.id,
            "outsider_id": outsider.id,
            "draft_expense_id": draft_expense.id,
            "submitted_expense_id": submitted_expense.id,
            "revenue_id": revenue_item.id,
            "account_id": account.id,
            "expense_category_id": exp_category.id,
            "revenue_category_id": rev_category.id,
            "payment_method_id": payment_method.id,
        }


@pytest.fixture
def login(client) -> LoginHelper:
    def _login(email: str, password: str, *, finish: bool = True) -> Response:
        return client.post("/login", data={"email": email, "password": password}, follow_redirects=False)

    return _login
