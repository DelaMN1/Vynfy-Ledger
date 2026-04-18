from __future__ import annotations

from flask import Blueprint, Response, flash, g, redirect, render_template, request, url_for

from app.extensions import db
from app.transactions.forms import DeleteDraftForm, ExpenseActionForm, ExpenseForm, RevenueForm, SettlementForm, TransactionFilterForm
from app.transactions.services import (
    approve_expense,
    assign_filter_choices,
    assign_form_choices,
    create_transaction_from_form,
    export_transactions_csv,
    get_transaction_or_404,
    list_transactions,
    mark_expense_paid,
    mark_revenue_received,
    reject_expense,
    return_expense_for_edit,
    soft_delete_draft,
    submit_expense,
    update_transaction_from_form,
)
from app.utils.decorators import admin_required, login_required
from app.utils.enums import TransactionType
from app.utils.types import TransactionFilters


transactions_bp = Blueprint("transactions", __name__)


def _filters() -> TransactionFilters:
    return TransactionFilters(
        q=request.args.get("q") or None,
        status=request.args.get("status") or None,
        category_id=request.args.get("category_id", type=int) or None,
        account_id=request.args.get("account_id", type=int) or None,
        owner_id=request.args.get("owner_id", type=int) or None,
    )


def _render_list(transaction_type: str | None = None) -> str:
    form = TransactionFilterForm(formdata=request.args)
    assign_filter_choices(form, user=g.current_user, transaction_type=transaction_type)
    pagination = list_transactions(user=g.current_user, transaction_type=transaction_type, filters=_filters())
    page_title = "Transactions" if transaction_type is None else ("Revenue" if transaction_type == TransactionType.REVENUE.value else "Expenses")
    return render_template("transactions/list.html", page_title=page_title, pagination=pagination, filter_form=form, transaction_type=transaction_type)


@transactions_bp.get("/revenue")
@login_required
def revenue_list():
    return _render_list(TransactionType.REVENUE.value)


@transactions_bp.route("/revenue/new", methods=["GET", "POST"])
@login_required
def revenue_new():
    if not (g.current_user.is_admin or g.current_user.can_create_revenue):
        flash("You do not have permission to create revenue entries.", "error")
        return redirect(url_for("transactions.revenue_list"))
    form = RevenueForm()
    assign_form_choices(form, TransactionType.REVENUE.value)
    if form.validate_on_submit():
        try:
            item = create_transaction_from_form(form=form, transaction_type=TransactionType.REVENUE.value, actor=g.current_user)
            db.session.commit()
            flash("Revenue entry saved.", "success")
            return redirect(url_for("transactions.revenue_detail", transaction_id=item.id))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
    return render_template("transactions/form.html", form=form, transaction=None, page_title="New Revenue", transaction_type=TransactionType.REVENUE.value)


@transactions_bp.get("/revenue/<int:transaction_id>")
@login_required
def revenue_detail(transaction_id: int):
    transaction = get_transaction_or_404(transaction_id, user=g.current_user, transaction_type=TransactionType.REVENUE.value)
    return render_template("transactions/detail.html", transaction=transaction, action_form=None, settlement_form=SettlementForm(), delete_form=DeleteDraftForm())


@transactions_bp.route("/revenue/<int:transaction_id>/edit", methods=["GET", "POST"])
@login_required
def revenue_edit(transaction_id: int):
    transaction = get_transaction_or_404(transaction_id, user=g.current_user, transaction_type=TransactionType.REVENUE.value)
    form = RevenueForm(obj=transaction)
    assign_form_choices(form, TransactionType.REVENUE.value)
    if form.validate_on_submit():
        try:
            update_transaction_from_form(transaction=transaction, form=form, actor=g.current_user)
            db.session.commit()
            flash("Revenue entry updated.", "success")
            return redirect(url_for("transactions.revenue_detail", transaction_id=transaction.id))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
    return render_template("transactions/form.html", form=form, transaction=transaction, page_title="Edit Revenue", transaction_type=TransactionType.REVENUE.value)


@transactions_bp.post("/revenue/<int:transaction_id>/mark-received")
@login_required
def revenue_mark_received(transaction_id: int):
    transaction = get_transaction_or_404(transaction_id, user=g.current_user, transaction_type=TransactionType.REVENUE.value)
    form = SettlementForm()
    if form.validate_on_submit():
        try:
            mark_revenue_received(transaction, g.current_user, form.amount.data, form.settled_date.data)
            db.session.commit()
            flash("Revenue settlement updated.", "success")
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
    return redirect(url_for("transactions.revenue_detail", transaction_id=transaction.id))


@transactions_bp.get("/expenses")
@login_required
def expense_list():
    return _render_list(TransactionType.EXPENSE.value)


@transactions_bp.route("/expenses/new", methods=["GET", "POST"])
@login_required
def expense_new():
    form = ExpenseForm()
    assign_form_choices(form, TransactionType.EXPENSE.value)
    if form.validate_on_submit():
        try:
            item = create_transaction_from_form(form=form, transaction_type=TransactionType.EXPENSE.value, actor=g.current_user)
            db.session.commit()
            flash("Expense saved.", "success")
            return redirect(url_for("transactions.expense_detail", transaction_id=item.id))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
    return render_template("transactions/form.html", form=form, transaction=None, page_title="New Expense", transaction_type=TransactionType.EXPENSE.value)


@transactions_bp.get("/expenses/<int:transaction_id>")
@login_required
def expense_detail(transaction_id: int):
    transaction = get_transaction_or_404(transaction_id, user=g.current_user, transaction_type=TransactionType.EXPENSE.value)
    return render_template("transactions/detail.html", transaction=transaction, action_form=ExpenseActionForm(), settlement_form=SettlementForm(), delete_form=DeleteDraftForm())


@transactions_bp.route("/expenses/<int:transaction_id>/edit", methods=["GET", "POST"])
@login_required
def expense_edit(transaction_id: int):
    transaction = get_transaction_or_404(transaction_id, user=g.current_user, transaction_type=TransactionType.EXPENSE.value)
    form = ExpenseForm(obj=transaction)
    assign_form_choices(form, TransactionType.EXPENSE.value)
    if form.validate_on_submit():
        try:
            update_transaction_from_form(transaction=transaction, form=form, actor=g.current_user)
            db.session.commit()
            flash("Expense updated.", "success")
            return redirect(url_for("transactions.expense_detail", transaction_id=transaction.id))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
    return render_template("transactions/form.html", form=form, transaction=transaction, page_title="Edit Expense", transaction_type=TransactionType.EXPENSE.value)


@transactions_bp.post("/expenses/<int:transaction_id>/submit")
@login_required
def expense_submit(transaction_id: int):
    transaction = get_transaction_or_404(transaction_id, user=g.current_user, transaction_type=TransactionType.EXPENSE.value)
    try:
        submit_expense(transaction, g.current_user)
        db.session.commit()
        flash("Expense submitted for approval.", "success")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "error")
    return redirect(url_for("transactions.expense_detail", transaction_id=transaction.id))


@transactions_bp.post("/expenses/<int:transaction_id>/approve")
@admin_required
def expense_approve(transaction_id: int):
    transaction = get_transaction_or_404(transaction_id, user=g.current_user, transaction_type=TransactionType.EXPENSE.value)
    try:
        approve_expense(transaction, g.current_user)
        db.session.commit()
        flash("Expense approved.", "success")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "error")
    return redirect(url_for("transactions.expense_detail", transaction_id=transaction.id))


@transactions_bp.post("/expenses/<int:transaction_id>/reject")
@admin_required
def expense_reject(transaction_id: int):
    transaction = get_transaction_or_404(transaction_id, user=g.current_user, transaction_type=TransactionType.EXPENSE.value)
    form = ExpenseActionForm()
    if form.validate_on_submit():
        try:
            reject_expense(transaction, g.current_user, form.note.data or "")
            db.session.commit()
            flash("Expense rejected.", "success")
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
    return redirect(url_for("transactions.expense_detail", transaction_id=transaction.id))


@transactions_bp.post("/expenses/<int:transaction_id>/return")
@admin_required
def expense_return(transaction_id: int):
    transaction = get_transaction_or_404(transaction_id, user=g.current_user, transaction_type=TransactionType.EXPENSE.value)
    form = ExpenseActionForm()
    if form.validate_on_submit():
        try:
            return_expense_for_edit(transaction, g.current_user, form.note.data or "")
            db.session.commit()
            flash("Expense returned for edit.", "success")
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
    return redirect(url_for("transactions.expense_detail", transaction_id=transaction.id))


@transactions_bp.post("/expenses/<int:transaction_id>/mark-paid")
@admin_required
def expense_mark_paid(transaction_id: int):
    transaction = get_transaction_or_404(transaction_id, user=g.current_user, transaction_type=TransactionType.EXPENSE.value)
    form = SettlementForm()
    if form.validate_on_submit():
        try:
            mark_expense_paid(transaction, g.current_user, form.settled_date.data)
            db.session.commit()
            flash("Expense marked paid.", "success")
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
    return redirect(url_for("transactions.expense_detail", transaction_id=transaction.id))


@transactions_bp.get("/transactions")
@login_required
def transactions_list():
    return _render_list()


@transactions_bp.get("/transactions/<int:transaction_id>")
@login_required
def transaction_detail(transaction_id: int):
    transaction = get_transaction_or_404(transaction_id, user=g.current_user)
    if transaction.transaction_type == TransactionType.REVENUE.value:
        return redirect(url_for("transactions.revenue_detail", transaction_id=transaction.id))
    return redirect(url_for("transactions.expense_detail", transaction_id=transaction.id))


@transactions_bp.post("/transactions/<int:transaction_id>/delete")
@login_required
def transaction_delete(transaction_id: int):
    transaction = get_transaction_or_404(transaction_id, user=g.current_user)
    form = DeleteDraftForm()
    if form.validate_on_submit():
        try:
            soft_delete_draft(transaction, g.current_user)
            db.session.commit()
            flash("Draft deleted.", "success")
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
    return redirect(url_for("transactions.transactions_list"))


@transactions_bp.get("/transactions/export/csv")
@login_required
def transactions_export():
    content = export_transactions_csv(user=g.current_user, transaction_type=request.args.get("type"), filters=_filters())
    return Response(
        content,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=transactions.csv"},
    )
