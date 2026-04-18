from __future__ import annotations

from collections.abc import Callable, Mapping
from decimal import Decimal

from app.models import Account, Category, PaymentMethod
from app.utils.enums import AccountType


SettingsModel = Account | Category | PaymentMethod


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
