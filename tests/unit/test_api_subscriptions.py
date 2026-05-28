"""
Tests for manual CRUD subscription endpoints (Phase 3.4).

Verifies:
- POST /api/subscriptions creates a subscription
- POST /api/subscriptions/{id}/update updates fields
- DELETE /api/subscriptions/{id} removes a subscription
- Error cases: 404 for missing subscription, 422 for invalid body
"""
import pytest
from fastapi.testclient import TestClient

from backend.db.setup import get_connection


@pytest.fixture()
def client(db_path):
    """TestClient against the real FastAPI app using a test DB."""
    import os
    os.environ["DB_PATH"] = db_path
    os.environ["USE_MOCK"] = "true"
    from backend.api.app import app
    return TestClient(app)


# ── POST /api/subscriptions — create ─────────────────────────────────────────

def test_create_subscription_returns_201(client):
    """POST /api/subscriptions with valid body → 201 and subscription object."""
    response = client.post(
        "/api/subscriptions",
        json={"name": "Manual Sub", "amount": 9.99, "currency": "USD", "billing_cycle": "MONTHLY"},
    )
    assert response.status_code == 201, (
        f"POST /api/subscriptions must return 201, got {response.status_code}: {response.text}"
    )
    data = response.json()
    assert data["name"] == "Manual Sub"
    assert data["amount"] == pytest.approx(9.99)
    assert data["currency"] == "USD"
    assert data["billing_cycle"] == "MONTHLY"
    assert data["status"] == "ACTIVE"  # default
    assert "subscription_id" in data


def test_create_subscription_name_only(client):
    """POST /api/subscriptions with just a name → 201 (other fields have defaults)."""
    response = client.post("/api/subscriptions", json={"name": "Minimal Sub"})
    assert response.status_code == 201, (
        f"POST /api/subscriptions with minimal body must return 201, got {response.status_code}: {response.text}"
    )
    data = response.json()
    assert data["name"] == "Minimal Sub"
    assert data["currency"] == "USD"   # default
    assert data["status"] == "ACTIVE"  # default


def test_create_subscription_missing_name_returns_422(client):
    """POST /api/subscriptions without required 'name' field → 422."""
    response = client.post(
        "/api/subscriptions",
        json={"amount": 9.99, "currency": "USD"},  # no 'name'
    )
    assert response.status_code == 422, (
        f"POST /api/subscriptions without 'name' must return 422, got {response.status_code}"
    )


def test_create_subscription_ils_currency(client):
    """POST /api/subscriptions with ILS currency → stored correctly."""
    response = client.post(
        "/api/subscriptions",
        json={"name": "Israeli Service", "amount": 49.90, "currency": "ILS", "billing_cycle": "MONTHLY"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["currency"] == "ILS"
    assert data["amount"] == pytest.approx(49.90)


def test_create_subscription_persists_in_db(client, db_path):
    """POST /api/subscriptions persists the subscription in the database."""
    response = client.post("/api/subscriptions", json={"name": "DB Test Sub"})
    assert response.status_code == 201
    sub_id = response.json()["subscription_id"]

    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT name, status FROM subscriptions WHERE subscription_id = ?", (sub_id,)
    ).fetchone()
    conn.close()
    assert row is not None, f"Subscription {sub_id} must exist in DB after POST"
    assert row[0] == "DB Test Sub"
    assert row[1] == "ACTIVE"


# ── POST /api/subscriptions/{id}/update ───────────────────────────────────────

def test_update_subscription_changes_amount(client):
    """POST /api/subscriptions/{id}/update with amount → 200, amount updated."""
    # First create
    create_resp = client.post(
        "/api/subscriptions",
        json={"name": "Update Test", "amount": 5.00, "currency": "USD"},
    )
    assert create_resp.status_code == 201
    sub_id = create_resp.json()["subscription_id"]

    # Then update
    update_resp = client.post(
        f"/api/subscriptions/{sub_id}/update",
        json={"amount": 12.99},
    )
    assert update_resp.status_code == 200, (
        f"POST /api/subscriptions/{{id}}/update must return 200, got {update_resp.status_code}: {update_resp.text}"
    )
    data = update_resp.json()
    assert data["amount"] == pytest.approx(12.99), (
        f"amount must be updated to 12.99, got {data['amount']}"
    )
    assert data["name"] == "Update Test"  # unchanged


def test_update_subscription_changes_status(client):
    """POST /api/subscriptions/{id}/update with status=CANCELLED → status updated."""
    create_resp = client.post("/api/subscriptions", json={"name": "Status Test"})
    sub_id = create_resp.json()["subscription_id"]

    update_resp = client.post(
        f"/api/subscriptions/{sub_id}/update",
        json={"status": "CANCELLED"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["status"] == "CANCELLED"


def test_update_subscription_changes_billing_cycle(client):
    """POST /api/subscriptions/{id}/update with billing_cycle=ANNUAL → cycle updated."""
    create_resp = client.post(
        "/api/subscriptions",
        json={"name": "Cycle Test", "billing_cycle": "MONTHLY"},
    )
    sub_id = create_resp.json()["subscription_id"]

    update_resp = client.post(
        f"/api/subscriptions/{sub_id}/update",
        json={"billing_cycle": "ANNUAL"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["billing_cycle"] == "ANNUAL"


def test_update_nonexistent_subscription_returns_404(client):
    """POST /api/subscriptions/{nonexistent_id}/update → 404."""
    response = client.post(
        "/api/subscriptions/sub-does-not-exist/update",
        json={"amount": 9.99},
    )
    assert response.status_code == 404, (
        f"Updating a nonexistent subscription must return 404, got {response.status_code}"
    )


# ── DELETE /api/subscriptions/{id} ───────────────────────────────────────────

def test_delete_subscription_returns_204(client):
    """DELETE /api/subscriptions/{id} → 204, subscription removed."""
    create_resp = client.post("/api/subscriptions", json={"name": "To Delete"})
    assert create_resp.status_code == 201
    sub_id = create_resp.json()["subscription_id"]

    delete_resp = client.delete(f"/api/subscriptions/{sub_id}")
    assert delete_resp.status_code == 204, (
        f"DELETE /api/subscriptions/{{id}} must return 204, got {delete_resp.status_code}: {delete_resp.text}"
    )


def test_delete_subscription_removes_from_db(client, db_path):
    """DELETE /api/subscriptions/{id} removes the row from the database."""
    create_resp = client.post("/api/subscriptions", json={"name": "DB Delete Test"})
    sub_id = create_resp.json()["subscription_id"]

    client.delete(f"/api/subscriptions/{sub_id}")

    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT subscription_id FROM subscriptions WHERE subscription_id = ?", (sub_id,)
    ).fetchone()
    conn.close()
    assert row is None, f"Subscription {sub_id} must not exist in DB after DELETE"


def test_delete_nonexistent_subscription_returns_404(client):
    """DELETE /api/subscriptions/{nonexistent_id} → 404."""
    response = client.delete("/api/subscriptions/sub-does-not-exist")
    assert response.status_code == 404, (
        f"Deleting a nonexistent subscription must return 404, got {response.status_code}"
    )


def test_delete_subscription_does_not_appear_in_list(client):
    """After DELETE, subscription must not appear in GET /api/subscriptions."""
    create_resp = client.post("/api/subscriptions", json={"name": "List Delete Test"})
    sub_id = create_resp.json()["subscription_id"]

    # Verify it appears before delete
    before = client.get("/api/subscriptions").json()
    assert any(s["subscription_id"] == sub_id for s in before), "Must appear before delete"

    client.delete(f"/api/subscriptions/{sub_id}")

    # Must not appear after delete
    after = client.get("/api/subscriptions").json()
    assert not any(s["subscription_id"] == sub_id for s in after), (
        f"Deleted subscription {sub_id} must not appear in GET /api/subscriptions"
    )


# ── Source provider assignment ────────────────────────────────────────────────

def test_create_subscription_in_mock_mode_uses_mock_provider(client):
    """In mock mode (USE_MOCK=true), manually created subscription uses source_provider=MOCK."""
    response = client.post("/api/subscriptions", json={"name": "Mock Provider Test"})
    assert response.status_code == 201
    data = response.json()
    assert data["source_provider"] == "MOCK", (
        f"In mock mode, manually created subscription must have source_provider='MOCK', "
        f"got {data['source_provider']!r}"
    )
