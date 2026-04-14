from __future__ import annotations

from urllib.parse import urlsplit

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, session, url_for

from app.auth.forms import (
    ForgotPasswordForm,
    LoginCodeForm,
    LoginForm,
    RegisterForm,
    ResendLoginCodeForm,
    ResetPasswordForm,
    ResendVerificationForm,
)
from app.auth.services import (
    authenticate_user,
    complete_login_magic_token,
    logout_current_user,
    register_user,
    resend_login_challenge,
    request_password_reset,
    reset_user_password,
    send_verification_email,
    verify_login_code,
    verify_email_token,
)
from app.extensions import db, limiter
from app.models.session import LoginChallenge
from app.models.user import User
from app.utils.time import utcnow


auth_bp = Blueprint("auth", __name__)
PENDING_LOGIN_KEY = "pending_login_challenge_id"
PENDING_NEXT_KEY = "pending_login_next"


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
    resend_form = ResendVerificationForm(prefix="resend")
    if form.validate_on_submit():
        try:
            challenge = authenticate_user(email=form.email.data, password=form.password.data)
            db.session.commit()
            session[PENDING_LOGIN_KEY] = challenge.id
            session[PENDING_NEXT_KEY] = _safe_next_url(request.args.get("next"))
            flash(f"We sent a sign-in code to your email.{_delivery_hint()}", "success")
            return redirect(url_for("auth.verify_login"))
        except ValueError as exc:
            db.session.commit()
            flash(f"{exc}{_delivery_hint() if 'fresh link has been sent' in str(exc) else ''}", "error")
    return render_template("auth/login.html", form=form, resend_form=resend_form)


@auth_bp.route("/login/verify", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def verify_login():
    challenge_id = session.get(PENDING_LOGIN_KEY)
    if not challenge_id:
        flash("Start your sign-in again.", "warning")
        return redirect(url_for("auth.login"))

    challenge = db.session.get(LoginChallenge, challenge_id)
    if not challenge or challenge.consumed_at or challenge.expires_at <= utcnow():
        session.pop(PENDING_LOGIN_KEY, None)
        session.pop(PENDING_NEXT_KEY, None)
        flash("Your sign-in session is no longer valid. Start again.", "warning")
        return redirect(url_for("auth.login"))

    form = LoginCodeForm()
    resend_form = ResendLoginCodeForm(prefix="login_resend")
    if form.validate_on_submit():
        try:
            verify_login_code(challenge_id=challenge_id, code=form.code.data)
            db.session.commit()
            next_url = session.pop(PENDING_NEXT_KEY, url_for("dashboard.overview"))
            session.pop(PENDING_LOGIN_KEY, None)
            flash("Signed in successfully.", "success")
            return redirect(next_url)
        except ValueError as exc:
            db.session.commit()
            flash(str(exc), "error")
    return render_template("auth/verify_login.html", form=form, resend_form=resend_form, challenge=challenge)


@auth_bp.post("/login/verify/resend")
@limiter.limit("5 per minute")
def resend_login():
    challenge_id = session.get(PENDING_LOGIN_KEY)
    if not challenge_id:
        flash("Start your sign-in again.", "warning")
        return redirect(url_for("auth.login"))
    form = ResendLoginCodeForm(prefix="login_resend")
    if form.validate_on_submit():
        try:
            challenge = resend_login_challenge(challenge_id)
            db.session.commit()
            session[PENDING_LOGIN_KEY] = challenge.id
            flash(f"A fresh sign-in code has been sent.{_delivery_hint()}", "success")
        except ValueError as exc:
            db.session.rollback()
            session.pop(PENDING_LOGIN_KEY, None)
            session.pop(PENDING_NEXT_KEY, None)
            flash(str(exc), "error")
            return redirect(url_for("auth.login"))
    return redirect(url_for("auth.verify_login"))


@auth_bp.get("/login/magic/<token>")
@limiter.limit("20 per hour")
def login_magic(token: str):
    try:
        complete_login_magic_token(token)
        db.session.commit()
        next_url = session.pop(PENDING_NEXT_KEY, url_for("dashboard.overview"))
        session.pop(PENDING_LOGIN_KEY, None)
        flash("Signed in successfully.", "success")
        return redirect(next_url)
    except ValueError as exc:
        db.session.rollback()
        session.pop(PENDING_LOGIN_KEY, None)
        session.pop(PENDING_NEXT_KEY, None)
        flash(str(exc), "error")
        return redirect(url_for("auth.login"))


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
        request_password_reset(form.email.data)
        db.session.commit()
        flash(f"If that email exists, a reset link has been sent.{_delivery_hint()}", "success")
        return redirect(url_for("auth.login"))
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
    session.pop(PENDING_LOGIN_KEY, None)
    session.pop(PENDING_NEXT_KEY, None)
    db.session.commit()
    flash("Signed out successfully.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.post("/resend-verification")
@limiter.limit("5 per minute")
def resend_verification():
    form = ResendVerificationForm(prefix="resend")
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower()).first()
        if user and not user.email_verified:
            send_verification_email(user)
            db.session.commit()
    flash(f"If the account exists and is pending verification, a fresh link has been sent.{_delivery_hint()}", "success")
    return redirect(url_for("auth.login"))
