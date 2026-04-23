from __future__ import annotations

from collections.abc import Callable, Mapping
from decimal import Decimal

from app.models import Account, AccountingMapping, Budget, Category, PaymentMethod, SpendPolicy
from app.utils.enums import AccountType, TransactionType


SettingsModel = Account | Category | PaymentMethod | Budget | SpendPolicy | AccountingMapping


def _assert_duplicate_submit_is_idempotent(
    *,
    client,
    app,
    login,
    path: str,
    payload: Mapping[str, str],
    model: type[SettingsModel],
    lookup_kwargs: Mapping[str, str],
    extra_assertions: Callable[[SettingsModel], None] | None = None,
):
    login("admin@example.com", "AdminPassword123")
    first = client.post(path, data=payload, follow_redirects=False)
    second = client.post(path, data=payload, follow_redirects=False)

    assert first.status_code == 302
    assert second.status_code == 302
    with app.app_context():
        items = model.query.filter_by(**lookup_kwargs).all()
        assert len(items) == 1
        if extra_assertions:
            extra_assertions(items[0])


def _assert_normalized_account(item) -> None:
    assert Decimal(item.opening_balance) == Decimal("1000.00")
    assert item.currency_code == "GHS"


def test_duplicate_category_submit_is_idempotent(client, app, sample_data, login):
    _assert_duplicate_submit_is_idempotent(
        client=client,
        app=app,
        login=login,
        path="/settings/categories",
        payload={"name": "Operations", "type": "expense", "color": "#dc2626", "description": ""},
        model=Category,
        lookup_kwargs={"name": "Operations"},
    )


def test_duplicate_account_submit_is_idempotent(client, app, sample_data, login):
    _assert_duplicate_submit_is_idempotent(
        client=client,
        app=app,
        login=login,
        path="/settings/accounts",
        payload={
            "name": "Main Account",
            "type": AccountType.BANK.value,
            "opening_balance": "1000.00",
            "currency_code": "ghs",
        },
        model=Account,
        lookup_kwargs={"name": "Main Account"},
        extra_assertions=_assert_normalized_account,
    )


def test_duplicate_payment_method_submit_is_idempotent(client, app, sample_data, login):
    _assert_duplicate_submit_is_idempotent(
        client=client,
        app=app,
        login=login,
        path="/settings/payment-methods",
        payload={"name": "Bank Transfer"},
        model=PaymentMethod,
        lookup_kwargs={"name": "Bank Transfer"},
    )


def test_duplicate_budget_submit_is_idempotent(client, app, sample_data, login):
    _assert_duplicate_submit_is_idempotent(
        client=client,
        app=app,
        login=login,
        path="/settings/budgets",
        payload={
            "name": "Ops Budget",
            "transaction_type": TransactionType.EXPENSE.value,
            "category_id": str(sample_data["expense_category_id"]),
            "account_id": str(sample_data["account_id"]),
            "owner_id": str(sample_data["staff_id"]),
            "amount": "2000.00",
            "alert_percent": "80",
        },
        model=Budget,
        lookup_kwargs={"name": "Ops Budget"},
    )


def test_duplicate_policy_submit_is_idempotent(client, app, sample_data, login):
    _assert_duplicate_submit_is_idempotent(
        client=client,
        app=app,
        login=login,
        path="/settings/policies",
        payload={
            "name": "Ops Policy",
            "transaction_type": TransactionType.EXPENSE.value,
            "category_id": str(sample_data["expense_category_id"]),
            "account_id": str(sample_data["account_id"]),
            "payment_method_id": str(sample_data["payment_method_id"]),
            "max_amount": "500.00",
            "require_attachment": "y",
        },
        model=SpendPolicy,
        lookup_kwargs={"name": "Ops Policy"},
    )


def test_duplicate_accounting_mapping_submit_is_idempotent(client, app, sample_data, login):
    _assert_duplicate_submit_is_idempotent(
        client=client,
        app=app,
        login=login,
        path="/settings/accounting-mappings",
        payload={
            "name": "Ops GL",
            "transaction_type": TransactionType.EXPENSE.value,
            "category_id": str(sample_data["expense_category_id"]),
            "account_id": str(sample_data["account_id"]),
            "payment_method_id": str(sample_data["payment_method_id"]),
            "gl_code": "6000",
            "cost_center": "OPS",
            "project_code": "HQ",
        },
        model=AccountingMapping,
        lookup_kwargs={"name": "Ops GL"},
    )


def test_new_settings_pages_render_for_admin(client, sample_data, login):
    login("admin@example.com", "AdminPassword123")
    assert client.get("/settings/budgets").status_code == 200
    assert client.get("/settings/policies").status_code == 200
    assert client.get("/settings/accounting-mappings").status_code == 200
