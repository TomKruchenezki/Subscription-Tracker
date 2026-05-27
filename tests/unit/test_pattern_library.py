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
