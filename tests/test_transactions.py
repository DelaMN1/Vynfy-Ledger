from __future__ import annotations

from io import BytesIO

from app.extensions import db
from app.models import AccountingMapping, Attachment, Budget, SpendPolicy, Transaction, TransactionComment
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


def test_expense_submit_requires_attachment_when_policy_configured(client, app, sample_data, login):
    with app.app_context():
        db.session.add(
            SpendPolicy(
                name="Operations receipts",
                transaction_type=TransactionType.EXPENSE.value,
                category_id=sample_data["expense_category_id"],
                require_attachment=True,
            )
        )
        db.session.commit()

    login("staff@example.com", "StaffPassword123")
    response = client.post(f"/expenses/{sample_data['draft_expense_id']}/submit", follow_redirects=True)
    assert b"requires at least one attachment" in response.data


def test_expense_create_applies_budget_and_accounting_mapping(client, app, sample_data, login):
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
                payment_method_id=sample_data["payment_method_id"],
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
            "counterparty": "Stationery Hub",
            "category_id": sample_data["expense_category_id"],
            "account_id": sample_data["account_id"],
            "payment_method_id": sample_data["payment_method_id"],
            "transaction_date": "2026-04-05",
            "amount": "120.00",
            "note": "Restocking",
            "save_draft": "1",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    with app.app_context():
        item = Transaction.query.filter_by(title="Printer supplies").first()
        assert item.budget is not None
        assert item.accounting_gl_code == "6000"
        assert item.accounting_cost_center == "OPS"
        assert item.accounting_project_code == "HQ"


def test_duplicate_receipt_hash_is_tracked(client, app, sample_data, login):
    login("staff@example.com", "StaffPassword123")
    base_payload = {
        "counterparty": "Vendor",
        "category_id": sample_data["expense_category_id"],
        "account_id": sample_data["account_id"],
        "payment_method_id": sample_data["payment_method_id"],
        "transaction_date": "2026-04-05",
        "amount": "50.00",
        "save_draft": "1",
    }
    first = client.post(
        "/expenses/new",
        data={
            **base_payload,
            "title": "Receipt one",
            "attachments": (BytesIO(b"same-receipt"), "receipt-one.pdf", "application/pdf"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    second = client.post(
        "/expenses/new",
        data={
            **base_payload,
            "title": "Receipt two",
            "attachments": (BytesIO(b"same-receipt"), "receipt-two.pdf", "application/pdf"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )

    assert first.status_code == 302
    assert second.status_code == 302
    with app.app_context():
        attachments = Attachment.query.order_by(Attachment.id.asc()).all()
        assert len(attachments) == 2
        assert attachments[0].sha256_hash
        assert attachments[1].duplicate_of_attachment_id == attachments[0].id


def test_transaction_comment_is_recorded(client, app, sample_data, login):
    login("admin@example.com", "AdminPassword123")
    response = client.post(
        f"/transactions/{sample_data['submitted_expense_id']}/comments",
        data={"body": "Please attach the vendor invoice before payment."},
        follow_redirects=False,
    )
    assert response.status_code == 302
    with app.app_context():
        comment = TransactionComment.query.filter_by(transaction_id=sample_data["submitted_expense_id"]).first()
        assert comment is not None
        assert "vendor invoice" in comment.body
