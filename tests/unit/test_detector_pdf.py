"""
Phase 3.7: detector integration with PDF-derived evidence.

Verifies that a parsed PDF can supply a missing amount, that attachment rows are
persisted (structured only), that the receipt-only guardrail holds (a bare receipt
never becomes CONFIRMED), and that persistence is idempotent / skippable.
"""
from datetime import datetime, timezone

import pytest

from backend.db.setup import get_connection
from backend.detector.detector import process_email
from backend.models.email_metadata import EmailMetadata
from backend.parser.pdf_extractor import extract_pdf_fields
from tests.fixtures.pdf_factory import make_text_pdf


def _email(sender, subject, pdf_lines, *, msg_id="m1", account="acctA",
           detected_type="PDF_INVOICE", status="PARSED"):
    pdf = make_text_pdf(pdf_lines)
    ev = extract_pdf_fields(pdf)
    att = {
        "filename": "invoice.pdf", "mime_type": "application/pdf",
        "size_bytes": len(pdf), "gmail_attachment_id": "att-1",
        "detected_attachment_type": detected_type, "processing_status": status,
        "evidence": ev,
    }
    return EmailMetadata(
        source_message_id=msg_id, source_provider="GMAIL", source_account_id=account,
        source_account_email="me@gmail.com", sender_address=sender, sender_name=None,
        subject=subject, email_date=datetime(2026, 1, 15, tzinfo=timezone.utc),
        attachments=[att],
    )


@pytest.fixture
def conn(db_path):
    c = get_connection(db_path)
    yield c
    c.close()


def test_pdf_supplies_missing_amount(conn):
    """Subject has no amount; the PDF invoice provides it."""
    email = _email(
        "receipts@spotify.com", "Your Spotify receipt",
        ["Spotify", "Billing Period: 2026-01-01 to 2026-01-31",
         "Your subscription auto-renews monthly.", "Total Amount Due: 19.90 ILS"],
    )
    process_email(conn, email)
    row = conn.execute(
        "SELECT amount_extracted, currency_extracted, detection_state, evidence_summary "
        "FROM email_records WHERE source_message_id='m1'"
    ).fetchone()
    assert row["amount_extracted"] == 19.90
    assert row["currency_extracted"] == "ILS"
    assert "amount from PDF invoice" in (row["evidence_summary"] or "")


def test_pdf_attachment_rows_persisted(conn):
    email = _email(
        "receipts@spotify.com", "Your Spotify receipt",
        ["Spotify", "Billing Period: 2026-01-01 to 2026-01-31",
         "auto-renews monthly subscription", "Total Amount Due: 19.90 ILS"],
    )
    process_email(conn, email)
    att = conn.execute("SELECT * FROM email_attachments").fetchall()
    assert len(att) == 1
    assert att[0]["detected_attachment_type"] == "PDF_INVOICE"
    assert att[0]["processing_status"] == "PARSED"
    fields = conn.execute("SELECT * FROM attachment_extracted_fields").fetchall()
    assert len(fields) == 1
    assert fields[0]["amount"] == 19.90
    assert fields[0]["inferred_cycle"] == "MONTHLY"
    assert "amount_in_pdf" in (fields[0]["evidence_reasons"] or "")


def test_pdf_with_recurring_evidence_can_confirm(conn):
    """Billing period + recurring wording → genuine recurring evidence → CONFIRMED."""
    email = _email(
        "receipts@spotify.com", "Your Spotify receipt",
        ["Spotify", "Billing Period: 2026-01-01 to 2026-01-31",
         "Your subscription auto-renews monthly.", "Total Amount Due: 19.90 ILS"],
    )
    process_email(conn, email)
    row = conn.execute(
        "SELECT detection_state FROM email_records WHERE source_message_id='m1'"
    ).fetchone()
    assert row["detection_state"] == "CONFIRMED_SUBSCRIPTION"


def test_receipt_only_pdf_not_confirmed(conn):
    """A bare receipt (amount, no cycle/recurring) must NOT reach CONFIRMED."""
    email = _email(
        "receipts@spotify.com", "Your receipt",
        ["Spotify", "Receipt", "Total: 9.99 USD"],
    )
    process_email(conn, email)
    row = conn.execute(
        "SELECT detection_state FROM email_records WHERE source_message_id='m1'"
    ).fetchone()
    assert row["detection_state"] != "CONFIRMED_SUBSCRIPTION"
    fields = conn.execute(
        "SELECT penalty_reasons FROM attachment_extracted_fields"
    ).fetchone()
    assert "receipt_one_time_no_recurring" in (fields["penalty_reasons"] or "")


def test_refund_pdf_does_not_fill_charge_amount(conn):
    """A refund PDF must not be treated as a subscription charge amount.

    Uses a Tier-1 sender + receipt subject (so the email is stored) whose attached PDF
    is a refund — the refund amount must NOT be used to fill the charge amount, and the
    refund penalty must be recorded on the structured evidence row.
    """
    email = _email(
        "receipts@spotify.com", "Your Spotify receipt",
        ["Spotify", "Refund issued to your card", "Total refunded: 30.00 USD"],
    )
    process_email(conn, email)
    row = conn.execute(
        "SELECT amount_extracted, missing_evidence FROM email_records WHERE source_message_id='m1'"
    ).fetchone()
    assert row is not None
    # refund PDF amount → NOT used to fill a charge amount (subject had none)
    assert row["amount_extracted"] is None
    assert "refund" in (row["missing_evidence"] or "").lower()
    fields = conn.execute(
        "SELECT penalty_reasons FROM attachment_extracted_fields"
    ).fetchone()
    assert "refund_detected" in (fields["penalty_reasons"] or "")


def test_persist_attachments_false_skips_rows_but_uses_amount(conn):
    """Reprocess mode: amount still used for scoring, but no attachment rows inserted."""
    email = _email(
        "receipts@spotify.com", "Your Spotify receipt",
        ["Spotify", "Billing Period: 2026-01-01 to 2026-01-31",
         "subscription auto-renews monthly", "Total Amount Due: 19.90 ILS"],
    )
    process_email(conn, email, persist_attachments=False)
    row = conn.execute(
        "SELECT amount_extracted FROM email_records WHERE source_message_id='m1'"
    ).fetchone()
    assert row["amount_extracted"] == 19.90               # amount used for scoring
    assert conn.execute("SELECT COUNT(*) FROM email_attachments").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM attachment_extracted_fields").fetchone()[0] == 0


def test_rescan_does_not_duplicate_attachment_rows(conn):
    email = _email(
        "receipts@spotify.com", "Your Spotify receipt",
        ["Spotify", "Billing Period: 2026-01-01 to 2026-01-31",
         "subscription auto-renews monthly", "Total Amount Due: 19.90 ILS"],
    )
    process_email(conn, email)
    process_email(conn, email)  # same message_id again (re-scan)
    assert conn.execute("SELECT COUNT(*) FROM email_attachments").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM attachment_extracted_fields").fetchone()[0] == 1


def test_unparsed_pdf_sets_missing_evidence_note(conn):
    """A PDF that failed to parse surfaces a 'not parsed (needs review)' note."""
    pdf = make_text_pdf(["whatever"])
    att = {
        "filename": "scan.pdf", "mime_type": "application/pdf", "size_bytes": len(pdf),
        "gmail_attachment_id": "a1", "detected_attachment_type": "PDF_RECEIPT",
        "processing_status": "PARSE_FAILED", "evidence": None,
    }
    email = EmailMetadata(
        source_message_id="m1", source_provider="GMAIL", source_account_id="A",
        source_account_email="me@x.com", sender_address="receipts@spotify.com",
        sender_name=None, subject="Your Spotify receipt",
        email_date=datetime(2026, 1, 15, tzinfo=timezone.utc), attachments=[att],
    )
    process_email(conn, email)
    row = conn.execute(
        "SELECT missing_evidence FROM email_records WHERE source_message_id='m1'"
    ).fetchone()
    assert "not parsed" in (row["missing_evidence"] or "")
    # metadata row persisted even though parse failed (evidence row optional)
    assert conn.execute("SELECT COUNT(*) FROM email_attachments").fetchone()[0] == 1
