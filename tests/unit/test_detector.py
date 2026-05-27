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


def test_trial_end_creates_trial_subscription(conn):
    """TRIAL_END on a brand-new subscription creates it with status=TRIAL, not ACTIVE."""
    email = _make_email("t004", "no-reply@figma.com",
                        "Your Figma Professional trial is ending soon - $15.00/month")
    result = process_email(conn, email)
    assert result.disposition == "DETECTED"
    subs = get_subscriptions(conn)
    assert any(s["name"] == "Figma" and s["status"] == "TRIAL" for s in subs)


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


# ---------------------------------------------------------------------------
# Phase 1.2: event_type and lifecycle date tests
# ---------------------------------------------------------------------------

def test_receipt_event_type_is_subscription_started(conn):
    """First receipt for a service → event_type 'subscription_started'."""
    email = _make_email("t008", "billing@account.netflix.com",
                        "Your Netflix membership receipt - $15.49")
    result = process_email(conn, email)
    assert result.event_type == "subscription_started"
    records = get_email_records(conn)
    assert records[0]["event_type"] == "subscription_started"


def test_second_receipt_is_renewal_charge(conn):
    """Second receipt for the same service → event_type 'renewal_charge'."""
    first = _make_email("t009a", "billing@account.netflix.com",
                        "Your Netflix membership receipt - $15.49", "2025-04-01T08:00:00Z")
    second = _make_email("t009b", "billing@account.netflix.com",
                         "Your Netflix membership receipt - $15.49", "2025-05-01T08:00:00Z")
    process_email(conn, first)
    result = process_email(conn, second)
    assert result.event_type == "renewal_charge"
    records = get_email_records(conn)
    renewal_records = [r for r in records if r["event_type"] == "renewal_charge"]
    assert len(renewal_records) == 1


def test_cancellation_sets_cancelled_at(conn):
    """Processing a cancellation email populates cancelled_at on the subscription row."""
    receipt = _make_email("t010a", "billing@account.netflix.com",
                          "Your Netflix receipt - $15.49", "2025-04-01T08:00:00Z")
    cancel = _make_email("t010b", "billing@account.netflix.com",
                         "Your Netflix subscription has been cancelled", "2025-05-01T08:00:00Z")
    process_email(conn, receipt)
    process_email(conn, cancel)

    subs = get_subscriptions(conn)
    netflix = [s for s in subs if s["name"] == "Netflix"][0]
    assert netflix["cancelled_at"] is not None, "cancelled_at must be set after cancellation email"


def test_cancellation_event_type(conn):
    """Cancellation email → event_type 'cancellation' on the email record."""
    receipt = _make_email("t011a", "billing@account.netflix.com",
                          "Your Netflix receipt - $15.49", "2025-04-01T08:00:00Z")
    cancel = _make_email("t011b", "billing@account.netflix.com",
                         "Your Netflix subscription has been cancelled", "2025-05-01T08:00:00Z")
    process_email(conn, receipt)
    result = process_email(conn, cancel)
    assert result.event_type == "cancellation"


def test_trial_started_sets_trial_status(conn):
    """TRIAL_STARTED email creates subscription with status='TRIAL' and event_type 'trial_started'."""
    email = _make_email("t012", "noreply@github.com",
                        "You've started a free trial of GitHub Copilot")
    result = process_email(conn, email)
    assert result.disposition == "DETECTED"
    assert result.event_type == "trial_started"
    subs = get_subscriptions(conn)
    github = [s for s in subs if s["name"] == "GitHub"][0]
    assert github["status"] == "TRIAL"


def test_first_charge_date_set_on_receipt(conn):
    """After a receipt, first_charge_date must be populated on the subscription."""
    email = _make_email("t013", "billing@account.netflix.com",
                        "Your Netflix membership receipt - $15.49")
    process_email(conn, email)
    subs = get_subscriptions(conn)
    netflix = [s for s in subs if s["name"] == "Netflix"][0]
    assert netflix["first_charge_date"] is not None, "first_charge_date must be set on first receipt"


def test_short_evidence_stored_on_receipt(conn):
    """A receipt email must produce a non-null short_evidence starting with 'New subscription'."""
    email = _make_email("t014", "billing@account.netflix.com",
                        "Your Netflix membership receipt - $15.49")
    process_email(conn, email)
    records = get_email_records(conn)
    assert records[0]["short_evidence"] is not None
    assert records[0]["short_evidence"].startswith("New subscription")


def test_refund_pattern_detected(conn):
    """Refund subject on a Tier 1 domain → DETECTED with event_type 'refund'."""
    email = _make_email("t015", "billing@account.netflix.com",
                        "We've issued a refund of $15.49 to your account")
    result = process_email(conn, email)
    assert result.disposition == "DETECTED"
    assert result.event_type == "refund"


def test_failed_payment_pattern_detected(conn):
    """Failed-payment subject on a Tier 1 domain → DETECTED with event_type 'failed_payment'."""
    email = _make_email("t016", "no-reply@spotify.com",
                        "Action required: payment failed for your Spotify Premium subscription")
    result = process_email(conn, email)
    assert result.disposition == "DETECTED"
    assert result.event_type == "failed_payment"


# ---------------------------------------------------------------------------
# Phase 2.4C: lifecycle date MIN/MAX semantics test
# ---------------------------------------------------------------------------

def test_lifecycle_dates_correct_when_emails_newest_first(conn):
    """Gmail processes emails newest-first. first_charge_date must be the oldest date
    (MIN semantics) and last_charge_date must be the newest date (MAX semantics),
    regardless of processing order."""
    # Simulate Gmail newest-first: May 22 email processed before March 20
    newer = _make_email(
        "t017a", "billing@account.netflix.com",
        "Your Netflix membership receipt - $15.49",
        "2025-05-22T10:00:00Z",
    )
    older = _make_email(
        "t017b", "billing@account.netflix.com",
        "Your Netflix membership receipt - $15.49",
        "2025-03-20T10:00:00Z",
    )

    process_email(conn, newer)  # processed first (newest-first order)
    process_email(conn, older)  # processed second

    subs = get_subscriptions(conn)
    netflix = [s for s in subs if s["name"] == "Netflix"][0]

    assert netflix["first_charge_date"].startswith("2025-03-20"), (
        f"first_charge_date should be 2025-03-20 (MIN = oldest charge), "
        f"got {netflix['first_charge_date']}"
    )
    assert netflix["last_charge_date"].startswith("2025-05-22"), (
        f"last_charge_date should be 2025-05-22 (MAX = most recent charge), "
        f"got {netflix['last_charge_date']}"
    )
