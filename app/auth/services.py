from __future__ import annotations

import smtplib
from datetime import timedelta
from email.message import EmailMessage
from html import escape
from pathlib import Path

from email_validator import EmailNotValidError, validate_email
from flask import current_app, g, request, url_for

from app.extensions import db
from app.models.session import LoginChallenge
from app.models.user import User
from app.utils.audit import record_audit
from app.utils.auth import create_session, revoke_session
from app.utils.exceptions import ServiceError
from app.utils.security import consume_dummy_password_check, generate_numeric_code, generate_token, hash_token, load_token, validate_password_policy
from app.utils.time import utcnow


def normalize_email(email: str) -> str:
    try:
        return validate_email(email, check_deliverability=False).normalized
    except EmailNotValidError as exc:
        raise ServiceError("Enter a valid email address.") from exc


def _send_email(recipient: str, subject: str, body: str) -> None:
    outbox = Path(current_app.config["OUTBOX_FOLDER"])
    outbox.mkdir(parents=True, exist_ok=True)

    def write_outbox_copy(reason: str | None = None) -> None:
        filename = outbox / f"{utcnow().strftime('%Y%m%d%H%M%S%f')}_{subject.replace(' ', '_').lower()}.txt"
        prefix = f"[fallback reason] {reason}\n\n" if reason else ""
        filename.write_text(f"{prefix}To: {recipient}\nSubject: {subject}\n\n{body}", encoding="utf-8")
        current_app.logger.info("Email saved to %s", filename)
        current_app.logger.info("Email preview for %s:\n%s", recipient, body)

    if current_app.config["SENDGRID_API_KEY"]:
        try:
            from sendgrid import SendGridAPIClient
            from sendgrid.helpers.mail import Mail

            message = Mail(
                from_email=current_app.config["MAIL_FROM"],
                to_emails=recipient,
                subject=subject,
                html_content=escape(body).replace("\n", "<br>"),
                plain_text_content=body,
            )
            response = SendGridAPIClient(current_app.config["SENDGRID_API_KEY"]).send(message)
            current_app.logger.info("SendGrid email accepted with status %s", response.status_code)
            return
        except Exception as exc:  # SendGrid SDK raises provider-specific exceptions without a narrow stable base type.
            current_app.logger.exception("SendGrid delivery failed; falling back to SMTP/outbox.")
            if not current_app.config["SMTP_HOST"]:
                write_outbox_copy(str(exc))
                return

    if current_app.config["SMTP_HOST"]:
        try:
            message = EmailMessage()
            message["Subject"] = subject
            message["From"] = current_app.config["MAIL_FROM"]
            message["To"] = recipient
            message.set_content(body)
            with smtplib.SMTP(current_app.config["SMTP_HOST"], current_app.config["SMTP_PORT"], timeout=30) as server:
                if current_app.config["SMTP_USE_TLS"]:
                    server.starttls()
                if current_app.config["SMTP_USERNAME"]:
                    server.login(current_app.config["SMTP_USERNAME"], current_app.config["SMTP_PASSWORD"])
                server.send_message(message)
            return
        except (smtplib.SMTPException, OSError) as exc:
            current_app.logger.exception("SMTP delivery failed; falling back to local outbox.")
            write_outbox_copy(str(exc))
            return

    write_outbox_copy()


def _verification_token(user: User) -> str:
    return generate_token({"purpose": "verify-email", "user_id": user.id})


def _reset_token(user: User) -> str:
    return generate_token({"purpose": "reset-password", "user_id": user.id})


def _login_challenge_token(challenge: LoginChallenge) -> str:
    return generate_token({"purpose": "login-challenge", "challenge_id": challenge.id})


def send_verification_email(user: User) -> None:
    token = _verification_token(user)
    verification_url = url_for("auth.verify_email", token=token, _external=True)
    _send_email(
        user.email,
        "Verify your Vynfy Ledger account",
        f"Hello {user.full_name},\n\nVerify your email to access Vynfy Ledger:\n{verification_url}\n",
    )


def send_login_code_email(user: User, challenge: LoginChallenge, code: str) -> None:
    magic_url = url_for("auth.login_magic", token=_login_challenge_token(challenge), _external=True)
    _send_email(
        user.email,
        "Your Vynfy Ledger sign-in code",
        (
            f"Hello {user.full_name},\n\n"
            f"Use this sign-in code to complete your login: {code}\n\n"
            f"Or use this magic link:\n{magic_url}\n\n"
            f"This code expires in {current_app.config['LOGIN_CHALLENGE_MINUTES']} minutes."
        ),
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
        raise ServiceError("Verification link is invalid.")
    user.email_verified = True
    record_audit(user_id=user.id, entity_type="user", entity_id=user.id, action="verify_email")
    return user


def request_password_reset(email: str) -> None:
    normalized_email = normalize_email(email)
    user = User.query.filter_by(email=normalized_email).first()
    if user:
        send_password_reset_email(user)


def reset_user_password(token: str, password: str) -> User:
    payload = load_token(token, max_age=current_app.config["PASSWORD_RESET_MINUTES"] * 60)
    if payload.get("purpose") != "reset-password":
        raise ServiceError("Password reset link is invalid.")
    user = db.session.get(User, payload.get("user_id"))
    if not user:
        raise ServiceError("Password reset link is invalid.")
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
        consume_dummy_password_check(password)
        raise ServiceError("Invalid email or password.")

    now = utcnow()
    if user.locked_until and user.locked_until > now:
        record_audit(user_id=user.id, entity_type="auth", entity_id=user.id, action="login_locked")
        raise ServiceError("Invalid email or password.")

    if not user.is_active:
        raise ServiceError("Invalid email or password.")

    if not user.check_password(password):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= current_app.config["MAX_FAILED_LOGINS"]:
            overage = user.failed_login_attempts - current_app.config["MAX_FAILED_LOGINS"]
            backoff_minutes = min(
                current_app.config["LOGIN_LOCKOUT_BASE_MINUTES"] * (2**overage),
                current_app.config["MAX_LOGIN_LOCKOUT_MINUTES"],
            )
            user.locked_until = now + timedelta(minutes=backoff_minutes)
            record_audit(
                user_id=user.id,
                entity_type="auth",
                entity_id=user.id,
                action="lockout",
                new_values={"failed_attempts": user.failed_login_attempts, "locked_until": user.locked_until.isoformat()},
            )
        record_audit(user_id=user.id, entity_type="auth", entity_id=user.id, action="login_failed")
        raise ServiceError("Invalid email or password.")

    if not user.email_verified:
        send_verification_email(user)
        raise ServiceError("Verify your email before signing in. A fresh link has been sent.")

    return start_login_challenge(user)


def _get_active_challenge(challenge_id: int) -> LoginChallenge:
    challenge = db.session.get(LoginChallenge, challenge_id)
    if not challenge:
        raise ServiceError("Your sign-in session is missing. Start again.")
    if challenge.consumed_at:
        raise ServiceError("This sign-in code has already been used. Start again.")
    if challenge.expires_at <= utcnow():
        raise ServiceError("This sign-in code has expired. Start again.")
    return challenge


def start_login_challenge(user: User) -> LoginChallenge:
    now = utcnow()
    LoginChallenge.query.filter(
        LoginChallenge.user_id == user.id,
        LoginChallenge.consumed_at.is_(None),
        LoginChallenge.expires_at > now,
    ).update({"consumed_at": now})
    code = generate_numeric_code()
    challenge = LoginChallenge(
        user_id=user.id,
        code_hash=hash_token(code),
        expires_at=now + timedelta(minutes=current_app.config["LOGIN_CHALLENGE_MINUTES"]),
        max_attempts=current_app.config["LOGIN_CHALLENGE_MAX_ATTEMPTS"],
        ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
        user_agent=request.user_agent.string,
    )
    db.session.add(challenge)
    db.session.flush()
    send_login_code_email(user, challenge, code)
    record_audit(user_id=user.id, entity_type="auth", entity_id=challenge.id, action="login_challenge_sent")
    return challenge


def resend_login_challenge(challenge_id: int) -> LoginChallenge:
    challenge = _get_active_challenge(challenge_id)
    challenge.consumed_at = utcnow()
    return start_login_challenge(challenge.user)


def complete_login_challenge(challenge: LoginChallenge) -> str:
    user = challenge.user
    second_factor_at = utcnow()
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = second_factor_at
    challenge.consumed_at = second_factor_at
    token = create_session(
        user,
        ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
        user_agent=request.user_agent.string,
        second_factor_at=second_factor_at,
    )
    g.session_cookie_to_set = token
    record_audit(user_id=user.id, entity_type="auth", entity_id=challenge.id, action="login")
    return token


def verify_login_code(*, challenge_id: int, code: str) -> str:
    challenge = _get_active_challenge(challenge_id)
    if challenge.attempt_count >= challenge.max_attempts:
        challenge.consumed_at = utcnow()
        raise ServiceError("Too many invalid code attempts. Start again.")
    if hash_token(code.strip()) != challenge.code_hash:
        challenge.attempt_count += 1
        record_audit(user_id=challenge.user_id, entity_type="auth", entity_id=challenge.id, action="login_code_failed")
        raise ServiceError("Invalid sign-in code.")
    return complete_login_challenge(challenge)


def complete_login_magic_token(token: str) -> str:
    payload = load_token(token, max_age=current_app.config["LOGIN_CHALLENGE_MINUTES"] * 60)
    if payload.get("purpose") != "login-challenge":
        raise ServiceError("Magic link is invalid.")
    challenge = _get_active_challenge(int(payload.get("challenge_id")))
    return complete_login_challenge(challenge)


def logout_current_user() -> None:
    if getattr(g, "auth_session", None) and getattr(g, "current_user", None):
        revoke_session(g.auth_session)
        record_audit(user_id=g.current_user.id, entity_type="auth", entity_id=g.current_user.id, action="logout")
    g.clear_session_cookie = True
