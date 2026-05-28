"""
Tests for GET /api/payment-events endpoint (Phase 3.3B).

Verifies:
- Endpoint exists and returns 200
- Response contains only safe structured fields (no raw email content)
- Filtering by event_type works
- renewal_charge event_type is accepted (migration 007 constraint)
"""
import pytest
from fastapi.testclient import TestClient

from backend.db.setup import insert_payment_event, get_connection


@pytest.fixture()
def client(db_path):
    """TestClient against the real FastAPI app using a test DB."""
    import os
    os.environ["DB_PATH"] = db_path
    os.environ["USE_MOCK"] = "true"
    from backend.api.app import app
    return TestClient(app)


def _insert_test_event(db_path: str, **overrides) -> None:
    """Helper: insert a payment_event directly into the DB."""
    conn = get_connection(db_path)
    defaults = dict(
        event_id="pe-api-001",
        source_message_id="msg-api-001",
        source_provider="MOCK",
        source_account_id="mock_default",
        event_type="subscription_charge",
        amount=9.99,
        currency="USD",
        merchant_name="Spotify",
        event_date="2026-01-15T00:00:00Z",
        is_recurring_candidate=1,
        is_one_time_candidate=0,
        subscription_id=None,
        confidence_score=0.85,
    )
    defaults.update(overrides)
    insert_payment_event(conn, **defaults)
    conn.commit()
    conn.close()


def test_get_payment_events_returns_200(client):
    """GET /api/payment-events must return 200 and a list (empty is OK)."""
    response = client.get("/api/payment-events")
    assert response.status_code == 200, (
        f"GET /api/payment-events must return 200. Got {response.status_code}. "
        f"Ensure backend/api/routers/payment_events.py is created and registered in app.py."
    )
    data = response.json()
    assert isinstance(data, list), f"Response must be a JSON list, got {type(data)}"


def test_get_payment_events_with_data(client, db_path):
    """GET /api/payment-events returns events after inserting one."""
    _insert_test_event(db_path)
    response = client.get("/api/payment-events")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1, f"Expected 1 event, got {len(data)}"
    ev = data[0]
    assert ev["merchant_name"] == "Spotify"
    assert ev["event_type"] == "subscription_charge"
    assert ev["amount"] == pytest.approx(9.99)
    assert ev["currency"] == "USD"


def test_get_payment_events_safe_fields_only(client, db_path):
    """Response must not contain any raw email content fields.

    Privacy: payment_events table stores no subject, sender_address, snippet,
    body_text, body_html, or short_evidence. These must not appear in API responses.
    """
    _insert_test_event(db_path)
    response = client.get("/api/payment-events")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1

    forbidden_fields = {
        "subject", "sender_address", "snippet", "body_text",
        "body_html", "short_evidence", "raw_body", "payload",
    }
    ev_keys = set(data[0].keys())
    present_forbidden = forbidden_fields & ev_keys
    assert not present_forbidden, (
        f"GET /api/payment-events must not expose raw email content. "
        f"Found forbidden fields in response: {present_forbidden}"
    )


def test_get_payment_events_filter_by_event_type(client, db_path):
    """?event_type=renewal_charge filters response to matching events only."""
    _insert_test_event(db_path, event_id="pe-filter-001", source_message_id="msg-f-001",
                       event_type="subscription_charge")
    _insert_test_event(db_path, event_id="pe-filter-002", source_message_id="msg-f-002",
                       event_type="renewal_charge")
    _insert_test_event(db_path, event_id="pe-filter-003", source_message_id="msg-f-003",
                       event_type="refund", amount=9.99)

    response = client.get("/api/payment-events?event_type=renewal_charge")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1, f"Filter should return 1 renewal_charge event, got {len(data)}"
    assert data[0]["event_type"] == "renewal_charge"


def test_get_payment_events_renewal_charge_accepted(client, db_path):
    """'renewal_charge' event_type must be accepted by the schema (migration 007).

    Phase 3.3 only had 'subscription_charge'. Migration 007 adds 'renewal_charge'.
    If this test fails with a DB constraint error, migration 007 was not applied.
    """
    _insert_test_event(db_path,
                       event_id="pe-renewal-api-001",
                       source_message_id="msg-renewal-api-001",
                       event_type="renewal_charge")

    response = client.get("/api/payment-events")
    assert response.status_code == 200
    data = response.json()
    renewal_events = [e for e in data if e["event_type"] == "renewal_charge"]
    assert len(renewal_events) == 1, (
        f"'renewal_charge' must be stored and returned. "
        f"If DB error occurred, check migration 007 applied 'renewal_charge' to CHECK constraint."
    )


def test_get_payment_events_recurring_filter(client, db_path):
    """?is_recurring_candidate=1 returns only recurring candidates."""
    _insert_test_event(db_path, event_id="pe-rec-001", source_message_id="msg-rec-001",
                       is_recurring_candidate=1)
    _insert_test_event(db_path, event_id="pe-nonrec-001", source_message_id="msg-nonrec-001",
                       is_recurring_candidate=0)

    response = client.get("/api/payment-events?is_recurring_candidate=1")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["is_recurring_candidate"] == 1
