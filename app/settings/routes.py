from __future__ import annotations

from collections.abc import Callable

from flask import Blueprint, Response, abort, flash, g, redirect, render_template, url_for

from app.auth.forms import AdminUserForm
from app.auth.services import create_user_by_admin, update_user_role
from app.extensions import db
from app.models import Account, AccountingMapping, Budget, Category, PaymentMethod, SpendPolicy, User
from app.settings.forms import AccountForm, AccountingMappingForm, BudgetForm, CategoryForm, PaymentMethodForm, SpendPolicyForm, UserRoleForm
from app.settings.services import create_account, create_accounting_mapping, create_budget, create_category, create_payment_method, create_spend_policy
from app.utils.decorators import admin_required
from app.utils.exceptions import ServiceError


settings_bp = Blueprint("settings", __name__)


def _settings_context() -> dict[str, list[object]]:
    return {
        "categories": Category.query.order_by(Category.name.asc()).all(),
        "accounts": Account.query.order_by(Account.name.asc()).all(),
        "methods": PaymentMethod.query.order_by(PaymentMethod.name.asc()).all(),
        "users": User.query.order_by(User.full_name.asc()).all(),
        "budgets": Budget.query.order_by(Budget.name.asc()).all(),
        "policies": SpendPolicy.query.order_by(SpendPolicy.name.asc()).all(),
        "mappings": AccountingMapping.query.order_by(AccountingMapping.name.asc()).all(),
    }


def _assign_finance_rule_choices(form: BudgetForm | SpendPolicyForm | AccountingMappingForm) -> None:
    form.category_id.choices = [(0, "Any category")] + [(item.id, item.name) for item in Category.query.order_by(Category.name.asc()).all()]
    form.account_id.choices = [(0, "Any account")] + [(item.id, item.name) for item in Account.query.order_by(Account.name.asc()).all()]
    if hasattr(form, "payment_method_id"):
        form.payment_method_id.choices = [(0, "Any payment method")] + [(item.id, item.name) for item in PaymentMethod.query.order_by(PaymentMethod.name.asc()).all()]
    if hasattr(form, "owner_id"):
        form.owner_id.choices = [(0, "Unassigned")] + [(item.id, item.full_name) for item in User.query.order_by(User.full_name.asc()).all()]


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
    return render_template("settings/categories.html", form=form, **_settings_context())


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
    return render_template("settings/accounts.html", form=form, **_settings_context())


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
    return render_template("settings/payment_methods.html", form=form, **_settings_context())


@settings_bp.route("/settings/users", methods=["GET", "POST"])
@admin_required
def users():
    form = AdminUserForm()
    user_role_form = UserRoleForm()
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
                is_active=form.is_active.data,
            ),
        )
        if response:
            return response
    return render_template("settings/users.html", form=form, user_role_form=user_role_form, **_settings_context())


@settings_bp.post("/settings/users/<int:user_id>/role")
@admin_required
def update_user_role_action(user_id: int):
    form = UserRoleForm()
    if not form.validate_on_submit():
        flash("Select a valid role.", "error")
        return redirect(url_for("settings.users"))

    user = db.session.get(User, user_id)
    if not user:
        abort(404)

    try:
        update_user_role(actor=g.current_user, user=user, role=form.role.data)
        db.session.commit()
    except ServiceError as exc:
        db.session.rollback()
        flash(str(exc), "error")
    else:
        flash("User role updated.", "success")
    return redirect(url_for("settings.users"))


@settings_bp.route("/settings/budgets", methods=["GET", "POST"])
@admin_required
def budgets():
    form = BudgetForm()
    _assign_finance_rule_choices(form)
    if form.validate_on_submit():
        response = _submit_settings_change(
            success_message="Budget saved.",
            redirect_endpoint="settings.budgets",
            action=lambda: create_budget(
                name=form.name.data,
                transaction_type=form.transaction_type.data or None,
                category_id=form.category_id.data or None,
                account_id=form.account_id.data or None,
                owner_id=form.owner_id.data or None,
                amount=form.amount.data,
                alert_percent=form.alert_percent.data,
                actor=g.current_user,
            ),
        )
        if response:
            return response
    return render_template("settings/budgets.html", form=form, **_settings_context())


@settings_bp.route("/settings/policies", methods=["GET", "POST"])
@admin_required
def policies():
    form = SpendPolicyForm()
    _assign_finance_rule_choices(form)
    if form.validate_on_submit():
        response = _submit_settings_change(
            success_message="Spend policy saved.",
            redirect_endpoint="settings.policies",
            action=lambda: create_spend_policy(
                name=form.name.data,
                transaction_type=form.transaction_type.data or None,
                category_id=form.category_id.data or None,
                account_id=form.account_id.data or None,
                payment_method_id=form.payment_method_id.data or None,
                max_amount=form.max_amount.data,
                require_attachment=form.require_attachment.data,
                require_note=form.require_note.data,
                block_on_over_budget=form.block_on_over_budget.data,
                description=form.description.data,
                actor=g.current_user,
            ),
        )
        if response:
            return response
    return render_template("settings/policies.html", form=form, **_settings_context())


@settings_bp.route("/settings/accounting-mappings", methods=["GET", "POST"])
@admin_required
def accounting_mappings():
    form = AccountingMappingForm()
    _assign_finance_rule_choices(form)
    if form.validate_on_submit():
        response = _submit_settings_change(
            success_message="Accounting mapping saved.",
            redirect_endpoint="settings.accounting_mappings",
            action=lambda: create_accounting_mapping(
                name=form.name.data,
                transaction_type=form.transaction_type.data or None,
                category_id=form.category_id.data or None,
                account_id=form.account_id.data or None,
                payment_method_id=form.payment_method_id.data or None,
                gl_code=form.gl_code.data,
                cost_center=form.cost_center.data,
                project_code=form.project_code.data,
                actor=g.current_user,
            ),
        )
        if response:
            return response
    return render_template("settings/accounting_mappings.html", form=form, **_settings_context())
