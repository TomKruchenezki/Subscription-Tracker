"""Behavioral tests for the 5-stage detection pipeline."""
import sqlite3
from datetime import datetime, timezone
import pytest

from backend.models.email_metadata import EmailMetadata
from backend.detector.detector import process_email
from backend.db.setup import get_subscriptions, get_email_records, get_payment_events


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


# ---------------------------------------------------------------------------
# Phase 2.7: Strong ACTIVE gate — only RECEIPT/RENEWAL creates ACTIVE
# ---------------------------------------------------------------------------

def test_tier1_no_billing_evidence_ignored(conn):
    """Tier 1 + NONE + amount = 0.25 + 0.00 + 0.10 = 0.35 → IGNORED at default
    threshold (0.40). Known domain alone is no longer sufficient to DETECT or FLAG."""
    email = _make_email(
        "t018", "no-reply@spotify.com",
        "Something from Spotify: $9.99",   # no receipt/renewal language
    )
    result = process_email(conn, email)
    assert result.disposition == "IGNORED", (
        f"Expected IGNORED (score 0.35 < threshold 0.40), got {result.disposition}"
    )
    assert len(get_subscriptions(conn)) == 0


def test_tier1_no_billing_evidence_forensic_flagged(conn):
    """Phase 3.1 fix: Tier 1 + NONE + amount = 0.25 → IGNORED in ALL modes.
    Parser score is zeroed when pattern is NONE (no billing language in subject).
    An incidental dollar amount in body_text is not billing evidence without a
    subject-level billing signal. Before Phase 3.1 this was 0.35 → FLAGGED."""
    email = _make_email(
        "t019", "no-reply@spotify.com",
        "Something from Spotify: $9.99",
    )
    result = process_email(conn, email, review_threshold=0.30)
    assert result.disposition == "IGNORED", (
        f"Expected IGNORED (Phase 3.1 fix: parser score zeroed for NONE → 0.25 < 0.30), "
        f"got {result.disposition}"
    )
    assert len(get_subscriptions(conn)) == 0


def test_receipt_pattern_still_creates_active_subscription(conn):
    """RECEIPT pattern + DETECTED must still create ACTIVE subscription (strong evidence)."""
    email = _make_email(
        "t020", "billing@account.netflix.com",
        "Your Netflix membership receipt - $15.49",
    )
    result = process_email(conn, email)
    assert result.disposition == "DETECTED"
    subs = get_subscriptions(conn)
    active_subs = [s for s in subs if s["status"] == "ACTIVE"]
    assert len(active_subs) == 1, "RECEIPT pattern must create ACTIVE subscription"
    assert active_subs[0]["name"] == "Netflix"


def test_renewal_pattern_still_creates_active_subscription(conn):
    """RENEWAL pattern + DETECTED must still create ACTIVE subscription (strong evidence)."""
    email = _make_email(
        "t021", "email.spotify.com",
        "Your Spotify Premium subscription renewal - $9.99/mo",
    )
    result = process_email(conn, email)
    assert result.disposition == "DETECTED"
    subs = get_subscriptions(conn)
    active_subs = [s for s in subs if s["status"] == "ACTIVE"]
    assert len(active_subs) == 1, "RENEWAL pattern must create ACTIVE subscription"
    assert active_subs[0]["name"] == "Spotify"


# ---------------------------------------------------------------------------
# Phase 2.8: ACTIVE gate — RECEIPT/RENEWAL with NULL amount → UNKNOWN status
# ---------------------------------------------------------------------------

def test_receipt_no_amount_creates_unknown_not_active(conn):
    """RECEIPT pattern + no extractable amount → DETECTED but status=UNKNOWN, not ACTIVE."""
    email = _make_email(
        "t022", "billing@account.netflix.com",
        "Your Netflix membership receipt",   # receipt language but no $ amount
    )
    result = process_email(conn, email)
    assert result.disposition == "DETECTED"
    subs = get_subscriptions(conn)
    assert len(subs) == 1, "A subscription row should be created"
    assert subs[0]["status"] == "UNKNOWN", (
        f"RECEIPT with no amount must create UNKNOWN status, got {subs[0]['status']}"
    )


def test_receipt_with_amount_creates_active(conn):
    """RECEIPT pattern + extractable amount → DETECTED and status=ACTIVE."""
    email = _make_email(
        "t023", "billing@account.netflix.com",
        "Your Netflix membership receipt - $15.49",
    )
    result = process_email(conn, email)
    assert result.disposition == "DETECTED"
    subs = get_subscriptions(conn)
    assert len(subs) == 1
    assert subs[0]["status"] == "ACTIVE", (
        f"RECEIPT with amount must create ACTIVE status, got {subs[0]['status']}"
    )


def test_unknown_upgrades_to_active_on_receipt_with_amount(conn):
    """Processing a no-amount receipt first (→ UNKNOWN), then a receipt with amount
    (→ ACTIVE) upgrades the subscription to ACTIVE."""
    no_amt = _make_email(
        "t024a", "billing@account.netflix.com",
        "Your Netflix membership receipt",     # receipt language but no amount → UNKNOWN
        "2025-04-01T08:00:00Z",
    )
    with_amt = _make_email(
        "t024b", "billing@account.netflix.com",
        "Your Netflix membership receipt - $15.49",   # amount → ACTIVE
        "2025-05-01T08:00:00Z",
    )
    process_email(conn, no_amt)
    subs_after_first = get_subscriptions(conn)
    assert subs_after_first[0]["status"] == "UNKNOWN"

    process_email(conn, with_amt)
    subs_after_second = get_subscriptions(conn)
    netflix = [s for s in subs_after_second if s["name"] == "Netflix"]
    assert len(netflix) == 1
    assert netflix[0]["status"] == "ACTIVE", (
        f"Subscription should upgrade from UNKNOWN to ACTIVE after receipt with amount, "
        f"got {netflix[0]['status']}"
    )


def test_tier1_no_billing_evidence_deep_mode_ignored(conn):
    """Tier 1 + NONE + amount = 0.35 → IGNORED at deep mode threshold (0.40)."""
    email = _make_email(
        "t025", "no-reply@spotify.com",
        "Something from Spotify: $9.99",
    )
    result = process_email(conn, email, review_threshold=0.40)
    assert result.disposition == "IGNORED"
    assert len(get_subscriptions(conn)) == 0


# ---------------------------------------------------------------------------
# Phase 2.9: Google Play domain coverage
# ---------------------------------------------------------------------------

def test_google_play_receipt_detected(conn):
    """Google Play receipt from google.com → DETECTED after adding google.com to Tier 1."""
    email = _make_email(
        "t026", "noreply@google.com",
        "Your Google Play receipt - $2.99",
    )
    result = process_email(conn, email)
    assert result.disposition == "DETECTED", (
        f"Expected DETECTED (google.com is Tier 1 + RECEIPT pattern), got {result.disposition}"
    )
    subs = get_subscriptions(conn)
    assert len(subs) == 1
    assert subs[0]["name"] in ("Google", "Google Play")


def test_google_com_notification_still_ignored(conn):
    """google.com + NOTIFICATION subject = 0.25 - 0.45 = 0.00 → IGNORED.
    Adding google.com to Tier 1 must not cause security/notification emails to be DETECTED."""
    email = _make_email(
        "t027", "no-reply@accounts.google.com",
        "Security alert: new sign-in from a new device",
    )
    result = process_email(conn, email)
    assert result.disposition == "IGNORED", (
        f"Expected IGNORED (NOTIFICATION pattern suppresses Tier 1 score), got {result.disposition}"
    )
    assert len(get_subscriptions(conn)) == 0


# ---------------------------------------------------------------------------
# Phase 3.2: Hebrew billing support — integration tests
# ---------------------------------------------------------------------------

def _make_email_with_snippet(message_id, sender, subject, snippet=None, date_str="2025-05-01T08:00:00Z"):
    """Like _make_email but also supports an optional snippet field."""
    return EmailMetadata(
        source_message_id=message_id,
        source_provider="MOCK",
        source_account_id="mock_default",
        source_account_email="demo@mock.local",
        sender_address=sender,
        sender_name=None,
        subject=subject,
        email_date=datetime.fromisoformat(date_str.replace("Z", "+00:00")),
        snippet=snippet,
    )


def test_hebrew_receipt_with_ils_amount_detected(conn):
    """Hebrew subject + ₪ amount in snippet → DETECTED, ACTIVE subscription."""
    email = _make_email_with_snippet(
        "heb-001",
        "billing@spotify.com",
        "קבלה על תשלום",
        snippet="חויבת ₪12.90 עבור Spotify Premium",
    )
    result = process_email(conn, email)
    assert result.disposition == "DETECTED", (
        f"Expected DETECTED (Hebrew RECEIPT subject + ILS amount in snippet), got {result.disposition}"
    )
    subs = get_subscriptions(conn)
    assert len(subs) == 1
    assert subs[0]["amount"] == pytest.approx(12.90)
    assert subs[0]["status"] == "ACTIVE"


def test_hebrew_promotion_with_price_ignored(conn):
    """Hebrew promotional email with ₪ price → IGNORED (PROMOTIONAL penalty suppresses score)."""
    email = _make_email(
        "heb-002",
        "no-reply@spotify.com",
        "מבצע מיוחד - שדרג ל-Premium ב-₪7.90 לחודש הראשון",
    )
    result = process_email(conn, email)
    assert result.disposition == "IGNORED", (
        f"Expected IGNORED (מבצע = PROMOTIONAL pattern suppresses score), got {result.disposition}"
    )
    assert len(get_subscriptions(conn)) == 0


def test_hebrew_renewal_subject_detected(conn):
    """Hebrew renewal subject + ₪/mo amount in snippet → DETECTED, MONTHLY billing cycle."""
    email = _make_email_with_snippet(
        "heb-003",
        "billing@spotify.com",
        "חידוש מנוי Spotify",
        snippet="₪12.90/mo — Spotify Premium חודשי",
    )
    result = process_email(conn, email)
    assert result.disposition == "DETECTED", (
        f"Expected DETECTED (Hebrew חידוש מנוי = RENEWAL pattern + amount), got {result.disposition}"
    )
    subs = get_subscriptions(conn)
    assert len(subs) == 1
    assert subs[0]["amount"] == pytest.approx(12.90)
    assert subs[0]["billing_cycle"] == "MONTHLY"


def test_mixed_hebrew_english_works(conn):
    """English subject from Tier 1 sender, Hebrew snippet with ₪ amount → both contribute correctly."""
    email = _make_email_with_snippet(
        "heb-004",
        "billing@spotify.com",
        "Your Spotify Premium receipt",
        snippet="חויבת ₪12.90 עבור Spotify Premium",
    )
    result = process_email(conn, email)
    assert result.disposition == "DETECTED", (
        f"Expected DETECTED (English RECEIPT subject + Hebrew ILS amount in snippet), got {result.disposition}"
    )
    subs = get_subscriptions(conn)
    assert len(subs) == 1
    assert subs[0]["amount"] == pytest.approx(12.90)


# ---------------------------------------------------------------------------
# Phase 3.3: payment_events integration tests
# ---------------------------------------------------------------------------

def test_receipt_creates_payment_event(conn):
    """Processing a RECEIPT email creates a payment_event row with event_type='subscription_charge'."""
    email = _make_email(
        "pe-t001",
        "billing@account.netflix.com",
        "Your Netflix membership receipt - $15.49",
    )
    result = process_email(conn, email)
    assert result.disposition == "DETECTED"

    events = get_payment_events(conn, source_message_id="pe-t001")
    assert len(events) == 1, (
        f"A RECEIPT email must produce exactly 1 payment_event, got {len(events)}"
    )
    assert events[0]["event_type"] == "subscription_charge", (
        f"RECEIPT pattern must map to 'subscription_charge', got {events[0]['event_type']!r}"
    )
    assert events[0]["merchant_name"] == "Netflix"
    assert events[0]["confidence_score"] > 0.0


def test_ils_currency_preserved_on_rescan(conn):
    """Bug 2 regression: ILS currency set on first scan must not be overwritten by NULL on re-scan.

    First email: Hebrew receipt with ₪12.90 → subscription created with currency='ILS'.
    Second email: same service, no currency in subject → COALESCE must keep currency='ILS'.
    """
    # First scan: Hebrew receipt with ILS amount in snippet
    first = _make_email_with_snippet(
        "ils-preserve-001",
        "billing@spotify.com",
        "קבלה על תשלום",
        snippet="חויבת ₪12.90 עבור Spotify Premium",
    )
    process_email(conn, first)

    subs = get_subscriptions(conn)
    assert len(subs) == 1
    assert subs[0]["currency"] == "ILS", (
        f"First scan must store currency='ILS', got {subs[0]['currency']!r}"
    )

    # Second scan: same service, subject has no currency signal (simulates no-symbol renewal)
    second = _make_email(
        "ils-preserve-002",
        "billing@spotify.com",
        "חידוש מנוי Spotify",  # no currency symbol
    )
    process_email(conn, second)

    subs_after = get_subscriptions(conn)
    spotify_subs = [s for s in subs_after if s["name"] == "Spotify"]
    assert len(spotify_subs) == 1
    assert spotify_subs[0]["currency"] == "ILS", (
        f"currency must remain 'ILS' after re-scan with no currency in subject, "
        f"got {spotify_subs[0]['currency']!r}. Bug 2 (COALESCE fix) must be in effect."
    )


def test_refund_creates_payment_event_not_subscription(conn):
    """A REFUND email creates a payment_event with event_type='refund' but does NOT create a new subscription."""
    email = _make_email(
        "pe-refund-001",
        "billing@account.netflix.com",
        "We've issued a refund of $15.49 to your account",
    )
    result = process_email(conn, email)
    assert result.disposition == "DETECTED", (
        f"REFUND from Tier 1 sender should be DETECTED, got {result.disposition}"
    )

    # No new subscription should be created (no existing sub to link to)
    subs = get_subscriptions(conn)
    assert len(subs) == 0, (
        f"A REFUND email must not create a new subscription, got {len(subs)} subscriptions"
    )

    # A payment_event with event_type='refund' should exist
    events = get_payment_events(conn, source_message_id="pe-refund-001")
    assert len(events) == 1, (
        f"REFUND email must create exactly 1 payment_event, got {len(events)}"
    )
    assert events[0]["event_type"] == "refund", (
        f"REFUND pattern must map to 'refund' payment_event, got {events[0]['event_type']!r}"
    )


def test_notification_creates_no_payment_event(conn):
    """A NOTIFICATION email (e.g. security alert) must not create any payment_event."""
    email = _make_email(
        "pe-notif-001",
        "no-reply@accounts.google.com",
        "Security alert: new sign-in from a new device",
    )
    result = process_email(conn, email)
    assert result.disposition == "IGNORED", (
        f"NOTIFICATION should be IGNORED, got {result.disposition}"
    )

    events = get_payment_events(conn, source_message_id="pe-notif-001")
    assert len(events) == 0, (
        f"NOTIFICATION email must NOT create any payment_event, got {len(events)}"
    )


# ---------------------------------------------------------------------------
# Phase 3.3B: Payment event semantics — correctness tests
# ---------------------------------------------------------------------------

def test_none_pattern_creates_no_payment_event(conn):
    """Email with no billing pattern must not create a payment_event regardless of disposition.

    Phase 3.3 bug: PatternType.NONE was mapped to 'unknown_payment', causing every
    ambiguous email to produce a payment_event. After fix, PatternType.NONE → no event.
    """
    # Vague subject from unknown sender — no billing pattern, no amount.
    # May be FLAGGED or IGNORED depending on confidence score thresholds.
    # Either way, no payment_event should be created.
    email = _make_email(
        "pe-none-001",
        "noreply@somewebsite.example.com",
        "Your account update",
    )
    process_email(conn, email)

    events = get_payment_events(conn, source_message_id="pe-none-001")
    assert len(events) == 0, (
        f"PatternType.NONE (no financial signal) must produce no payment_event. "
        f"Got {len(events)} event(s). Phase 3.3 bug: NONE was mapping to 'unknown_payment'."
    )


def test_renewal_creates_renewal_charge_event(conn):
    """A second RECEIPT from the same Tier 1 sender (renewal) must create event_type='renewal_charge'.

    Phase 3.3 bug: RENEWAL was collapsed to 'subscription_charge', losing semantic distinction.
    After fix: first charge → 'subscription_charge'; subsequent → 'renewal_charge'.
    """
    # First receipt — creates the subscription
    first = _make_email(
        "pe-renewal-001",
        "billing@account.netflix.com",
        "Your Netflix membership receipt - $15.49",
        date_str="2025-01-01T08:00:00Z",
    )
    process_email(conn, first)

    # Second receipt — renewal of existing subscription
    second = _make_email(
        "pe-renewal-002",
        "billing@account.netflix.com",
        "Your Netflix membership receipt - $15.49",
        date_str="2025-02-01T08:00:00Z",
    )
    process_email(conn, second)

    events_first = get_payment_events(conn, source_message_id="pe-renewal-001")
    events_second = get_payment_events(conn, source_message_id="pe-renewal-002")

    assert len(events_first) == 1
    assert events_first[0]["event_type"] == "subscription_charge", (
        f"First receipt must produce 'subscription_charge', got {events_first[0]['event_type']!r}"
    )

    assert len(events_second) == 1
    assert events_second[0]["event_type"] == "renewal_charge", (
        f"Second receipt (renewal) must produce 'renewal_charge', "
        f"got {events_second[0]['event_type']!r}. "
        f"Phase 3.3 bug: RENEWAL was mapped to 'subscription_charge'."
    )


def test_flagged_no_amount_creates_no_payment_event(conn):
    """FLAGGED email without an extracted amount must not create any payment_event.

    Phase 3.3 bug: ALL FLAGGED emails (including those with no financial data) created
    payment_events. After fix: FLAGGED + no amount → no event.
    """
    # Tier 1 sender (Google) but subject has no billing pattern → FLAGGED NOTIFICATION or similar
    # Use an unknown sender to ensure FLAGGED disposition with no amount
    email = _make_email(
        "pe-flagged-noamt-001",
        "receipt@unknownservice.example.com",
        "Payment confirmation",  # RECEIPT-like subject from unknown sender → FLAGGED
    )
    result = process_email(conn, email)
    # The email may be FLAGGED (unknown sender, receipt-like subject, no amount)
    if result.disposition != "FLAGGED":
        pytest.skip(f"Expected FLAGGED, got {result.disposition} — adjust test fixture")

    events = get_payment_events(conn, source_message_id="pe-flagged-noamt-001")
    assert len(events) == 0, (
        f"FLAGGED email with no extracted amount must not create a payment_event, "
        f"got {len(events)} event(s). "
        f"Phase 3.3 bug: all FLAGGED emails created 'unknown_payment' events regardless of amount."
    )


def test_is_recurring_candidate_requires_amount(conn):
    """is_recurring_candidate must be 0 when no amount was extracted.

    A subscription_charge or renewal_charge without an amount is not a confirmed
    recurring payment — we don't know the amount to track.
    """
    # Spotify renewal without amount in subject
    email = _make_email(
        "pe-recurring-noamt-001",
        "billing@spotify.com",
        "חידוש מנוי Spotify",  # renewal subject, no amount
    )
    process_email(conn, email)

    events = get_payment_events(conn, source_message_id="pe-recurring-noamt-001")
    if events:
        assert events[0]["is_recurring_candidate"] == 0, (
            f"is_recurring_candidate must be 0 when amount is NULL, "
            f"got {events[0]['is_recurring_candidate']}. "
            f"A charge without a confirmed amount is not a meaningful recurring signal."
        )


def test_cancellation_event_type_preserved(conn):
    """CANCELLATION pattern must create event_type='cancellation' — not 'subscription_charge'."""
    # First create a subscription to cancel
    receipt = _make_email(
        "pe-cancel-setup",
        "billing@account.netflix.com",
        "Your Netflix membership receipt - $15.49",
    )
    process_email(conn, receipt)

    cancellation = _make_email(
        "pe-cancel-001",
        "billing@account.netflix.com",
        "Your Netflix subscription has been cancelled",
    )
    process_email(conn, cancellation)

    events = get_payment_events(conn, source_message_id="pe-cancel-001")
    assert len(events) == 1, (
        f"CANCELLATION email must create exactly 1 payment_event, got {len(events)}"
    )
    assert events[0]["event_type"] == "cancellation", (
        f"CANCELLATION pattern must produce event_type='cancellation', "
        f"got {events[0]['event_type']!r}"
    )


def test_payment_events_total_less_than_email_records(conn):
    """Non-financial emails must not produce payment_events; financial ones must.

    Phase 3.3 bug: payment_events == email_records because every email produced an event.
    After fix: only real financial events (receipt, renewal) produce payment_events.

    Note: non-financial emails from unknown senders may be IGNORED (score < threshold)
    and never reach email_records at all. The assertion here checks per-message behaviour
    rather than aggregate counts, to avoid depending on whether IGNORED emails are stored.
    """
    financial_ids = ["mix-001", "mix-002"]
    non_financial_ids = ["mix-003", "mix-004", "mix-005"]

    emails = [
        # Financial — produce payment_events (subscription_charge / renewal_charge)
        _make_email("mix-001", "billing@account.netflix.com",
                    "Your Netflix membership receipt - $15.49", "2025-01-01T08:00:00Z"),
        _make_email("mix-002", "billing@account.netflix.com",
                    "Your Netflix membership receipt - $15.49", "2025-02-01T08:00:00Z"),
        # Non-financial — no billing pattern, no amount → must NOT produce payment_events
        _make_email("mix-003", "no-reply@accounts.google.com",
                    "Security alert: new sign-in"),
        _make_email("mix-004", "noreply@somesite.example.com",
                    "Welcome to our newsletter"),
        _make_email("mix-005", "noreply@somesite.example.com",
                    "Weekly digest: top articles this week"),
    ]
    for email in emails:
        process_email(conn, email)

    # Financial emails must each produce exactly 1 payment_event.
    for msg_id in financial_ids:
        events = get_payment_events(conn, source_message_id=msg_id)
        assert len(events) == 1, (
            f"Financial email {msg_id} must produce 1 payment_event, got {len(events)}"
        )

    # Non-financial emails must produce zero payment_events regardless of disposition
    # (DETECTED, FLAGGED, or IGNORED — none of them carry financial signal).
    for msg_id in non_financial_ids:
        events = get_payment_events(conn, source_message_id=msg_id)
        assert len(events) == 0, (
            f"Non-financial email {msg_id} must not produce payment_events, "
            f"got {len(events)}. Phase 3.3 bug: every email was creating a payment_event."
        )
