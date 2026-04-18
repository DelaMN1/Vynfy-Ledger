from __future__ import annotations

from flask import Blueprint, g, render_template, request

from app.dashboard.services import dashboard_context
from app.utils.decorators import login_required


dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.get("/dashboard")
@login_required
def overview() -> str:
    context = dashboard_context(g.current_user, range_key=request.args.get("range", "month"))
    if request.headers.get("HX-Request"):
        return render_template("dashboard/_dashboard_content.html", **context)
    return render_template("dashboard/index.html", **context)
