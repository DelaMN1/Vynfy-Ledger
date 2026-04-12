from __future__ import annotations

from flask import Blueprint, render_template

from app.admin.services import pending_approvals
from app.utils.decorators import admin_required


admin_bp = Blueprint("admin", __name__)


@admin_bp.get("/admin/pending-approvals")
@admin_required
def approvals():
    return render_template("admin/pending_approvals.html", items=pending_approvals())
