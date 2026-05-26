"""Behavioral tests for the 5-stage detection pipeline."""
import sqlite3
from datetime import datetime, timezone
import pytest

from backend.models.email_metadata import EmailMetadata
from backend.detector.detector import process_email
from backend.db.setup import get_subscriptions, get_email_records


def _make_email(message_id, sender, subject, date_str="2025-05-01T08:00:00Z"):
    return EmailMetadata(
        source_message_id=message_id,
        source_provider="MOCK",
        source_account_id="mock_default",
        source_account_email="demo@mock.local",
        sender_address=sender,
        sender_name=None,
        subject=subject,
        email_date=datetime.fromisoformat(date_str.replace("Z", "+00:00")),
    )


@pytest.fixture
def conn(db_path):
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    yield c
    c.close()


def test_detected_receipt_creates_subscription(conn):
    email = _make_email("t001", "billing@account.netflix.com",
                        "Your Netflix membership receipt - $15.49")
    result = process_email(conn, email)
    assert result.disposition == "DETECTED"
    subs = get_subscriptions(conn)
    assert len(subs) == 1
    assert subs[0]["name"] == "Netflix"


def test_duplicate_message_id_not_double_stored(conn):
    email = _make_email("t002", "billing@account.netflix.com",
                        "Your Netflix receipt - $15.49")
    process_email(conn, email)
    process_email(conn, email)  # same source_message_id
    records = get_email_records(conn)
    assert len(records) == 1, "Duplicate source_message_id must not create a second email_record"


def test_cancellation_updates_subscription_status(conn):
    # First, create the subscription via a receipt
    receipt = _make_email("t003a", "billing@account.netflix.com",
                           "Your Netflix receipt - $15.49", "2025-04-01T08:00:00Z")
    process_email(conn, receipt)

    # Then process a cancellation
    cancel = _make_email("t003b", "billing@account.netflix.com",
                          "Your Netflix subscription has been cancelled", "2025-05-01T08:00:00Z")
    process_email(conn, cancel)

    subs = get_subscriptions(conn)
    netflix_subs = [s for s in subs if s["name"] == "Netflix"]
    assert len(netflix_subs) == 1
    assert netflix_subs[0]["status"] == "CANCELLED"


def test_trial_end_creates_active_subscription(conn):
    email = _make_email("t004", "no-reply@figma.com",
                        "Your Figma Professional trial is ending soon - $15.00/month")
    result = process_email(conn, email)
    assert result.disposition == "DETECTED"
    subs = get_subscriptions(conn)
    assert any(s["name"] == "Figma" and s["status"] == "ACTIVE" for s in subs)


def test_amazon_com_not_detected(conn):
    """amazon.com is excluded — one-time purchases should never be subscriptions."""
    email = _make_email("t005", "no-reply@amazon.com",
                        "Your Amazon.com order receipt - $29.99")
    result = process_email(conn, email)
    assert result.disposition == "IGNORED"
    assert len(get_subscriptions(conn)) == 0


def test_primevideo_com_is_detected(conn):
    """primevideo.com is Tier 1 — distinct from amazon.com."""
    email = _make_email("t006", "noreply@primevideo.com",
                        "Your Amazon Prime Video receipt - $8.99")
    result = process_email(conn, email)
    assert result.disposition == "DETECTED"
    subs = get_subscriptions(conn)
    assert any(s["name"] == "Amazon Prime Video" for s in subs)


def test_flagged_email_stores_record_but_no_subscription(conn):
    """Unknown domain + receipt pattern → FLAGGED: email_record stored, no subscription row."""
    email = _make_email("t007", "billing@claritydesk.io",
                        "Your Claritydesk receipt - $29.00")
    result = process_email(conn, email)
    assert result.disposition == "FLAGGED"
    assert result.subscription_id is None
    assert len(get_subscriptions(conn)) == 0
    records = get_email_records(conn, disposition="FLAGGED")
    assert len(records) == 1
    assert records[0]["subscription_id"] is None
