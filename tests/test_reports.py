from __future__ import annotations

from app.extensions import db
from app.models import User
from app.reports.services import build_report
from app.transactions.services import TransactionFilters


def test_report_metrics_calculate_correctly(app, sample_data):
    with app.app_context():
        admin = db.session.get(User, sample_data["admin_id"])
        report = build_report(admin, "cash_flow_monthly", TransactionFilters())
        assert report["metric_total"] == 1000.0


def test_csv_export_works(client, sample_data, login):
    login("admin@example.com", "AdminPassword123")
    response = client.get("/reports/export/csv?report=expense_monthly")
    assert response.status_code == 200
    assert response.mimetype.startswith("text/csv")
    assert b"label,value" in response.data
