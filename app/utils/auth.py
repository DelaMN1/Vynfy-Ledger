from __future__ import annotations

from datetime import timedelta

from flask import current_app, g, request

from app.extensions import db
from app.models.session import UserSession
from app.utils.security import generate_session_token, hash_token
from app.utils.time import utcnow


SESSION_COOKIE = "vynfy_session"


def _session_expiry() -> tuple:
    issued_at = utcnow()
    expires_at = issued_at + current_app.config["ACCESS_SESSION_TTL"]
    return issued_at, expires_at


def create_session(user, *, ip_address: str | None, user_agent: str | None, second_factor_at=None, replaced_session: UserSession | None = None) -> str:
    raw_token = generate_session_token()
    issued_at, expires_at = _session_expiry()
    second_factor_verified_at = second_factor_at or issued_at
    session = UserSession(
        user_id=user.id,
        token_hash=hash_token(raw_token),
        issued_at=issued_at,
        expires_at=expires_at,
        second_factor_verified_at=second_factor_verified_at,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.session.add(session)
    db.session.flush()
    if replaced_session:
        replaced_session.revoked_at = issued_at
        replaced_session.replaced_by_token_id = session.id
    g.auth_session = session
    return raw_token


def revoke_session(session: UserSession | None) -> None:
    if session and not session.revoked_at:
        session.revoked_at = utcnow()


def load_user_from_session() -> None:
    g.current_user = None
    g.auth_session = None
    g.session_cookie_to_set = None
    g.clear_session_cookie = False

    raw_token = request.cookies.get(SESSION_COOKIE)
    if not raw_token:
        return

    session = (
        UserSession.query.join(UserSession.user)
        .filter(UserSession.token_hash == hash_token(raw_token), UserSession.revoked_at.is_(None))
        .first()
    )
    if not session or session.expires_at <= utcnow() or not session.user.is_active:
        g.clear_session_cookie = True
        return

    g.current_user = session.user
    g.auth_session = session

    rotate_after = current_app.config["SESSION_ROTATE_AFTER"]
    if utcnow() - session.issued_at >= rotate_after:
        new_token = create_session(
            session.user,
            ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
            user_agent=request.user_agent.string,
            second_factor_at=session.second_factor_verified_at,
            replaced_session=session,
        )
        g.session_cookie_to_set = new_token


def apply_auth_cookie(response):
    if getattr(g, "clear_session_cookie", False):
        response.delete_cookie(
            SESSION_COOKIE,
            secure=current_app.config["SESSION_COOKIE_SECURE"],
            httponly=True,
            samesite=current_app.config["SESSION_COOKIE_SAMESITE"],
        )
        return response

    if getattr(g, "session_cookie_to_set", None):
        expires_at = utcnow() + current_app.config["ACCESS_SESSION_TTL"]
        response.set_cookie(
            SESSION_COOKIE,
            g.session_cookie_to_set,
            max_age=int(current_app.config["ACCESS_SESSION_TTL"].total_seconds()),
            httponly=True,
            secure=current_app.config["SESSION_COOKIE_SECURE"],
            samesite=current_app.config["SESSION_COOKIE_SAMESITE"],
        )
        if g.auth_session:
            g.auth_session.expires_at = expires_at
        db.session.commit()
    return response
