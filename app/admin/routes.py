from __future__ import annotations

from flask import Blueprint, render_template

from app.utils.decorators import admin_required
from app.transactions.services import pending_approvals


admin_bp = Blueprint("admin", __name__)


@admin_bp.get("/admin/pending-approvals")
@admin_required
def approvals():
    return render_template("admin/pending_approvals.html", items=pending_approvals())
