from __future__ import annotations

from datetime import timedelta

from app.extensions import db
from app.models import User, UserSession
from app.utils.security import generate_token
from app.utils.time import utcnow


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


def test_email_verification_flow(client, app):
    with app.app_context():
        user = User(full_name="Pending User", email="pending@example.com", email_verified=False)
        user.set_password("PendingPassword123")
        db.session.add(user)
        db.session.commit()
        token = generate_token({"purpose": "verify-email", "user_id": user.id})
    response = client.get(f"/verify-email/{token}", follow_redirects=False)
    assert response.status_code == 302
    with app.app_context():
        user = User.query.filter_by(email="pending@example.com").first()
        assert user.email_verified is True


def test_login_logout_and_session_rotation(client, app, sample_data, login):
    response = login("admin@example.com", "AdminPassword123")
    assert response.status_code == 302
    assert "vynfy_session=" in response.headers.get("Set-Cookie", "")

    with app.app_context():
        session = UserSession.query.one()
        session.issued_at = utcnow() - timedelta(minutes=20)
        db.session.commit()

    rotated = client.get("/dashboard")
    assert rotated.status_code == 200
    assert "vynfy_session=" in rotated.headers.get("Set-Cookie", "")

    logout_response = client.post("/logout", follow_redirects=False)
    assert logout_response.status_code == 302
    with app.app_context():
        assert UserSession.query.filter(UserSession.revoked_at.is_(None)).count() == 0


def test_failed_login_locks_account(client, app, sample_data):
    for _ in range(5):
        client.post("/login", data={"email": "staff@example.com", "password": "wrong-password"})
    with app.app_context():
        user = User.query.filter_by(email="staff@example.com").first()
        assert user.locked_until is not None
    response = client.post("/login", data={"email": "staff@example.com", "password": "StaffPassword123"}, follow_redirects=True)
    assert b"temporarily locked" in response.data
