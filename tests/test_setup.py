from __future__ import annotations

from app.extensions import db
from app.models import Account, Category, PaymentMethod, User


def test_login_page_exposes_initialize_link_when_no_admin(client):
    response = client.get("/login", follow_redirects=False)
    assert response.status_code == 200
    assert b"Initialize system" in response.data


def test_login_page_hides_initialize_link_when_bootstrap_disabled(client, app):
    app.config.update(APP_ENV="production", BOOTSTRAP_SETUP_ENABLED=True, BOOTSTRAP_SETUP_TOKEN=None)
    response = client.get("/login", follow_redirects=False)
    assert response.status_code == 200
    assert b"Initialize system" not in response.data


def test_initialize_first_admin_creates_seed_data(client, app):
    response = client.post(
        "/setup/initialize",
        data={
            "full_name": "Initial Admin",
            "email": "admin@example.com",
            "password": "RootLedger123",
            "confirm_password": "RootLedger123",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")

    with app.app_context():
        user = User.query.filter_by(email="admin@example.com").one()
        assert user.role == "admin"
        assert user.can_create_expense is True
        assert Category.query.count() >= 5
        assert Account.query.count() >= 1
        assert PaymentMethod.query.count() >= 3


def test_initialize_requires_bootstrap_token_when_configured(client, app):
    app.config["BOOTSTRAP_SETUP_TOKEN"] = "top-secret-bootstrap"
    response = client.post(
        "/setup/initialize",
        data={
            "full_name": "Initial Admin",
            "email": "admin@example.com",
            "password": "RootLedger123",
            "confirm_password": "RootLedger123",
            "access_token": "wrong-token",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Bootstrap access token is invalid." in response.data


def test_initialize_route_disables_after_admin_exists(client, app):
    with app.app_context():
        user = User(full_name="Existing Admin", email="existing@example.com", role="admin", email_verified=True, is_active=True)
        user.set_password("RootLedger123")
        db.session.add(user)
        db.session.commit()

    response = client.get("/setup/initialize", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_setup_seed_cli_is_idempotent(app):
    runner = app.test_cli_runner()

    first = runner.invoke(args=["setup", "baseline"])
    second = runner.invoke(args=["setup", "baseline"])

    assert first.exit_code == 0
    assert second.exit_code == 0
    with app.app_context():
        assert Category.query.count() == 5
        assert Account.query.count() == 1
        assert PaymentMethod.query.count() == 3


def test_balances_recalc_cli_repairs_cached_drift(app, sample_data):
    runner = app.test_cli_runner()

    check = runner.invoke(args=["balances", "check"])
    recalc = runner.invoke(args=["balances", "recalc"])

    assert check.exit_code == 0
    assert "drifted_accounts=1" in check.output
    assert recalc.exit_code == 0
    with app.app_context():
        account = db.session.get(Account, sample_data["account_id"])
        assert account is not None
        assert str(account.current_balance_cached) == "2000.00"
