from __future__ import annotations

import smtplib
from email.message import EmailMessage
from pathlib import Path

from email_validator import EmailNotValidError, validate_email
from flask import current_app, g, request, url_for

from app.extensions import db
from app.models.user import User
from app.utils.audit import record_audit
from app.utils.auth import create_session, revoke_session
from app.utils.exceptions import ServiceError
from app.utils.security import generate_token, load_token, validate_password_policy
from app.utils.time import utcnow


def normalize_email(email: str) -> str:
    try:
        return validate_email(email, check_deliverability=False).normalized
    except EmailNotValidError as exc:
        raise ServiceError("Enter a valid email address.") from exc


def _send_email(recipient: str, subject: str, body: str) -> None:
    if current_app.config["SMTP_HOST"]:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = current_app.config["MAIL_FROM"]
        message["To"] = recipient
        message.set_content(body)
        with smtplib.SMTP(current_app.config["SMTP_HOST"], current_app.config["SMTP_PORT"]) as server:
            if current_app.config["SMTP_USE_TLS"]:
                server.starttls()
            if current_app.config["SMTP_USERNAME"]:
                server.login(current_app.config["SMTP_USERNAME"], current_app.config["SMTP_PASSWORD"])
            server.send_message(message)
        return

    outbox = Path(current_app.config["OUTBOX_FOLDER"])
    outbox.mkdir(parents=True, exist_ok=True)
    filename = outbox / f"{utcnow().strftime('%Y%m%d%H%M%S%f')}_{subject.replace(' ', '_').lower()}.txt"
    filename.write_text(f"To: {recipient}\nSubject: {subject}\n\n{body}", encoding="utf-8")


def _verification_token(user: User) -> str:
    return generate_token({"purpose": "verify-email", "user_id": user.id})


def _reset_token(user: User) -> str:
    return generate_token({"purpose": "reset-password", "user_id": user.id})


def send_verification_email(user: User) -> None:
    token = _verification_token(user)
    verification_url = url_for("auth.verify_email", token=token, _external=True)
    _send_email(
        user.email,
        "Verify your Vynfy Ledger account",
        f"Hello {user.full_name},\n\nVerify your email to access Vynfy Ledger:\n{verification_url}\n",
    )


def send_password_reset_email(user: User) -> None:
    token = _reset_token(user)
    reset_url = url_for("auth.reset_password", token=token, _external=True)
    _send_email(
        user.email,
        "Reset your Vynfy Ledger password",
        f"Hello {user.full_name},\n\nReset your password here:\n{reset_url}\n",
    )


def register_user(*, full_name: str, email: str, password: str, role: str = "staff", can_create_revenue: bool = False) -> User:
    normalized_email = normalize_email(email)
    if User.query.filter_by(email=normalized_email).first():
        raise ServiceError("An account with that email already exists.")

    password_errors = validate_password_policy(password)
    if password_errors:
        raise ServiceError(" ".join(password_errors))

    user = User(
        full_name=full_name.strip(),
        email=normalized_email,
        role=role,
        can_create_revenue=can_create_revenue,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    record_audit(user_id=user.id, entity_type="user", entity_id=user.id, action="register", new_values={"email": user.email})
    send_verification_email(user)
    return user


def create_user_by_admin(
    *,
    actor: User,
    full_name: str,
    email: str,
    password: str,
    role: str,
    can_create_revenue: bool,
    email_verified: bool,
    is_active: bool,
) -> User:
    user = register_user(
        full_name=full_name,
        email=email,
        password=password,
        role=role,
        can_create_revenue=can_create_revenue,
    )
    user.email_verified = email_verified
    user.is_active = is_active
    record_audit(
        user_id=actor.id,
        entity_type="user",
        entity_id=user.id,
        action="admin_create_user",
        new_values={"role": role, "is_active": is_active},
    )
    return user


def verify_email_token(token: str) -> User:
    payload = load_token(token, max_age=60 * 60 * 24)
    if payload.get("purpose") != "verify-email":
        raise ServiceError("Verification link is invalid.")
    user = db.session.get(User, payload.get("user_id"))
    if not user:
        raise ServiceError("User not found.")
    user.email_verified = True
    record_audit(user_id=user.id, entity_type="user", entity_id=user.id, action="verify_email")
    return user


def request_password_reset(email: str) -> None:
    normalized_email = normalize_email(email)
    user = User.query.filter_by(email=normalized_email).first()
    if user:
        send_password_reset_email(user)


def reset_user_password(token: str, password: str) -> User:
    payload = load_token(token, max_age=60 * 60 * 4)
    if payload.get("purpose") != "reset-password":
        raise ServiceError("Password reset link is invalid.")
    user = db.session.get(User, payload.get("user_id"))
    if not user:
        raise ServiceError("User not found.")
    password_errors = validate_password_policy(password)
    if password_errors:
        raise ServiceError(" ".join(password_errors))
    user.set_password(password)
    user.failed_login_attempts = 0
    user.locked_until = None
    record_audit(user_id=user.id, entity_type="user", entity_id=user.id, action="password_reset")
    return user


def authenticate_user(*, email: str, password: str) -> str:
    normalized_email = normalize_email(email)
    user = User.query.filter_by(email=normalized_email).first()
    if not user:
        raise ServiceError("Invalid email or password.")

    now = utcnow()
    if user.locked_until and user.locked_until > now:
        record_audit(user_id=user.id, entity_type="auth", entity_id=user.id, action="login_locked")
        raise ServiceError("Account temporarily locked. Try again later.")

    if not user.is_active:
        raise ServiceError("This account is inactive.")

    if not user.check_password(password):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= current_app.config["MAX_FAILED_LOGINS"]:
            from datetime import timedelta

            user.locked_until = now + timedelta(minutes=current_app.config["LOGIN_LOCKOUT_MINUTES"])
            record_audit(user_id=user.id, entity_type="auth", entity_id=user.id, action="lockout")
        record_audit(user_id=user.id, entity_type="auth", entity_id=user.id, action="login_failed")
        raise ServiceError("Invalid email or password.")

    if not user.email_verified:
        send_verification_email(user)
        raise ServiceError("Verify your email before signing in. A fresh link has been sent.")

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    token = create_session(
        user,
        ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
        user_agent=request.user_agent.string,
    )
    g.session_cookie_to_set = token
    record_audit(user_id=user.id, entity_type="auth", entity_id=user.id, action="login")
    return token


def logout_current_user() -> None:
    if getattr(g, "auth_session", None) and getattr(g, "current_user", None):
        revoke_session(g.auth_session)
        record_audit(user_id=g.current_user.id, entity_type="auth", entity_id=g.current_user.id, action="logout")
    g.clear_session_cookie = True
