from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

import app.auth.services as auth_services
from app.extensions import db
from app.models import User, UserSession
from app.utils.security import generate_token, hash_token
from app.utils.time import utcnow
from app.utils.types import PasswordResetTokenPayload, VerificationTokenPayload


def test_registration_creates_unverified_user_and_outbox(client, app):
    response = client.post(
        "/register",
        data={
            "full_name": "New User",
            "email": "new@example.com",
            "password": "ComplexPass123",
            "confirm_password": "ComplexPass123",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    with app.app_context():
        user = User.query.filter_by(email="new@example.com").first()
        assert user is not None
        assert user.email_verified is False


def test_registration_duplicate_flush_shows_friendly_error(client, monkeypatch):
    def duplicate_flush(*args, **kwargs):
        raise IntegrityError("insert users", {}, Exception("UNIQUE constraint failed: users.email"))

    monkeypatch.setattr(auth_services.db.session, "flush", duplicate_flush)
    response = client.post(
        "/register",
        data={
            "full_name": "New User",
            "email": "new@example.com",
            "password": "ComplexPass123",
            "confirm_password": "ComplexPass123",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"An account with that email already exists." in response.data


def test_email_verification_flow(client, app):
    with app.app_context():
        user = User(full_name="Pending User", email="pending@example.com", email_verified=False)
        user.set_password("PendingPassword123")
        db.session.add(user)
        db.session.commit()
        verification_payload: VerificationTokenPayload = {"purpose": "verify-email", "user_id": user.id}
        token = generate_token(verification_payload)
    response = client.get(f"/verify-email/{token}", follow_redirects=False)
    assert response.status_code == 302
    with app.app_context():
        user = User.query.filter_by(email="pending@example.com").first()
        assert user.email_verified is True


def test_login_logout_and_session_rotation(client, app, sample_data, login):
    response = login("admin@example.com", "AdminPassword123", finish=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")
    assert "vynfy_session=" in response.headers.get("Set-Cookie", "")

    with app.app_context():
        session = UserSession.query.one()
        session.issued_at = utcnow() - timedelta(minutes=20)
        db.session.commit()
        db.session.remove()

    rotated = client.get("/dashboard")
    assert rotated.status_code == 200
    assert "vynfy_session=" in rotated.headers.get("Set-Cookie", "")

    with app.app_context():
        sessions = UserSession.query.order_by(UserSession.id.asc()).all()
        assert len(sessions) == 2
        assert sessions[0].revoked_at is not None
        assert sessions[0].replaced_by_token_id == sessions[1].id
        assert sessions[0].second_factor_verified_at == sessions[1].second_factor_verified_at
        db.session.remove()

    logout_response = client.post("/logout", follow_redirects=False)
    assert logout_response.status_code == 302
    with app.app_context():
        assert UserSession.query.filter(UserSession.revoked_at.is_(None)).count() == 0


def test_login_does_not_send_challenge_email(client, app, sample_data):
    outbox_dir = Path(app.config["OUTBOX_FOLDER"])
    response = client.post("/login", data={"email": "staff@example.com", "password": "StaffPassword123"}, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")
    assert not outbox_dir.exists() or not any(outbox_dir.iterdir())


def test_fresh_login_revokes_prior_active_sessions(app, sample_data):
    first_client = app.test_client()
    second_client = app.test_client()

    first = first_client.post("/login", data={"email": "staff@example.com", "password": "StaffPassword123"}, follow_redirects=False)
    assert first.status_code == 302

    with app.app_context():
        first_session = UserSession.query.filter(UserSession.revoked_at.is_(None)).one()
        first_session_id = first_session.id

    second = second_client.post("/login", data={"email": "staff@example.com", "password": "StaffPassword123"}, follow_redirects=False)
    assert second.status_code == 302

    with app.app_context():
        sessions = UserSession.query.order_by(UserSession.id.asc()).all()
        assert len(sessions) == 2
        assert db.session.get(UserSession, first_session_id).revoked_at is not None
        assert UserSession.query.filter(UserSession.revoked_at.is_(None)).count() == 1


def test_csrf_tokens_do_not_expire_by_default(app):
    assert app.config["WTF_CSRF_TIME_LIMIT"] is None


def test_password_reset_invalidates_existing_reset_tokens_and_sessions(client, app):
    with app.app_context():
        user = User(full_name="Reset User", email="reset@example.com", email_verified=True)
        user.set_password("ResetPassword123")
        db.session.add(user)
        db.session.flush()
        active_session = UserSession(
            user_id=user.id,
            token_hash=hash_token("active-session"),
            issued_at=utcnow(),
            expires_at=utcnow() + timedelta(minutes=30),
            second_factor_verified_at=utcnow(),
        )
        db.session.add(active_session)
        db.session.commit()
        token = generate_token(
            {
                "purpose": "reset-password",
                "user_id": user.id,
                "password_changed_at": user.password_changed_at.isoformat(),
            }
        )
        user_id = user.id
        session_id = active_session.id

    with app.test_request_context("/reset-password/test", method="POST"):
        auth_services.reset_user_password(token, "BrandNewCredential123")
        db.session.commit()

    with app.app_context():
        user = db.session.get(User, user_id)
        assert user.check_password("BrandNewCredential123")
        assert db.session.get(UserSession, session_id).revoked_at is not None

    with app.test_request_context("/reset-password/test", method="POST"):
        with pytest.raises(ValueError, match="Password reset link is invalid."):
            auth_services.reset_user_password(token, "AnotherFreshCredential123")


def test_failed_login_locks_account(client, app, sample_data):
    for _ in range(9):
        client.post("/login", data={"email": "staff@example.com", "password": "wrong-password"})
    with app.app_context():
        user = User.query.filter_by(email="staff@example.com").first()
        assert user.locked_until is None

    client.post("/login", data={"email": "staff@example.com", "password": "wrong-password"})
    with app.app_context():
        user = User.query.filter_by(email="staff@example.com").first()
        assert user.locked_until is not None
        first_lock = user.locked_until

    with app.test_request_context("/login", method="POST"):
        with pytest.raises(ValueError, match="Invalid email or password."):
            auth_services.authenticate_user(email="staff@example.com", password="StaffPassword123")
        db.session.commit()

    with app.app_context():
        user = User.query.filter_by(email="staff@example.com").first()
        user.locked_until = utcnow() - timedelta(seconds=1)
        db.session.commit()

    with app.test_request_context("/login", method="POST"):
        with pytest.raises(ValueError, match="Invalid email or password."):
            auth_services.authenticate_user(email="staff@example.com", password="wrong-password")
        db.session.commit()

        user = User.query.filter_by(email="staff@example.com").first()
        assert user.locked_until is not None
        assert user.locked_until > first_lock


def test_protected_routes_require_auth_by_default(client):
    protected = client.get("/reports", follow_redirects=False)
    public = client.get("/forgot-password", follow_redirects=False)
    assert protected.status_code == 302
    assert "/login" in protected.headers["Location"]
    assert public.status_code == 200


def test_password_login_defaults_to_dashboard_when_no_safe_next(client, sample_data):
    response = client.post("/login", data={"email": "staff@example.com", "password": "StaffPassword123"}, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")


def test_login_next_redirect_is_sanitized(client, sample_data):
    response = client.post(
        "/login?next=https://attacker.example/steal",
        data={"email": "staff@example.com", "password": "StaffPassword123"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")


def test_password_reset_uses_configured_expiry(client, app, monkeypatch):
    with app.app_context():
        user = User(full_name="Reset User", email="reset@example.com", email_verified=True)
        user.set_password("ResetPassword123")
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    captured = {}

    def fake_load_token(_token: str, max_age: int) -> PasswordResetTokenPayload:
        captured["max_age"] = max_age
        with app.app_context():
            user = db.session.get(User, user_id)
            return {
                "purpose": "reset-password",
                "user_id": user_id,
                "password_changed_at": user.password_changed_at.isoformat(),
            }

    monkeypatch.setattr(auth_services, "load_token", fake_load_token)
    with app.app_context():
        auth_services.reset_user_password("token", "FreshCredential123")

    assert captured["max_age"] == app.config["PASSWORD_RESET_MINUTES"] * 60


def test_admin_routes_require_recent_sign_in(client, app, sample_data, login):
    login("admin@example.com", "AdminPassword123")
    with app.app_context():
        session = UserSession.query.filter(UserSession.revoked_at.is_(None)).one()
        session_id = session.id
        session.second_factor_verified_at = utcnow() - timedelta(minutes=app.config["ADMIN_STEP_UP_MINUTES"] + 1)
        db.session.commit()

    response = client.get("/admin/pending-approvals", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]

    with app.app_context():
        session = db.session.get(UserSession, session_id)
        assert session.revoked_at is not None


def test_admin_post_redirect_does_not_preserve_post_next(client, app, sample_data, login):
    login("admin@example.com", "AdminPassword123")
    with app.app_context():
        session = UserSession.query.filter(UserSession.revoked_at.is_(None)).one()
        session.second_factor_verified_at = utcnow() - timedelta(minutes=app.config["ADMIN_STEP_UP_MINUTES"] + 1)
        db.session.commit()

    response = client.post("/settings/categories", data={"name": "Ops", "type": "Expense", "color": "#123456"}, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
def test_production_password_reset_does_not_fallback_to_outbox(client, app):
    with app.app_context():
        user = User(full_name="Prod User", email="prod@example.com", email_verified=True)
        user.set_password("ProdPassword123")
        db.session.add(user)
        db.session.commit()

    app.config.update(APP_ENV="production", SENDGRID_API_KEY=None, SMTP_HOST=None, SMTP_USERNAME=None, SMTP_PASSWORD=None)
    response = client.post("/forgot-password", data={"email": "prod@example.com"}, follow_redirects=True)

    assert response.status_code == 200
    assert b"Email delivery is not configured for this environment." in response.data
    outbox_dir = Path(app.config["OUTBOX_FOLDER"])
    assert not outbox_dir.exists() or not any(outbox_dir.iterdir())


def test_responses_include_content_security_policy(client):
    response = client.get("/login")
    csp = response.headers["Content-Security-Policy"]
    assert "script-src 'self' 'nonce-" in csp
    assert "object-src 'none'" in csp
