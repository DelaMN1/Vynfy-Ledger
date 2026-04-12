from __future__ import annotations

from flask import Blueprint, flash, g, redirect, render_template, url_for

from app.auth.forms import AdminUserForm
from app.auth.services import create_user_by_admin
from app.extensions import db
from app.models import Account, Category, PaymentMethod, User
from app.settings.forms import AccountForm, CategoryForm, PaymentMethodForm
from app.settings.services import create_account, create_category, create_payment_method
from app.utils.decorators import admin_required


settings_bp = Blueprint("settings", __name__)


@settings_bp.route("/settings/categories", methods=["GET", "POST"])
@admin_required
def categories():
    form = CategoryForm()
    if form.validate_on_submit():
        create_category(name=form.name.data, category_type=form.type.data, color=form.color.data, description=form.description.data, actor=g.current_user)
        db.session.commit()
        flash("Category saved.", "success")
        return redirect(url_for("settings.categories"))
    return render_template("settings/categories.html", form=form, categories=Category.query.order_by(Category.name.asc()).all())


@settings_bp.route("/settings/accounts", methods=["GET", "POST"])
@admin_required
def accounts():
    form = AccountForm()
    if form.validate_on_submit():
        create_account(name=form.name.data, account_type=form.type.data, opening_balance=form.opening_balance.data, currency_code=form.currency_code.data, actor=g.current_user)
        db.session.commit()
        flash("Account saved.", "success")
        return redirect(url_for("settings.accounts"))
    return render_template("settings/accounts.html", form=form, accounts=Account.query.order_by(Account.name.asc()).all())


@settings_bp.route("/settings/payment-methods", methods=["GET", "POST"])
@admin_required
def payment_methods():
    form = PaymentMethodForm()
    if form.validate_on_submit():
        create_payment_method(name=form.name.data, actor=g.current_user)
        db.session.commit()
        flash("Payment method saved.", "success")
        return redirect(url_for("settings.payment_methods"))
    return render_template("settings/payment_methods.html", form=form, methods=PaymentMethod.query.order_by(PaymentMethod.name.asc()).all())


@settings_bp.route("/settings/users", methods=["GET", "POST"])
@admin_required
def users():
    form = AdminUserForm()
    if form.validate_on_submit():
        try:
            create_user_by_admin(
                actor=g.current_user,
                full_name=form.full_name.data,
                email=form.email.data,
                password=form.password.data,
                role=form.role.data,
                can_create_revenue=form.can_create_revenue.data,
                email_verified=form.email_verified.data,
                is_active=form.is_active.data,
            )
            db.session.commit()
            flash("User created.", "success")
            return redirect(url_for("settings.users"))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
    return render_template("settings/users.html", form=form, users=User.query.order_by(User.full_name.asc()).all())
