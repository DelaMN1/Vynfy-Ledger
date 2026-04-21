from __future__ import annotations

from urllib.parse import urlsplit

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, url_for

from app.auth.forms import ForgotPasswordForm, LoginForm, RegisterForm, ResetPasswordForm, ResendVerificationForm
from app.auth.services import (
    authenticate_user,
    logout_current_user,
    register_user,
    request_password_reset,
    reset_user_password,
    send_verification_email,
    verify_email_token,
)
from app.extensions import db, limiter
from app.models.user import User


auth_bp = Blueprint("auth", __name__)


def _safe_next_url(raw_value: str | None) -> str:
    if not raw_value:
        return url_for("dashboard.overview")
    target = raw_value.strip()
    parts = urlsplit(target)
    if parts.scheme or parts.netloc or not target.startswith("/") or target.startswith("//"):
        return url_for("dashboard.overview")
    return target


def _delivery_hint() -> str:
    if current_app.config["SENDGRID_API_KEY"] or current_app.config["SMTP_HOST"]:
        return ""
    return " Development mode: open instance/outbox to view the email link."


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
            flash(f"{exc}{_delivery_hint() if 'fresh link has been sent' in str(exc) else ''}", "error")
    return render_template("auth/login.html", form=form)


@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def register():
    if not current_app.config["REGISTRATION_ENABLED"]:
        flash("Registration is disabled. Ask an admin to create your account.", "warning")
        return redirect(url_for("auth.login"))

    form = RegisterForm()
    if form.validate_on_submit():
        try:
            register_user(full_name=form.full_name.data, email=form.email.data, password=form.password.data)
            db.session.commit()
            flash(f"Account created. Check your email for the verification link.{_delivery_hint()}", "success")
            return redirect(url_for("auth.login"))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
    return render_template("auth/register.html", form=form)


@auth_bp.get("/verify-email/<token>")
def verify_email(token: str):
    try:
        verify_email_token(token)
        db.session.commit()
        flash("Email verified. You can sign in now.", "success")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "error")
    return redirect(url_for("auth.login"))


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def forgot_password():
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        try:
            request_password_reset(form.email.data)
            db.session.commit()
            flash(f"If that email exists, a reset link has been sent.{_delivery_hint()}", "success")
            return redirect(url_for("auth.login"))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
    return render_template("auth/forgot_password.html", form=form)


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def reset_password(token: str):
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


@auth_bp.post("/resend-verification")
@limiter.limit("5 per minute")
def resend_verification():
    form = ResendVerificationForm(prefix="resend")
    if form.validate_on_submit():
        try:
            user = User.query.filter_by(email=form.email.data.lower()).first()
            if user and not user.email_verified:
                send_verification_email(user)
                db.session.commit()
            flash(f"If the account exists and is pending verification, a fresh link has been sent.{_delivery_hint()}", "success")
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
    return redirect(url_for("auth.login"))
