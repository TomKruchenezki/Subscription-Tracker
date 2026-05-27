"""Unit tests for pattern_library.py — English and Hebrew patterns."""
import pytest
from backend.detector.pattern_library import match_pattern, PatternType


# ── English patterns ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("subject, expected", [
    ("Your receipt from Netflix",                    PatternType.RECEIPT),
    ("Invoice for your subscription",                PatternType.RECEIPT),
    ("Payment confirmation: $15.49",                 PatternType.RECEIPT),
    ("You have been charged $9.99",                  PatternType.RECEIPT),
    ("Your subscription renewal is coming up",       PatternType.RENEWAL),
    ("Auto-renew reminder",                          PatternType.RENEWAL),
    ("Your trial is ending soon",                    PatternType.TRIAL_END),
    ("Free trial expires in 3 days",                 PatternType.TRIAL_END),
    ("Your free trial has started",                  PatternType.TRIAL_STARTED),
    ("Welcome to your trial",                        PatternType.TRIAL_STARTED),
    ("Your subscription has been cancelled",         PatternType.CANCELLATION),
    ("Cancellation confirmed",                       PatternType.CANCELLATION),
    ("We've issued a refund of $9.99",               PatternType.REFUND),
    ("Your refund is on its way",                    PatternType.REFUND),
    ("Action required: payment failed",              PatternType.FAILED_PAYMENT),
    ("Your card was declined",                       PatternType.FAILED_PAYMENT),
    ("Payment could not be processed",               PatternType.FAILED_PAYMENT),
    ("New price for your subscription",              PatternType.PRICE_CHANGE),
    ("50% off your first month",                     PatternType.PROMOTIONAL),
    ("Limited time offer — upgrade now",             PatternType.PROMOTIONAL),
    ("Hello from our team",                          PatternType.NONE),
])
def test_english_patterns(subject, expected):
    assert match_pattern(subject) == expected


# ── Hebrew patterns ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("subject, expected", [
    # Receipt / charge
    ("קבלה על תשלום",                               PatternType.RECEIPT),
    ("חשבונית מס",                                   PatternType.RECEIPT),
    ("חויבת $9.99",                                  PatternType.RECEIPT),
    ("עסקה בוצעה בהצלחה",                           PatternType.RECEIPT),
    ("חיוב חודשי",                                   PatternType.RECEIPT),
    ("תשלום התקבל",                                  PatternType.RECEIPT),
    # Renewal
    ("חידוש מנוי Spotify",                           PatternType.RENEWAL),
    ("המנוי שלך התחדש",                              PatternType.RENEWAL),
    ("מנוי פעיל",                                    PatternType.RENEWAL),
    # Cancellation
    ("ביטול המנוי",                                  PatternType.CANCELLATION),
    ("המנוי בוטל",                                   PatternType.CANCELLATION),
    # Refund
    ("החזר כספי אושר",                               PatternType.REFUND),
    ("זיכוי על הזמנה",                               PatternType.REFUND),
    # Failed payment
    ("התשלום נכשל",                                  PatternType.FAILED_PAYMENT),
    ("אמצעי התשלום נדחה",                            PatternType.FAILED_PAYMENT),
    # Trial
    ("ניסיון חינם הופעל",                            PatternType.TRIAL_STARTED),
    ("תקופת ניסיון התחילה",                          PatternType.TRIAL_STARTED),
])
def test_hebrew_patterns(subject, expected):
    result = match_pattern(subject)
    assert result == expected, (
        f"Expected {expected} for {subject!r}, got {result}"
    )


# ── Priority ordering ─────────────────────────────────────────────────────────

def test_failed_payment_beats_receipt():
    """FAILED_PAYMENT has higher priority than RECEIPT."""
    subject = "Action required: payment failed for your subscription receipt"
    assert match_pattern(subject) == PatternType.FAILED_PAYMENT


def test_cancellation_beats_renewal():
    """CANCELLATION has higher priority than RENEWAL."""
    subject = "Your subscription has been cancelled after renewal"
    assert match_pattern(subject) == PatternType.CANCELLATION


def test_refund_beats_receipt():
    """REFUND has higher priority than RECEIPT."""
    subject = "Refund receipt issued for $9.99"
    assert match_pattern(subject) == PatternType.REFUND


# ── NOTIFICATION patterns ─────────────────────────────────────────────────────

@pytest.mark.parametrize("subject", [
    "You appeared in 3 searches this week",
    "Your profile was viewed 5 times",
    "People you may know on LinkedIn",
    "You have a new connection request",
    "Someone endorsed your Python skill",
    "New job alert: Software Engineer in Tel Aviv",
    "Update to our User Agreement",
    "Important update to our Privacy Policy",
    "Changes to our Terms of Service",
    "We've updated our Terms and Conditions",
    "New sign-in from a new device",
    "New device sign-in detected",
    "Please verify your email address",
    "Reset your password",
    "Security alert: unusual activity",
    "Your e-ticket for flight LY123",
    "Your boarding pass is ready",
    "Your flight booking confirmation",
    "Hotel reservation confirmation - Marriott",
    "Reservation confirmation for your stay",
])
def test_notification_patterns_suppressed(subject):
    """Non-subscription notification subjects must match NOTIFICATION pattern."""
    result = match_pattern(subject)
    assert result == PatternType.NOTIFICATION, (
        f"Expected NOTIFICATION for {subject!r}, got {result}"
    )


def test_receipt_beats_notification():
    """A subject containing both a billing signal and a notification term
    must return RECEIPT (higher priority), not NOTIFICATION."""
    subject = "Your LinkedIn Premium receipt - $29.99"
    assert match_pattern(subject) == PatternType.RECEIPT


def test_renewal_beats_notification():
    """RENEWAL has higher priority than NOTIFICATION."""
    subject = "Your subscription renewal — security confirmed"
    assert match_pattern(subject) == PatternType.RENEWAL


# ── Phase 2.7: Grammarly / LinkedIn / Zoom NOTIFICATION patterns ──────────────

@pytest.mark.parametrize("subject", [
    # Grammarly weekly writing stats (not billing)
    "Your Grammarly Weekly Writing Report",
    "Your Grammarly writing activity this week",
    "Your Grammarly writing score this week",
    "Grammarly Weekly — Your grammar score",
    "Your weekly writing stats from Grammarly",
    # LinkedIn career digest (not billing)
    "Your weekly career digest from LinkedIn",
    "Weekly job alerts: top picks for you",
    "Monthly career digest — new opportunities",
    "Top jobs for you this week",
    "Your network digest this week",
    # Zoom non-billing (webinar/feature)
    "Join our free Zoom webinar this Thursday",
    "Zoom tips: get more from your meetings",
    "Webinar invitation: register now",
])
def test_phase27_notification_patterns(subject):
    """Phase 2.7 NOTIFICATION patterns: Grammarly stats, LinkedIn digests, Zoom webinars."""
    result = match_pattern(subject)
    assert result == PatternType.NOTIFICATION, (
        f"Expected NOTIFICATION for {subject!r}, got {result}"
    )


def test_grammarly_receipt_still_beats_notification():
    """A genuine Grammarly billing receipt must still be classified as RECEIPT."""
    subject = "Your Grammarly Premium receipt $12.99"
    assert match_pattern(subject) == PatternType.RECEIPT


def test_linkedin_receipt_still_beats_notification():
    """A genuine LinkedIn billing receipt must still be classified as RECEIPT."""
    subject = "Receipt for LinkedIn Premium subscription"
    assert match_pattern(subject) == PatternType.RECEIPT


def test_zoom_payment_beats_notification():
    """A genuine Zoom payment confirmation must still be classified as RECEIPT."""
    subject = "Payment confirmation for Zoom Pro — $14.99"
    assert match_pattern(subject) == PatternType.RECEIPT
