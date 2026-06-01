"""
Phase 3.7: user corrections must govern PDF-derived candidates too.

Because PDF evidence rides on the same email_record / payment_event / subscription that
the Phase 3.6 correction system already governs, these tests confirm corrections are not
bypassed when the amount/cycle came from a PDF:
  - rejected sender → no subscription recreated (even with strong PDF evidence)
  - relabel → corrected name used for PDF-derived rows
  - confirmed subscription → never downgraded
  - marked one-time → not resubscribed on reprocess
  - dismissed → skipped on reprocess
"""
import uuid
from datetime import datetime, timezone

import pytest

from backend.db.setup import get_connection, insert_user_correction, mark_one_time
from backend.detector.detector import process_email
from backend.models.email_metadata import EmailMetadata
from backend.parser.pdf_extractor import extract_pdf_fields
from tests.fixtures.pdf_factory import make_text_pdf

_RECURRING_PDF = [
    "Spotify", "Billing Period: 2026-01-01 to 2026-01-31",
    "Your subscription auto-renews monthly.", "Total Amount Due: 19.90 ILS",
]


def _pdf_email(sender, subject, lines, msg_id="m1"):
    pdf = make_text_pdf(lines)
    ev = extract_pdf_fields(pdf)
    att = {
        "filename": "invoice.pdf", "mime_type": "application/pdf", "size_bytes": len(pdf),
        "gmail_attachment_id": "a1", "detected_attachment_type": "PDF_INVOICE",
        "processing_status": "PARSED", "evidence": ev,
    }
    return EmailMetadata(
        source_message_id=msg_id, source_provider="GMAIL", source_account_id="A",
        source_account_email="me@x.com", sender_address=sender, sender_name=None,
        subject=subject, email_date=datetime(2026, 1, 15, tzinfo=timezone.utc),
        attachments=[att],
    )


@pytest.fixture
def conn(db_path):
    c = get_connection(db_path)
    yield c
    c.close()


def test_blocked_sender_not_recreated_with_pdf(conn):
    insert_user_correction(
        conn, correction_id=str(uuid.uuid4()), email_record_id=None, subscription_id=None,
        correction_type="REJECTED_SUB", sender_address="receipts@spotify.com",
    )
    conn.commit()
    res = process_email(conn, _pdf_email("receipts@spotify.com", "Your Spotify receipt", _RECURRING_PDF))
    assert res.disposition == "FLAGGED"
    assert conn.execute("SELECT COUNT(*) FROM subscriptions WHERE name='Spotify'").fetchone()[0] == 0


def test_relabel_applies_to_pdf_email(conn):
    insert_user_correction(
        conn, correction_id=str(uuid.uuid4()), email_record_id=None, subscription_id=None,
        correction_type="RELABELED", new_value="Spotify Family", sender_address="receipts@spotify.com",
    )
    conn.commit()
    res = process_email(conn, _pdf_email("receipts@spotify.com", "Your Spotify receipt", _RECURRING_PDF))
    assert res.canonical_name == "Spotify Family"
    assert conn.execute("SELECT COUNT(*) FROM subscriptions WHERE name='Spotify Family'").fetchone()[0] == 1


def test_confirmed_pdf_subscription_not_downgraded(conn):
    process_email(conn, _pdf_email("receipts@spotify.com", "Your Spotify receipt", _RECURRING_PDF))
    sub = conn.execute("SELECT detection_state FROM subscriptions WHERE name='Spotify'").fetchone()
    assert sub["detection_state"] == "CONFIRMED_ACTIVE"

    weak = EmailMetadata(
        source_message_id="m2", source_provider="GMAIL", source_account_id="A",
        source_account_email="me@x.com", sender_address="receipts@spotify.com", sender_name=None,
        subject="Your Spotify subscription", email_date=datetime(2026, 2, 15, tzinfo=timezone.utc),
    )
    process_email(conn, weak)
    sub2 = conn.execute("SELECT detection_state FROM subscriptions WHERE name='Spotify'").fetchone()
    assert sub2["detection_state"] == "CONFIRMED_ACTIVE"  # upgrade-only — never downgraded


def test_marked_one_time_pdf_not_resubscribed_on_reprocess(db_path):
    from scripts.reprocess_email_records import reprocess

    conn = get_connection(db_path)
    process_email(conn, _pdf_email("receipts@spotify.com", "Your Spotify receipt", _RECURRING_PDF))
    conn.commit()
    rec = conn.execute("SELECT record_id FROM email_records WHERE source_message_id='m1'").fetchone()
    pe = conn.execute("SELECT event_id FROM payment_events WHERE source_message_id='m1'").fetchone()
    assert conn.execute("SELECT COUNT(*) FROM subscriptions WHERE name='Spotify'").fetchone()[0] == 1

    # User marks the event one-time and removes the wrongly-created subscription.
    # Null the FK links first (as the delete API does) so the email_record survives
    # — a raw subscription delete would cascade and remove the audit record.
    mark_one_time(
        conn, email_record_id=rec["record_id"],
        payment_event_id=pe["event_id"] if pe else None,
        sender_address="receipts@spotify.com",
    )
    conn.execute(
        "UPDATE email_records SET subscription_id=NULL "
        "WHERE subscription_id IN (SELECT subscription_id FROM subscriptions WHERE name='Spotify')"
    )
    conn.execute(
        "UPDATE payment_events SET subscription_id=NULL "
        "WHERE subscription_id IN (SELECT subscription_id FROM subscriptions WHERE name='Spotify')"
    )
    conn.execute("DELETE FROM subscriptions WHERE name='Spotify'")
    conn.commit()
    conn.close()

    reprocess(db_path=db_path, dry_run=False)

    conn = get_connection(db_path)
    # Subscription must NOT be recreated, and no recurring candidate may remain.
    assert conn.execute("SELECT COUNT(*) FROM subscriptions WHERE name='Spotify'").fetchone()[0] == 0
    recurring = conn.execute(
        "SELECT COUNT(*) FROM payment_events WHERE source_message_id='m1' AND is_recurring_candidate=1"
    ).fetchone()[0]
    assert recurring == 0
    conn.close()


def test_dismissed_pdf_record_skipped_on_reprocess(db_path):
    from scripts.reprocess_email_records import reprocess

    conn = get_connection(db_path)
    process_email(conn, _pdf_email("receipts@spotify.com", "Your Spotify receipt", _RECURRING_PDF))
    conn.commit()
    # Sentinel: if reprocess skips this record, payment_events are NOT deleted/recreated.
    conn.execute("UPDATE payment_events SET confidence_score=0.999 WHERE source_message_id='m1'")
    conn.execute("UPDATE email_records SET user_dismissed=1 WHERE source_message_id='m1'")
    conn.commit()
    conn.close()

    reprocess(db_path=db_path, dry_run=False)

    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT confidence_score FROM payment_events WHERE source_message_id='m1'"
    ).fetchone()
    assert row is not None and row["confidence_score"] == pytest.approx(0.999), (
        "dismissed record's payment_events should be left untouched by reprocess"
    )
    conn.close()
