from __future__ import annotations


def test_dashboard_renders_monthly_totals_and_recent_activity(client, sample_data, login):
    login("admin@example.com", "AdminPassword123")
    response = client.get("/dashboard", follow_redirects=False)

    assert response.status_code == 200
    assert b"Revenue This Month" in response.data
    assert b"Expenses This Month" in response.data
    assert b"Net This Month" in response.data
    assert b"Add Revenue" in response.data
    assert b"Recent activity" in response.data
    assert b"Active users" in response.data
    assert b"Active accounts" in response.data
    assert b"Budget vs Actuals" not in response.data
    assert b"Action Queue" not in response.data
