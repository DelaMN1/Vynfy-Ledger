from __future__ import annotations

from datetime import date, timedelta

from flask import Blueprint, Response, flash, g, redirect, render_template, request, url_for

from app.extensions import db, limiter
from app.transactions.forms import (
    DeleteDraftForm,
    ExpenseActionForm,
    ExpenseEntryForm,
    ExpenseForm,
    HistoryFilterForm,
    RevenueEntryForm,
    RevenueForm,
    SettlementForm,
    TransactionCommentForm,
    TransactionFilterForm,
)
from app.transactions.services import (
    add_transaction_comment,
    apply_filters,
    approve_expense,
    assign_filter_choices,
    assign_form_choices,
    assign_simple_entry_choices,
    can_edit_transaction,
    create_transaction_from_form,
    create_simple_expense,
    create_simple_revenue,
    expense_action_state,
    export_transactions_csv,
    get_transaction_or_404,
    list_transactions,
    mark_expense_paid,
    mark_revenue_received,
    reject_expense,
    return_expense_for_edit,
    soft_delete_draft,
    submit_expense,
    transaction_exception_messages,
    update_transaction_from_form,
    visible_transactions_query,
)
from app.setup.services import ensure_entry_setup, missing_setup_message, setup_status
from app.utils.decorators import admin_required, login_required
from app.utils.enums import TransactionType
from app.utils.types import TransactionFilters


transactions_bp = Blueprint("transactions", __name__)


def _history_period() -> str:
    period = request.args.get("period", "month")
    return period if period in {"week", "month", "year"} else "month"


def _history_type() -> str | None:
    transaction_type = request.args.get("transaction_type") or request.args.get("type")
    return transaction_type if transaction_type in {TransactionType.REVENUE.value, TransactionType.EXPENSE.value} else None


def _period_bounds(period: str) -> tuple[date, date]:
    today = date.today()
    if period == "week":
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        return start, end
    if period == "year":
        return today.replace(month=1, day=1), today.replace(month=12, day=31)
    month_start = today.replace(day=1)
    if today.month == 12:
        next_month = date(today.year + 1, 1, 1)
    else:
        next_month = date(today.year, today.month + 1, 1)
    return month_start, next_month - timedelta(days=1)


def _history_filters() -> TransactionFilters:
    start_date, end_date = _period_bounds(_history_period())
    return TransactionFilters(
        q=request.args.get("q") or None,
        status=request.args.get("status") or None,
        start_date=start_date,
        end_date=end_date,
    )


def _filters() -> TransactionFilters:
    return TransactionFilters(
        q=request.args.get("q") or None,
        status=request.args.get("status") or None,
        category_id=request.args.get("category_id", type=int) or None,
        account_id=request.args.get("account_id", type=int) or None,
        owner_id=request.args.get("owner_id", type=int) or None,
        start_date=request.args.get("start_date", type=lambda value: date.fromisoformat(value) if value else None),
        end_date=request.args.get("end_date", type=lambda value: date.fromisoformat(value) if value else None),
    )


def _render_history() -> str:
    form = HistoryFilterForm(formdata=request.args)
    if not form.period.data:
        form.period.data = _history_period()
    selected_type = _history_type()
    form.transaction_type.data = selected_type or ""
    filters = _history_filters()
    pagination = list_transactions(user=g.current_user, transaction_type=selected_type, filters=filters)
    empty_state = None
    if not pagination.items:
        setup_state = setup_status()
        if not setup_state["is_ready_for_basic_entry"]:
            empty_state = {
                "title": "Finish setup before relying on history",
                "body": "Baseline categories, accounts, or payment methods are still missing, so this workspace is not fully operational yet.",
                "primary_label": "Open setup",
                "primary_url": url_for("setup.overview"),
                "secondary_label": None,
                "secondary_url": None,
            }
        else:
            base_query = visible_transactions_query(g.current_user, selected_type)
            total_records = base_query.count()
            period_count = apply_filters(
                base_query,
                TransactionFilters(start_date=filters.start_date, end_date=filters.end_date),
            ).count()
            if total_records == 0:
                empty_state = {
                    "title": "No transactions yet",
                    "body": "Create the first revenue or expense entry to start building ledger history.",
                    "primary_label": "Add revenue",
                    "primary_url": url_for("transactions.revenue_new"),
                    "secondary_label": "Add expense",
                    "secondary_url": url_for("transactions.expense_new"),
                }
            elif period_count == 0:
                empty_state = {
                    "title": "No records in this period",
                    "body": "There are ledger records, but none fall inside the selected week, month, or year window.",
                    "primary_label": "View this year",
                    "primary_url": url_for("transactions.transactions_list", period="year", transaction_type=selected_type, q=request.args.get("q"), status=request.args.get("status")),
                    "secondary_label": "Reset filters",
                    "secondary_url": url_for("transactions.transactions_list"),
                }
            else:
                empty_state = {
                    "title": "No records match the current filters",
                    "body": "Try clearing the status or search filters to widen the current history view.",
                    "primary_label": "Reset filters",
                    "primary_url": url_for("transactions.transactions_list", period=_history_period(), transaction_type=selected_type),
                    "secondary_label": None,
                    "secondary_url": None,
                }
    return render_template(
        "transactions/list.html",
        page_title="History",
        pagination=pagination,
        filter_form=form,
        selected_period=_history_period(),
        selected_type=selected_type,
        empty_state=empty_state,
    )


@transactions_bp.get("/revenue")
@login_required
def revenue_list():
    return redirect(url_for("transactions.transactions_list", type=TransactionType.REVENUE.value, period=_history_period(), q=request.args.get("q")))


@transactions_bp.route("/revenue/new", methods=["GET", "POST"])
@login_required
def revenue_new():
    if not (g.current_user.is_admin or g.current_user.can_create_revenue):
        flash("You do not have permission to create revenue entries.", "error")
        return redirect(url_for("transactions.transactions_list"))
    form = RevenueEntryForm()
    assign_simple_entry_choices(form)
    entry_ready = setup_status()["is_ready_for_basic_entry"]
    if form.validate_on_submit():
        try:
            ensure_entry_setup(TransactionType.REVENUE.value)
            create_simple_revenue(
                company_name=form.company_name.data,
                amount=form.amount.data,
                transaction_date=form.transaction_date.data,
                payment_method_id=form.payment_method_id.data,
                reference_number=form.reference_number.data,
                note=form.note.data,
                actor=g.current_user,
            )
            db.session.commit()
            flash("Revenue saved.", "success")
            return redirect(url_for("transactions.transactions_list", period="month"))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
    return render_template(
        "transactions/simple_form.html",
        form=form,
        entry_type=TransactionType.REVENUE.value,
        page_title="Add Revenue",
        entry_ready=entry_ready,
        entry_setup_message=missing_setup_message(transaction_type=TransactionType.REVENUE.value),
    )


@transactions_bp.get("/revenue/<int:transaction_id>")
@login_required
def revenue_detail(transaction_id: int):
    transaction = get_transaction_or_404(transaction_id, user=g.current_user, transaction_type=TransactionType.REVENUE.value)
    return render_template(
        "transactions/detail.html",
        transaction=transaction,
        action_form=None,
        settlement_form=SettlementForm(),
        delete_form=DeleteDraftForm(),
        comment_form=TransactionCommentForm(),
        exceptions=transaction_exception_messages(transaction),
        can_edit=can_edit_transaction(transaction, g.current_user),
        action_state=expense_action_state(transaction, g.current_user),
    )


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
    return redirect(url_for("transactions.transactions_list", type=TransactionType.EXPENSE.value, period=_history_period(), q=request.args.get("q")))


@transactions_bp.route("/expenses/new", methods=["GET", "POST"])
@login_required
def expense_new():
    if not (g.current_user.is_admin or g.current_user.can_create_expense):
        flash("You do not have permission to create expense entries.", "error")
        return redirect(url_for("transactions.transactions_list"))
    form = ExpenseEntryForm()
    assign_simple_entry_choices(form)
    entry_ready = setup_status()["is_ready_for_basic_entry"]
    if form.validate_on_submit():
        try:
            ensure_entry_setup(TransactionType.EXPENSE.value)
            create_simple_expense(
                title=form.title.data,
                amount=form.amount.data,
                transaction_date=form.transaction_date.data,
                payment_method_id=form.payment_method_id.data,
                reference_number=form.reference_number.data,
                note=form.note.data,
                actor=g.current_user,
            )
            db.session.commit()
            flash("Expense saved.", "success")
            return redirect(url_for("transactions.transactions_list", period="month"))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
    return render_template(
        "transactions/simple_form.html",
        form=form,
        entry_type=TransactionType.EXPENSE.value,
        page_title="Add Expense",
        entry_ready=entry_ready,
        entry_setup_message=missing_setup_message(transaction_type=TransactionType.EXPENSE.value),
    )


@transactions_bp.get("/expenses/<int:transaction_id>")
@login_required
def expense_detail(transaction_id: int):
    transaction = get_transaction_or_404(transaction_id, user=g.current_user, transaction_type=TransactionType.EXPENSE.value)
    return render_template(
        "transactions/detail.html",
        transaction=transaction,
        action_form=ExpenseActionForm(),
        settlement_form=SettlementForm(),
        delete_form=DeleteDraftForm(),
        comment_form=TransactionCommentForm(),
        exceptions=transaction_exception_messages(transaction),
        can_edit=can_edit_transaction(transaction, g.current_user),
        action_state=expense_action_state(transaction, g.current_user),
    )


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
    return _render_history()


@transactions_bp.get("/transactions/<int:transaction_id>")
@login_required
def transaction_detail(transaction_id: int):
    transaction = get_transaction_or_404(transaction_id, user=g.current_user)
    if transaction.transaction_type == TransactionType.REVENUE.value:
        return redirect(url_for("transactions.revenue_detail", transaction_id=transaction.id))
    return redirect(url_for("transactions.expense_detail", transaction_id=transaction.id))


@transactions_bp.post("/transactions/<int:transaction_id>/comments")
@login_required
def transaction_comment(transaction_id: int):
    transaction = get_transaction_or_404(transaction_id, user=g.current_user)
    form = TransactionCommentForm()
    if form.validate_on_submit():
        try:
            add_transaction_comment(transaction, g.current_user, form.body.data)
            db.session.commit()
            flash("Comment posted.", "success")
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
    return redirect(url_for("transactions.transaction_detail", transaction_id=transaction.id))


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
@limiter.limit("20 per hour")
@login_required
def transactions_export():
    history_mode = request.args.get("period") in {"week", "month", "year"} or _history_type() is not None
    filters = _history_filters() if history_mode else _filters()
    try:
        content = export_transactions_csv(
            user=g.current_user,
            transaction_type=_history_type() if history_mode else request.args.get("type"),
            filters=filters,
        )
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("transactions.transactions_list"))
    return Response(
        content,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=transactions.csv"},
    )
