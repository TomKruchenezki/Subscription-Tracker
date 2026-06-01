"""
Phase 3.7 API tests: attachment detail endpoint + has_attachment flag on email records.

Verifies:
- GET /api/email-records/{id}/attachments returns safe structured attachment + PDF fields
- GET /api/email-records sets has_attachment=true for records with attachments
- the response carries no raw PDF text and includes the account alias
"""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.db.setup import get_connection, insert_attachment, insert_attachment_fields


@pytest.fixture()
def client(db_path):
    import os
    os.environ["DB_PATH"] = db_path
    os.environ["USE_MOCK"] = "true"
    from backend.api.app import app
    return TestClient(app)


def _seed_record_with_attachment(db_path: str, record_id: str = "rec-att-1") -> str:
    conn = get_connection(db_path)
    conn.execute(
        """INSERT OR IGNORE INTO email_records
               (record_id, source_message_id, source_provider, source_account_id,
                source_account_email, sender_address, subject, email_date,
                confidence_score, disposition)
           VALUES (?, ?, 'MOCK', 'acctA', 'me@mock.local', 'receipts@spotify.com',
                   'Your Spotify receipt', '2026-01-15T00:00:00Z', 0.8, 'DETECTED')""",
        (record_id, f"msg-{record_id}"),
    )
    row_id = insert_attachment(
        conn, email_record_id=record_id, source_message_id=f"msg-{record_id}",
        source_account_id="acctA", gmail_attachment_id="att-1", filename="invoice.pdf",
        mime_type="application/pdf", size_bytes=2048, detected_attachment_type="PDF_INVOICE",
        processing_status="PARSED", parser_version="pdf-1.0",
    )
    insert_attachment_fields(
        conn, attachment_row_id=row_id, email_record_id=record_id,
        source_message_id=f"msg-{record_id}", provider="Spotify", amount=19.90,
        currency="ILS", inferred_cycle="MONTHLY",
        evidence_reasons="amount_in_pdf;billing_period_found",
        confidence_score=0.65, extraction_status="OK", parser_version="pdf-1.0",
    )
    conn.commit()
    conn.close()
    return record_id


def test_attachments_endpoint_returns_structured_fields(client, db_path):
    record_id = _seed_record_with_attachment(db_path)
    resp = client.get(f"/api/email-records/{record_id}/attachments")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data) == 1
    att = data[0]
    assert att["filename"] == "invoice.pdf"
    assert att["detected_attachment_type"] == "PDF_INVOICE"
    assert att["processing_status"] == "PARSED"
    fields = att["extracted_fields"]
    assert fields is not None
    assert fields["amount"] == 19.90
    assert fields["currency"] == "ILS"
    assert fields["inferred_cycle"] == "MONTHLY"
    assert "amount_in_pdf" in fields["evidence_reasons"]


def test_attachments_endpoint_no_raw_text_keys(client, db_path):
    """Response must not expose any raw-text/body/snippet field."""
    record_id = _seed_record_with_attachment(db_path, "rec-att-2")
    resp = client.get(f"/api/email-records/{record_id}/attachments")
    data = resp.json()
    keys = set(data[0].keys()) | set((data[0]["extracted_fields"] or {}).keys())
    prohibited = {"body", "html", "raw", "content", "full", "snippet", "payload",
                  "text", "pdf_text", "extracted_text"}
    assert keys.isdisjoint(prohibited), f"attachment response exposes raw-content keys: {keys & prohibited}"


def test_email_records_has_attachment_flag(client, db_path):
    record_id = _seed_record_with_attachment(db_path, "rec-att-3")
    resp = client.get("/api/email-records")
    assert resp.status_code == 200
    recs = {r["record_id"]: r for r in resp.json()}
    assert record_id in recs
    assert recs[record_id]["has_attachment"] is True
    assert recs[record_id]["account_alias"]  # privacy-safe account alias present


def test_email_records_without_attachment_flag_false(client, db_path):
    conn = get_connection(db_path)
    conn.execute(
        """INSERT OR IGNORE INTO email_records
               (record_id, source_message_id, source_provider, source_account_id,
                source_account_email, sender_address, subject, email_date,
                confidence_score, disposition)
           VALUES ('rec-noatt', 'msg-noatt', 'MOCK', 'acctA', 'me@mock.local',
                   'x@test.com', 'No attachment here', '2026-01-15T00:00:00Z', 0.8, 'FLAGGED')""",
    )
    conn.commit()
    conn.close()
    resp = client.get("/api/email-records")
    recs = {r["record_id"]: r for r in resp.json()}
    assert recs["rec-noatt"]["has_attachment"] is False
