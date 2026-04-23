from __future__ import annotations

from app.extensions import db
from app.models import Budget
from app.utils.enums import TransactionType


def test_dashboard_renders_budget_and_queue_sections(client, app, sample_data, login):
    with app.app_context():
        db.session.add(
            Budget(
                name="Ops Budget",
                transaction_type=TransactionType.EXPENSE.value,
                category_id=sample_data["expense_category_id"],
                account_id=sample_data["account_id"],
                owner_id=sample_data["staff_id"],
                amount=2500,
                alert_percent=80,
            )
        )
        db.session.commit()

    login("admin@example.com", "AdminPassword123")
    response = client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 200
    assert b"Budget vs Actuals" in response.data
    assert b"Action Queue" in response.data
