from __future__ import annotations

from flask import Blueprint, g, render_template

from app.dashboard.services import dashboard_context
from app.utils.decorators import login_required


dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.get("/dashboard")
@login_required
def overview() -> str:
    context = dashboard_context(g.current_user)
    return render_template("dashboard/index.html", **context)
