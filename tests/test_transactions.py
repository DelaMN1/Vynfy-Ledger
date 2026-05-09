from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.extensions import db
from app.models import AccountingMapping, Budget, Transaction
from app.utils.enums import ExpenseStatus, RevenueStatus, TransactionType


def test_create_revenue_entry_with_minimal_fields(client, app, sample_data, login):
    login("revenue@example.com", "RevenuePassword123")
    response = client.post(
        "/revenue/new",
        data={
            "company_name": "Client Y",
            "amount": "2400.00",
            "transaction_date": "2026-04-01",
            "payment_method_id": str(sample_data["payment_method_id"]),
            "reference_number": "INV-APR-2026",
            "note": "Paid in full",
            "submit": "1",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    with app.app_context():
        item = Transaction.query.filter_by(counterparty="Client Y", transaction_type=TransactionType.REVENUE.value).first()
        assert item is not None
        assert item.status == RevenueStatus.RECEIVED.value
        assert item.title == "Revenue from Client Y"
        assert item.expected_amount == Decimal("2400.00")
        assert item.received_amount == Decimal("2400.00")
        assert item.payment_method_id == sample_data["payment_method_id"]
        assert item.reference_number == "INV-APR-2026"
        assert item.note == "Paid in full"


def test_create_expense_entry_with_minimal_fields(client, app, sample_data, login):
    login("staff@example.com", "StaffPassword123")
    response = client.post(
        "/expenses/new",
        data={
            "title": "Office internet",
            "amount": "180.00",
            "transaction_date": "2026-04-05",
            "payment_method_id": str(sample_data["payment_method_id"]),
            "reference_number": "ISP-0426",
            "note": "Monthly service charge",
            "submit": "1",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    with app.app_context():
        item = Transaction.query.filter_by(title="Office internet", transaction_type=TransactionType.EXPENSE.value).first()
        assert item is not None
        assert item.status == ExpenseStatus.PAID.value
        assert item.settled_date == date(2026, 4, 5)
        assert item.payment_method_id == sample_data["payment_method_id"]
        assert item.reference_number == "ISP-0426"
        assert item.note == "Monthly service charge"


def test_history_is_canonical_and_legacy_lists_redirect(client, sample_data, login):
    login("admin@example.com", "AdminPassword123")

    revenue_response = client.get("/revenue", follow_redirects=False)
    expense_response = client.get("/expenses", follow_redirects=False)
    history_response = client.get("/transactions?period=month&transaction_type=revenue", follow_redirects=False)

    assert revenue_response.status_code == 302
    assert "transactions?type=revenue" in revenue_response.headers["Location"]
    assert expense_response.status_code == 302
    assert "transactions?type=expense" in expense_response.headers["Location"]
    assert history_response.status_code == 200
    assert b"Ledger History" in history_response.data
    assert b"All statuses" in history_response.data
    assert b"Client X" in history_response.data
    assert b"Draft expense" not in history_response.data


def test_history_period_filter_excludes_old_records(client, app, sample_data, login):
    with app.app_context():
        old_item = Transaction(
            transaction_type=TransactionType.EXPENSE.value,
            title="Old expense",
            category_id=sample_data["expense_category_id"],
            account_id=sample_data["account_id"],
            amount=Decimal("45.00"),
            transaction_date=date.today() - timedelta(days=400),
            settled_date=date.today() - timedelta(days=400),
            status=ExpenseStatus.PAID.value,
            submitted_by_id=sample_data["staff_id"],
        )
        db.session.add(old_item)
        db.session.commit()

    login("admin@example.com", "AdminPassword123")
    month_response = client.get("/transactions?period=month", follow_redirects=False)
    year_response = client.get("/transactions?period=year&q=Old", follow_redirects=False)

    assert month_response.status_code == 200
    assert b"Old expense" not in month_response.data
    assert year_response.status_code == 200
    assert b"Old expense" not in year_response.data


def test_transaction_detail_is_simplified(client, sample_data, login):
    login("staff@example.com", "StaffPassword123")
    response = client.get(f"/expenses/{sample_data['submitted_expense_id']}", follow_redirects=False)

    assert response.status_code == 200
    assert b"Back to History" in response.data
    assert b"Category" in response.data
    assert b"Account" in response.data
    assert b"Approval comments" not in response.data
    assert b"Status history" not in response.data
    assert b"Mark paid" not in response.data


def test_revenue_mark_received_still_works_for_legacy_flow(client, app, sample_data, login):
    login("admin@example.com", "AdminPassword123")
    response = client.post(
        f"/revenue/{sample_data['revenue_id']}/mark-received",
        data={"amount": "1000.00", "settled_date": "2026-04-09"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    with app.app_context():
        item = db.session.get(Transaction, sample_data["revenue_id"])
        assert item.status == RevenueStatus.RECEIVED.value


def test_expense_create_skips_heavy_control_resolution_for_simplified_flow(client, app, sample_data, login):
    with app.app_context():
        db.session.add(
            Budget(
                name="Ops monthly",
                transaction_type=TransactionType.EXPENSE.value,
                category_id=sample_data["expense_category_id"],
                account_id=sample_data["account_id"],
                owner_id=sample_data["staff_id"],
                amount=5000,
                alert_percent=80,
            )
        )
        db.session.add(
            AccountingMapping(
                name="Ops GL",
                transaction_type=TransactionType.EXPENSE.value,
                category_id=sample_data["expense_category_id"],
                account_id=sample_data["account_id"],
                gl_code="6000",
                cost_center="OPS",
                project_code="HQ",
            )
        )
        db.session.commit()

    login("staff@example.com", "StaffPassword123")
    response = client.post(
        "/expenses/new",
        data={
            "title": "Printer supplies",
            "amount": "120.00",
            "transaction_date": "2026-04-05",
            "submit": "1",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    with app.app_context():
        item = Transaction.query.filter_by(title="Printer supplies").first()
        assert item is not None
        assert item.budget is None
        assert item.accounting_gl_code is None
        assert item.accounting_cost_center is None
        assert item.accounting_project_code is None
