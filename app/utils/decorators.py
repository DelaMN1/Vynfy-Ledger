from __future__ import annotations

from datetime import timedelta
from functools import wraps

from flask import abort, current_app, flash, g, redirect, request, url_for

from app.extensions import db
from app.utils.auth import revoke_session
from app.utils.time import utcnow


def _auth_redirect():
    if request.method in {"GET", "HEAD"}:
        return redirect(url_for("auth.login", next=request.full_path))
    return redirect(url_for("auth.login"))


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not getattr(g, "current_user", None):
            return _auth_redirect()
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not g.current_user.is_admin:
            abort(403)
        if not getattr(g, "auth_session", None):
            abort(403)
        freshness_window = timedelta(minutes=current_app.config["ADMIN_STEP_UP_MINUTES"])
        if g.auth_session.second_factor_verified_at + freshness_window < utcnow():
            revoke_session(g.auth_session)
            db.session.commit()
            g.clear_session_cookie = True
            flash("Admin access requires a recent password sign-in.", "warning")
            return _auth_redirect()
        return view(*args, **kwargs)

    return wrapped
