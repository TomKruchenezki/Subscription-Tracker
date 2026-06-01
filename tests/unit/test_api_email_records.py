"""
Tests for Phase 3.5 email records dismiss endpoint.

Verifies:
- POST /api/email-records/{record_id}/dismiss → 200, DB persisted
- GET  /api/email-records/dismissed-ids → list of dismissed IDs
- GET  /api/email-records excludes user_dismissed=1 by default
- GET  /api/email-records?include_dismissed=true includes them
- POST /api/email-records/{nonexistent}/dismiss → 404
"""
import pytest
import sqlite3
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


def _insert_email_record(db_path: str, record_id: str = "rec-001") -> str:
    """Insert a minimal email_record for testing."""
    conn = sqlite3.connect(db_path)
    conn.execute("""
        INSERT OR IGNORE INTO email_records
            (record_id, source_message_id, source_provider, source_account_id,
             source_account_email, sender_address, subject, email_date,
             confidence_score, disposition)
        VALUES (?, ?, 'MOCK', 'mock_default', 'demo@mock.local',
                'billing@test.com', 'Test receipt', '2026-01-01T00:00:00Z',
                0.75, 'FLAGGED')
    """, (record_id, f"msg-{record_id}"))
    conn.commit()
    conn.close()
    return record_id


# ── POST /api/email-records/{id}/dismiss ──────────────────────────────────────

def test_dismiss_endpoint_returns_200(client, db_path):
    """POST /api/email-records/{id}/dismiss → 200 with dismissed=true."""
    record_id = _insert_email_record(db_path)
    response = client.post(f"/api/email-records/{record_id}/dismiss")
    assert response.status_code == 200, (
        f"POST /api/email-records/{{id}}/dismiss must return 200, "
        f"got {response.status_code}: {response.text}"
    )
    data = response.json()
    assert data["record_id"] == record_id
    assert data["dismissed"] is True


def test_dismiss_endpoint_persists_to_db(client, db_path):
    """After dismiss, email_records.user_dismissed=1 in DB."""
    record_id = _insert_email_record(db_path, "rec-persist-001")
    client.post(f"/api/email-records/{record_id}/dismiss")

    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT user_dismissed FROM email_records WHERE record_id = ?", (record_id,)
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == 1, (
        f"user_dismissed must be 1 after dismiss, got {row[0]}"
    )


def test_dismiss_inserts_correction_entry(client, db_path):
    """Dismiss should insert a DISMISSED_EMAIL entry in user_corrections."""
    record_id = _insert_email_record(db_path, "rec-correction-001")
    client.post(f"/api/email-records/{record_id}/dismiss")

    conn = get_connection(db_path)
    # Check if user_corrections table exists (migration 009)
    has_table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='user_corrections'"
    ).fetchone()
    if has_table:
        row = conn.execute(
            "SELECT correction_type FROM user_corrections WHERE email_record_id = ?",
            (record_id,),
        ).fetchone()
        conn.close()
        assert row is not None, "DISMISSED_EMAIL correction must be inserted"
        assert row[0] == "DISMISSED_EMAIL"
    else:
        conn.close()
        pytest.skip("user_corrections table not present (migration 009 not applied)")


def test_dismiss_nonexistent_record_returns_404(client):
    """POST /api/email-records/{nonexistent}/dismiss → 404."""
    response = client.post("/api/email-records/rec-does-not-exist/dismiss")
    assert response.status_code == 404, (
        f"Dismissing a nonexistent record must return 404, got {response.status_code}"
    )


def test_dismiss_is_idempotent(client, db_path):
    """Dismissing the same record twice should still return 200 (idempotent)."""
    record_id = _insert_email_record(db_path, "rec-idempotent-001")
    resp1 = client.post(f"/api/email-records/{record_id}/dismiss")
    resp2 = client.post(f"/api/email-records/{record_id}/dismiss")
    assert resp1.status_code == 200
    assert resp2.status_code == 200  # second dismiss is also OK


# ── GET /api/email-records/dismissed-ids ──────────────────────────────────────

def test_get_dismissed_ids_returns_list(client, db_path):
    """GET /api/email-records/dismissed-ids → JSON list."""
    response = client.get("/api/email-records/dismissed-ids")
    assert response.status_code == 200, (
        f"GET /api/email-records/dismissed-ids must return 200, "
        f"got {response.status_code}: {response.text}"
    )
    data = response.json()
    assert isinstance(data, list), f"Must return a list, got {type(data)}"


def test_get_dismissed_ids_contains_dismissed_record(client, db_path):
    """After dismissing, ID appears in GET /api/email-records/dismissed-ids."""
    record_id = _insert_email_record(db_path, "rec-dismissed-ids-001")
    client.post(f"/api/email-records/{record_id}/dismiss")

    response = client.get("/api/email-records/dismissed-ids")
    assert response.status_code == 200
    data = response.json()
    assert record_id in data, (
        f"Dismissed record {record_id!r} must appear in /dismissed-ids, got {data}"
    )


# ── GET /api/email-records (include_dismissed filter) ─────────────────────────

def test_email_records_excludes_dismissed_by_default(client, db_path):
    """GET /api/email-records by default excludes user_dismissed=1 records."""
    record_id = _insert_email_record(db_path, "rec-exclude-001")

    # Verify it appears before dismiss
    before = client.get("/api/email-records").json()
    assert any(r["record_id"] == record_id for r in before), (
        "Record must appear in email-records before dismiss"
    )

    # Dismiss it
    client.post(f"/api/email-records/{record_id}/dismiss")

    # Verify it's excluded by default
    after = client.get("/api/email-records").json()
    assert not any(r["record_id"] == record_id for r in after), (
        "Dismissed record must NOT appear in GET /api/email-records by default"
    )


def test_email_records_include_dismissed_flag(client, db_path):
    """GET /api/email-records?include_dismissed=true includes dismissed records."""
    record_id = _insert_email_record(db_path, "rec-include-001")
    client.post(f"/api/email-records/{record_id}/dismiss")

    response = client.get("/api/email-records?include_dismissed=true")
    assert response.status_code == 200
    data = response.json()
    assert any(r["record_id"] == record_id for r in data), (
        "Dismissed record must appear when include_dismissed=true"
    )


def test_email_records_dismissed_field_in_response(client, db_path):
    """GET /api/email-records response includes user_dismissed field."""
    record_id = _insert_email_record(db_path, "rec-field-001")

    # Before dismiss: user_dismissed=0
    before = client.get("/api/email-records").json()
    rec_before = next((r for r in before if r["record_id"] == record_id), None)
    assert rec_before is not None
    assert rec_before.get("user_dismissed", 0) == 0

    # After dismiss: should have user_dismissed=1 (if include_dismissed=true)
    client.post(f"/api/email-records/{record_id}/dismiss")
    after = client.get("/api/email-records?include_dismissed=true").json()
    rec_after = next((r for r in after if r["record_id"] == record_id), None)
    assert rec_after is not None
    assert rec_after.get("user_dismissed") == 1, (
        f"user_dismissed must be 1 after dismiss, got {rec_after.get('user_dismissed')}"
    )
