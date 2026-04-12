from __future__ import annotations


def test_staff_cannot_access_admin_routes(client, sample_data, login):
    login("staff@example.com", "StaffPassword123")
    response = client.get("/settings/categories")
    assert response.status_code == 403


def test_staff_cannot_view_other_users_private_items(client, sample_data, login):
    login("other@example.com", "OtherPassword123")
    response = client.get(f"/expenses/{sample_data['draft_expense_id']}")
    assert response.status_code == 403


def test_only_admin_can_approve_expenses(client, sample_data, login):
    login("staff@example.com", "StaffPassword123")
    response = client.post(f"/expenses/{sample_data['submitted_expense_id']}/approve", follow_redirects=False)
    assert response.status_code == 403


def test_only_owner_or_admin_can_edit_valid_records(client, sample_data, login):
    login("staff@example.com", "StaffPassword123")
    own_response = client.get(f"/expenses/{sample_data['draft_expense_id']}/edit")
    assert own_response.status_code == 200
    client.post("/logout")
    login("other@example.com", "OtherPassword123")
    foreign_response = client.get(f"/expenses/{sample_data['draft_expense_id']}/edit")
    assert foreign_response.status_code == 403
