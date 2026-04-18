from __future__ import annotations

from collections.abc import Callable

from flask import Blueprint, Response, flash, g, redirect, render_template, url_for

from app.auth.forms import AdminUserForm
from app.auth.services import create_user_by_admin
from app.extensions import db
from app.models import Account, Category, PaymentMethod, User
from app.settings.forms import AccountForm, CategoryForm, PaymentMethodForm
from app.settings.services import create_account, create_category, create_payment_method
from app.utils.decorators import admin_required


settings_bp = Blueprint("settings", __name__)


def _submit_settings_change(*, success_message: str, redirect_endpoint: str, action: Callable[[], object]) -> Response | None:
    try:
        action()
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "error")
        return None
    flash(success_message, "success")
    return redirect(url_for(redirect_endpoint))


@settings_bp.route("/settings/categories", methods=["GET", "POST"])
@admin_required
def categories():
    form = CategoryForm()
    if form.validate_on_submit():
        response = _submit_settings_change(
            success_message="Category saved.",
            redirect_endpoint="settings.categories",
            action=lambda: create_category(
                name=form.name.data,
                category_type=form.type.data,
                color=form.color.data,
                description=form.description.data,
                actor=g.current_user,
            ),
        )
        if response:
            return response
    return render_template("settings/categories.html", form=form, categories=Category.query.order_by(Category.name.asc()).all())


@settings_bp.route("/settings/accounts", methods=["GET", "POST"])
@admin_required
def accounts():
    form = AccountForm()
    if form.validate_on_submit():
        response = _submit_settings_change(
            success_message="Account saved.",
            redirect_endpoint="settings.accounts",
            action=lambda: create_account(
                name=form.name.data,
                account_type=form.type.data,
                opening_balance=form.opening_balance.data,
                currency_code=form.currency_code.data,
                actor=g.current_user,
            ),
        )
        if response:
            return response
    return render_template("settings/accounts.html", form=form, accounts=Account.query.order_by(Account.name.asc()).all())


@settings_bp.route("/settings/payment-methods", methods=["GET", "POST"])
@admin_required
def payment_methods():
    form = PaymentMethodForm()
    if form.validate_on_submit():
        response = _submit_settings_change(
            success_message="Payment method saved.",
            redirect_endpoint="settings.payment_methods",
            action=lambda: create_payment_method(name=form.name.data, actor=g.current_user),
        )
        if response:
            return response
    return render_template("settings/payment_methods.html", form=form, methods=PaymentMethod.query.order_by(PaymentMethod.name.asc()).all())


@settings_bp.route("/settings/users", methods=["GET", "POST"])
@admin_required
def users():
    form = AdminUserForm()
    if form.validate_on_submit():
        response = _submit_settings_change(
            success_message="User created.",
            redirect_endpoint="settings.users",
            action=lambda: create_user_by_admin(
                actor=g.current_user,
                full_name=form.full_name.data,
                email=form.email.data,
                password=form.password.data,
                role=form.role.data,
                can_create_revenue=form.can_create_revenue.data,
                email_verified=form.email_verified.data,
                is_active=form.is_active.data,
            ),
        )
        if response:
            return response
    return render_template("settings/users.html", form=form, users=User.query.order_by(User.full_name.asc()).all())
