from __future__ import annotations

from datetime import timedelta

from email_validator import EmailNotValidError, validate_email
from flask import current_app, g
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.session import UserSession
from app.models.user import User
from app.utils.audit import record_audit
from app.utils.auth import create_session, revoke_session
from app.utils.enums import Role
from app.utils.exceptions import ServiceError
from app.utils.security import (
    consume_dummy_password_check,
    generate_token,
    get_request_ip,
    get_request_user_agent,
    load_token,
    validate_password_policy,
)
from app.utils.time import ensure_utc, utcnow


def normalize_email(email: str) -> str:
    try:
        return validate_email(email, check_deliverability=False).normalized
    except EmailNotValidError as exc:
        raise ServiceError("Enter a valid email address.") from exc


def _build_user(
    *,
    full_name: str,
    email: str,
    password: str,
    role: str,
    can_create_revenue: bool,
    can_create_expense: bool,
    is_active: bool,
    hide_existing_account_errors: bool = False,
) -> User:
    normalized_email = normalize_email(email)

    if User.query.filter_by(email=normalized_email).first():
        if hide_existing_account_errors:
            raise ServiceError("Registration could not be completed.")
        raise ServiceError("An account with that email already exists.")

    password_errors = validate_password_policy(password)

    if password_errors:
        raise ServiceError(" ".join(password_errors))

    user = User(
        full_name=full_name.strip(),
        email=normalized_email,
        role=role,
        can_create_revenue=can_create_revenue,
        can_create_expense=can_create_expense,
        email_verified=True,
        is_active=is_active,
    )

    user.set_password(password)

    db.session.add(user)

    try:
        db.session.flush()
    except IntegrityError as exc:
        if hide_existing_account_errors:
            raise ServiceError("Registration could not be completed.") from exc

        raise ServiceError("An account with that email already exists.") from exc

    return user

def register_user(
    *,
    full_name: str,
    email: str,
    password: str,
    role: str = "staff",
    can_create_revenue: bool = False,
    can_create_expense: bool = False,
) -> User:
    user = _build_user(
        full_name=full_name,
        email=email,
        password=password,
        role=role,
        can_create_revenue=can_create_revenue,
        can_create_expense=can_create_expense,
        is_active=True,
        hide_existing_account_errors=True,
    )

    record_audit(
        user_id=user.id,
        entity_type="user",
        entity_id=user.id,
        action="register",
        new_values={"email": user.email},
    )

    return user


def bootstrap_admin_user(*, full_name: str, email: str, password: str) -> User:
    from app.setup.services import invalidate_setup_status_cache

    if User.query.filter_by(role=Role.ADMIN.value, is_active=True).first():
        raise ServiceError("Bootstrap setup is no longer available.")

    user = _build_user(
        full_name=full_name,
        email=email,
        password=password,
        role=Role.ADMIN.value,
        can_create_revenue=True,
        can_create_expense=True,
        is_active=True,
    )

    record_audit(
        user_id=user.id,
        entity_type="user",
        entity_id=user.id,
        action="bootstrap_create_admin",
        new_values={"email": user.email, "role": user.role},
    )
    invalidate_setup_status_cache()

    return user


def create_user_by_admin(
    *,
    actor: User,
    full_name: str,
    email: str,
    password: str,
    role: str,
    can_create_revenue: bool,
    can_create_expense: bool,
    is_active: bool,
) -> User:
    from app.setup.services import invalidate_setup_status_cache

    user = _build_user(
        full_name=full_name,
        email=email,
        password=password,
        role=role,
        can_create_revenue=can_create_revenue,
        can_create_expense=can_create_expense,
        is_active=is_active,
    )

    record_audit(
        user_id=actor.id,
        entity_type="user",
        entity_id=user.id,
        action="admin_create_user",
        new_values={
            "role": role,
            "is_active": is_active,
        },
    )
    invalidate_setup_status_cache()

    return user


def update_user_role(*, actor: User, user: User, role: str) -> User:
    from app.setup.services import invalidate_setup_status_cache

    if not actor.is_admin:
        raise ServiceError("Only admins can update user roles.")

    if role not in {Role.ADMIN.value, Role.STAFF.value}:
        raise ServiceError("Select a valid role.")

    if user.id == actor.id and role != Role.ADMIN.value:
        raise ServiceError("You cannot remove your own admin access.")

    if (
        user.role == Role.ADMIN.value
        and role != Role.ADMIN.value
        and user.is_active
    ):
        active_admin_count = User.query.filter_by(
            role=Role.ADMIN.value,
            is_active=True,
        ).count()

        if active_admin_count <= 1:
            raise ServiceError("At least one active admin account is required.")

    if user.role == role:
        return user

    previous_role = user.role
    user.role = role

    record_audit(
        user_id=actor.id,
        entity_type="user",
        entity_id=user.id,
        action="admin_update_user_role",
        old_values={"role": previous_role},
        new_values={"role": role},
    )
    invalidate_setup_status_cache()

    return user


def _reset_payload(user: User) -> dict[str, str | int]:
    return {
        "purpose": "reset-password",
        "user_id": user.id,
        "password_changed_at": user.password_changed_at.isoformat(),
    }


def begin_password_reset(email: str) -> str:
    normalized_email = normalize_email(email)
    user = User.query.filter_by(email=normalized_email).first()

    if not user or not user.is_active:
        return ""

    return generate_token(_reset_payload(user))


def reset_user_password(token: str, password: str) -> User:
    payload = load_token(
        token,
        max_age=current_app.config["PASSWORD_RESET_MINUTES"] * 60,
    )

    if payload.get("purpose") != "reset-password":
        raise ServiceError("Password reset link is invalid.")

    user = db.session.get(User, payload.get("user_id"))

    if not user:
        raise ServiceError("Password reset link is invalid.")

    if user.password_changed_at.isoformat() != payload.get("password_changed_at"):
        raise ServiceError("Password reset link is invalid.")

    password_errors = validate_password_policy(password)

    if password_errors:
        raise ServiceError(" ".join(password_errors))

    user.set_password(password)
    user.failed_login_attempts = 0
    user.locked_until = None

    now = utcnow()

    UserSession.query.filter(
        UserSession.user_id == user.id,
        UserSession.revoked_at.is_(None),
    ).update({"revoked_at": now})

    record_audit(
        user_id=user.id,
        entity_type="user",
        entity_id=user.id,
        action="password_reset",
    )

    return user


def complete_password_login(user: User) -> str:
    authenticated_at = utcnow()

    UserSession.query.filter(
        UserSession.user_id == user.id,
        UserSession.revoked_at.is_(None),
    ).update({"revoked_at": authenticated_at})

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = authenticated_at

    token = create_session(
        user,
        ip_address=get_request_ip(),
        user_agent=get_request_user_agent(),
        authenticated_at=authenticated_at,
    )

    g.session_cookie_to_set = token

    record_audit(
        user_id=user.id,
        entity_type="auth",
        entity_id=user.id,
        action="login",
    )

    return token


def authenticate_user(*, email: str, password: str) -> str:
    normalized_email = normalize_email(email)

    user = User.query.filter_by(email=normalized_email).first()

    if not user:
        consume_dummy_password_check(password)
        raise ServiceError("Invalid email or password.")

    now = utcnow()

    if user.locked_until and ensure_utc(user.locked_until) > now:
        record_audit(
            user_id=user.id,
            entity_type="auth",
            entity_id=user.id,
            action="login_locked",
        )

        raise ServiceError("Invalid email or password.")

    if not user.is_active:
        raise ServiceError("Invalid email or password.")

    if not user.check_password(password):
        user.failed_login_attempts += 1

        if user.failed_login_attempts >= current_app.config["MAX_FAILED_LOGINS"]:
            overage = (
                user.failed_login_attempts
                - current_app.config["MAX_FAILED_LOGINS"]
            )

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
                new_values={
                    "failed_attempts": user.failed_login_attempts,
                    "locked_until": user.locked_until.isoformat(),
                },
            )

        record_audit(
            user_id=user.id,
            entity_type="auth",
            entity_id=user.id,
            action="login_failed",
        )

        raise ServiceError("Invalid email or password.")

    return complete_password_login(user)


def logout_current_user() -> None:
    if getattr(g, "auth_session", None) and getattr(g, "current_user", None):
        revoke_session(g.auth_session)

        record_audit(
            user_id=g.current_user.id,
            entity_type="auth",
            entity_id=g.current_user.id,
            action="logout",
        )

    g.clear_session_cookie = True
