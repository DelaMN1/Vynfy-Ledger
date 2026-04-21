from __future__ import annotations

from datetime import date

from app.extensions import db
from app.models import ReconciliationSession


def test_reconciliation_session_creation(client, app, sample_data, login):
    login("admin@example.com", "AdminPassword123")
    response = client.post(
        "/reconciliation/start",
        data={
            "account_id": sample_data["account_id"],
            "period_start": "2026-04-01",
            "period_end": "2026-04-30",
            "statement_ending_balance": "2000.00",
            "notes": "April statement",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    with app.app_context():
        assert ReconciliationSession.query.count() == 1


def test_duplicate_reconciliation_start_is_idempotent(client, app, sample_data, login):
    login("admin@example.com", "AdminPassword123")
    payload = {
        "account_id": sample_data["account_id"],
        "period_start": "2026-04-01",
        "period_end": "2026-04-30",
        "statement_ending_balance": "2000.00",
        "notes": "April statement",
    }

    first = client.post("/reconciliation/start", data=payload, follow_redirects=False)
    second = client.post("/reconciliation/start", data=payload, follow_redirects=False)

    assert first.status_code == 302
    assert second.status_code == 302
    with app.app_context():
        assert ReconciliationSession.query.count() == 1


def test_finalize_requires_admin(client, app, sample_data, login):
    with app.app_context():
        session = ReconciliationSession(
            account_id=sample_data["account_id"],
            period_start=date(2026, 4, 1),
            period_end=date(2026, 4, 30),
            statement_ending_balance=1000,
            system_balance=1000,
            difference=0,
        )
        db.session.add(session)
        db.session.commit()
        session_id = session.id
    login("staff@example.com", "StaffPassword123")
    response = client.post(f"/reconciliation/{session_id}/finalize", follow_redirects=False)
    assert response.status_code == 403


def test_reconciliation_dashboard_requires_admin(client, sample_data, login):
    login("staff@example.com", "StaffPassword123")
    response = client.get("/reconciliation", follow_redirects=False)
    assert response.status_code == 403


def test_duplicate_reconciliation_finalize_is_idempotent(client, app, sample_data, login):
    with app.app_context():
        session = ReconciliationSession(
            account_id=sample_data["account_id"],
            period_start=date(2026, 4, 1),
            period_end=date(2026, 4, 30),
            statement_ending_balance=1000,
            system_balance=1000,
            difference=0,
        )
        db.session.add(session)
        db.session.commit()
        session_id = session.id

    login("admin@example.com", "AdminPassword123")
    first = client.post(f"/reconciliation/{session_id}/finalize", data={"transaction_ids": [sample_data["revenue_id"]]}, follow_redirects=False)
    second = client.post(f"/reconciliation/{session_id}/finalize", data={"transaction_ids": [sample_data["revenue_id"]]}, follow_redirects=False)

    assert first.status_code == 302
    assert second.status_code == 302
    with app.app_context():
        session = db.session.get(ReconciliationSession, session_id)
        assert session.selected_transaction_ids == [sample_data["revenue_id"]]


def test_finalize_rejects_transactions_outside_session_scope(client, app, sample_data, login):
    with app.app_context():
        session = ReconciliationSession(
            account_id=sample_data["account_id"],
            period_start=date(2026, 4, 1),
            period_end=date(2026, 4, 10),
            statement_ending_balance=1000,
            system_balance=1000,
            difference=0,
        )
        db.session.add(session)
        db.session.commit()
        session_id = session.id

    login("admin@example.com", "AdminPassword123")
    response = client.post(
        f"/reconciliation/{session_id}/finalize",
        data={"transaction_ids": [sample_data["draft_expense_id"]]},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Selected transactions must belong to the reconciliation account and period." in response.data
    with app.app_context():
        session = db.session.get(ReconciliationSession, session_id)
        assert session.status == "draft"
