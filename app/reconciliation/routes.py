from __future__ import annotations

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from app.extensions import db
from app.reconciliation.forms import ReconciliationForm
from app.reconciliation.services import (
    create_session_from_form,
    finalize_session,
    get_session_or_404,
    reconciliation_accounts,
    reconciliation_transactions,
)
from app.utils.decorators import admin_required


reconciliation_bp = Blueprint("reconciliation", __name__)


@reconciliation_bp.get("/reconciliation")
@admin_required
def index():
    form = ReconciliationForm()
    form.account_id.choices = reconciliation_accounts()
    active_session = None
    transactions = []
    session_id = request.args.get("session_id", type=int)
    if session_id:
        try:
            active_session = get_session_or_404(session_id, actor=g.current_user)
            transactions = reconciliation_transactions(active_session)
        except ValueError as exc:
            flash(str(exc), "error")
    return render_template("reconciliation/index.html", form=form, active_session=active_session, transactions=transactions)


@reconciliation_bp.post("/reconciliation/start")
@admin_required
def start():
    form = ReconciliationForm()
    form.account_id.choices = reconciliation_accounts()
    if form.validate_on_submit():
        try:
            session = create_session_from_form(form=form, actor=g.current_user)
            db.session.commit()
            flash("Reconciliation session created.", "success")
            return redirect(url_for("reconciliation.index", session_id=session.id))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "error")
    return render_template("reconciliation/index.html", form=form, active_session=None, transactions=[])


@reconciliation_bp.post("/reconciliation/<int:session_id>/finalize")
@admin_required
def finalize(session_id: int):
    try:
        session = get_session_or_404(session_id, actor=g.current_user)
        selected_transaction_ids = [int(value) for value in request.form.getlist("transaction_ids")]
        finalize_session(session=session, actor=g.current_user, selected_transaction_ids=selected_transaction_ids)
        db.session.commit()
        flash("Reconciliation finalized.", "success")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "error")
    return redirect(url_for("reconciliation.index", session_id=session_id))
