from __future__ import annotations

from collections.abc import Callable, Mapping
from decimal import Decimal

from app.extensions import db
from app.models import Account, AccountingMapping, AuditLog, Budget, Category, PaymentMethod, SpendPolicy, User
from app.utils.enums import AccountType, Role, TransactionType


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


def test_admin_user_creation_is_immediately_usable(client, app, sample_data, login):
    login("admin@example.com", "AdminPassword123")
    response = client.post(
        "/settings/users",
        data={
            "full_name": "Ops User",
            "email": "ops@example.com",
            "password": "OpsAccess123",
            "role": "staff",
            "is_active": "y",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    with app.app_context():
        user = User.query.filter_by(email="ops@example.com").one()
        assert user.email_verified is True
        assert user.is_active is True


def test_admin_can_promote_staff_user(client, app, sample_data, login):
    login("admin@example.com", "AdminPassword123")
    response = client.post(
        f"/settings/users/{sample_data['staff_id']}/role",
        data={"role": Role.ADMIN.value},
        follow_redirects=False,
    )

    assert response.status_code == 302
    with app.app_context():
        user = db.session.get(User, sample_data["staff_id"])
        assert user is not None
        assert user.role == Role.ADMIN.value
        audit = AuditLog.query.filter_by(entity_type="user", entity_id=user.id, action="admin_update_user_role").one()
        assert audit.old_values_json == {"role": Role.STAFF.value}
        assert audit.new_values_json == {"role": Role.ADMIN.value}


def test_admin_can_demote_other_admin_user(client, app, sample_data, login):
    with app.app_context():
        promoted_admin = db.session.get(User, sample_data["staff_id"])
        assert promoted_admin is not None
        promoted_admin.role = Role.ADMIN.value
        db.session.commit()

    login("admin@example.com", "AdminPassword123")
    response = client.post(
        f"/settings/users/{sample_data['staff_id']}/role",
        data={"role": Role.STAFF.value},
        follow_redirects=False,
    )

    assert response.status_code == 302
    with app.app_context():
        user = db.session.get(User, sample_data["staff_id"])
        assert user is not None
        assert user.role == Role.STAFF.value


def test_admin_cannot_demote_self(client, app, sample_data, login):
    login("admin@example.com", "AdminPassword123")
    response = client.post(
        f"/settings/users/{sample_data['admin_id']}/role",
        data={"role": Role.STAFF.value},
        follow_redirects=False,
    )

    assert response.status_code == 302
    with app.app_context():
        user = db.session.get(User, sample_data["admin_id"])
        assert user is not None
        assert user.role == Role.ADMIN.value
