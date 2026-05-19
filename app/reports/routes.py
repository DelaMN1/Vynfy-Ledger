from __future__ import annotations

from flask import Blueprint, Response, flash, g, redirect, render_template, request, url_for

from app.extensions import limiter
from app.reports.services import REPORT_OPTIONS, build_report, export_report_csv, normalize_report_key
from app.transactions.forms import TransactionFilterForm
from app.utils.decorators import login_required
from app.utils.types import TransactionFilters
from app.transactions.services import assign_filter_choices


reports_bp = Blueprint("reports", __name__)


def _filters() -> TransactionFilters:
    return TransactionFilters(
        q=request.args.get("q") or None,
        status=request.args.get("status") or None,
        category_id=request.args.get("category_id", type=int) or None,
        account_id=request.args.get("account_id", type=int) or None,
        owner_id=request.args.get("owner_id", type=int) or None,
    )


@reports_bp.get("/reports")
@login_required
def index() -> str:
    report_key = request.args.get("report", "cash_flow_monthly")
    form = TransactionFilterForm(formdata=request.args)
    assign_filter_choices(form, user=g.current_user)
    try:
        report = build_report(g.current_user, report_key, _filters())
    except ValueError as exc:
        flash(str(exc), "error")
        report = {"labels": [], "values": [], "rows": [], "metric_total": 0.0}
    return render_template("reports/index.html", report=report, report_key=report_key, report_options=REPORT_OPTIONS, filter_form=form)


@reports_bp.get("/reports/export/csv")
@limiter.limit("20 per hour")
@login_required
def export_csv() -> Response:
    report_key = request.args.get("report", "cash_flow_monthly")
    try:
        content = export_report_csv(g.current_user, report_key, _filters())
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("reports.index", report=report_key))
    filename = f"{normalize_report_key(report_key)}.csv"
    return Response(content, mimetype="text/csv; charset=utf-8", headers={"Content-Disposition": f"attachment; filename={filename}"})
