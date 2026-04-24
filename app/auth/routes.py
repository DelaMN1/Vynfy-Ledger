from __future__ import annotations

from urllib.parse import urlsplit

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, url_for

from app.auth.forms import ForgotPasswordForm, LoginForm, RegisterForm, ResetPasswordForm
from app.auth.services import (
    authenticate_user,
    begin_password_reset,
    logout_current_user,
    register_user,
    reset_user_password,
)
from app.extensions import db, limiter


auth_bp = Blueprint("auth", __name__)
REGISTRATION_DISABLED_MESSAGE = "Self-service registration is unavailable. Ask an admin to create your account."
PASSWORD_RESET_DISABLED_MESSAGE = "Self-service password reset is unavailable. Contact an admin to reset your password."
PASSWORD_RESET_REQUESTED_MESSAGE = (
    "If an active account matches that email, reset instructions will be delivered through your configured recovery channel."
)


def _safe_next_url(raw_value: str | None) -> str:
    if not raw_value:
        return url_for("dashboard.overview")
    target = raw_value.strip()
    parts = urlsplit(target)
    if parts.scheme or parts.netloc or not target.startswith("/") or target.startswith("//"):
        return url_for("dashboard.overview")
    return target


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login():
    if getattr(g, "current_user", None):
        return redirect(url_for("dashboard.overview"))

    form = LoginForm()
    if form.validate_on_submit():
        try:
            authenticate_user(email=form.email.data, password=form.password.data)
            db.session.commit()
            flash("Signed in successfully.", "success")
            return redirect(_safe_next_url(request.args.get("next")))
        except ValueError as exc:
            db.session.commit()
            flash(str(exc), "error")
    return render_template("auth/login.html", form=form)


@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def register():
    if not current_app.config["REGISTRATION_ENABLED"]:
        flash(REGISTRATION_DISABLED_MESSAGE, "warning")
        return redirect(url_for("auth.login"))

    form = RegisterForm()
    if form.validate_on_submit():
        try:
            register_user(full_name=form.full_name.data, email=form.email.data, password=form.password.data)
            db.session.commit()
            flash("Account created. You can sign in now.", "success")
            return redirect(url_for("auth.login"))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
    return render_template("auth/register.html", form=form)


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def forgot_password():
    if not current_app.config["SELF_SERVICE_PASSWORD_RESET_ENABLED"]:
        if request.method == "POST":
            flash(PASSWORD_RESET_DISABLED_MESSAGE, "warning")
            return redirect(url_for("auth.login"))
        return render_template("auth/forgot_password.html", form=None, reset_disabled=True)

    form = ForgotPasswordForm()
    if form.validate_on_submit():
        try:
            begin_password_reset(form.email.data)
            db.session.commit()
            flash(PASSWORD_RESET_REQUESTED_MESSAGE, "info")
            return redirect(url_for("auth.login"))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
    return render_template("auth/forgot_password.html", form=form, reset_disabled=False)


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def reset_password(token: str):
    if not current_app.config["SELF_SERVICE_PASSWORD_RESET_ENABLED"]:
        return render_template("partials/error.html", title="Not found", message="The requested page could not be found."), 404

    form = ResetPasswordForm()
    if form.validate_on_submit():
        try:
            reset_user_password(token, form.password.data)
            db.session.commit()
            flash("Password updated. Sign in with your new password.", "success")
            return redirect(url_for("auth.login"))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
    return render_template("auth/reset_password.html", form=form)


@auth_bp.post("/logout")
def logout():
    logout_current_user()
    db.session.commit()
    flash("Signed out successfully.", "success")
    return redirect(url_for("auth.login"))
