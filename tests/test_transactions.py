from __future__ import annotations

from io import BytesIO

from app.extensions import db
from app.models import Transaction
from app.utils.enums import ExpenseStatus, RevenueStatus, TransactionType


def test_create_revenue_entry(client, app, sample_data, login):
    login("revenue@example.com", "RevenuePassword123")
    response = client.post(
        "/revenue/new",
        data={
            "title": "April Retainer",
            "counterparty": "Client Y",
            "category_id": sample_data["revenue_category_id"],
            "account_id": sample_data["account_id"],
            "payment_method_id": sample_data["payment_method_id"],
            "transaction_date": "2026-04-01",
            "due_date": "2026-04-08",
            "expected_amount": "2400.00",
            "received_amount": "0",
            "submit_record": "1",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    with app.app_context():
        assert Transaction.query.filter_by(title="April Retainer", transaction_type=TransactionType.REVENUE.value).count() == 1


def test_create_submit_and_approve_expense(client, app, sample_data, login):
    login("staff@example.com", "StaffPassword123")
    response = client.post(
        "/expenses/new",
        data={
            "title": "Office internet",
            "counterparty": "ISP Ghana",
            "category_id": sample_data["expense_category_id"],
            "account_id": sample_data["account_id"],
            "payment_method_id": sample_data["payment_method_id"],
            "transaction_date": "2026-04-05",
            "due_date": "2026-04-06",
            "amount": "180.00",
            "save_draft": "1",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    with app.app_context():
        item = Transaction.query.filter_by(title="Office internet").first()
        assert item.status == ExpenseStatus.DRAFT.value
        expense_id = item.id

    submit_response = client.post(f"/expenses/{expense_id}/submit", follow_redirects=False)
    assert submit_response.status_code == 302
    client.post("/logout")
    login("admin@example.com", "AdminPassword123")
    approve_response = client.post(f"/expenses/{expense_id}/approve", follow_redirects=False)
    assert approve_response.status_code == 302
    with app.app_context():
        item = db.session.get(Transaction, expense_id)
        assert item.status == ExpenseStatus.APPROVED.value


def test_invalid_transition_is_blocked(client, app, sample_data, login):
    login("admin@example.com", "AdminPassword123")
    response = client.post(f"/expenses/{sample_data['draft_expense_id']}/approve", follow_redirects=True)
    assert b"Invalid status transition" in response.data


def test_duplicate_approve_does_not_overwrite_existing_approval(client, app, sample_data, login):
    login("admin@example.com", "AdminPassword123")
    first = client.post(f"/expenses/{sample_data['submitted_expense_id']}/approve", follow_redirects=False)
    second = client.post(f"/expenses/{sample_data['submitted_expense_id']}/approve", follow_redirects=False)

    assert first.status_code == 302
    assert second.status_code == 302
    with app.app_context():
        item = db.session.get(Transaction, sample_data["submitted_expense_id"])
        assert item.status == ExpenseStatus.APPROVED.value


def test_attachment_validation_blocks_invalid_files(client, app, sample_data, login):
    login("staff@example.com", "StaffPassword123")
    response = client.post(
        "/expenses/new",
        data={
            "title": "Unsafe attachment",
            "counterparty": "Vendor",
            "category_id": sample_data["expense_category_id"],
            "account_id": sample_data["account_id"],
            "payment_method_id": sample_data["payment_method_id"],
            "transaction_date": "2026-04-05",
            "amount": "50.00",
            "save_draft": "1",
            "attachments": (BytesIO(b"malicious"), "malware.exe"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"Unsupported attachment type" in response.data


def test_revenue_mark_received(client, app, sample_data, login):
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
