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
    # Phase 2.8: job alerts and recruiting
    "Full Stack Developer at Tech Startup",
    "Junior Software Engineer position — apply now",
    "Now hiring: Senior Product Manager",
    "Open role: Data Analyst at Wix",
    # Phase 2.8: LinkedIn invitations and social
    "Adi wants to connect on LinkedIn",
    "Invitation to connect with Someone",
    "John has accepted your invitation",
    "Your application was viewed by recruiter",
    # Phase 2.8: newsletter / content digest
    "New post from [Author] in your inbox",
    "New issue of The Weekly Digest",
    "Monthly newsletter: top stories this month",
    "Weekly newsletter from your favorite blog",
    # Phase 2.8: app install prompts
    "Download the LinkedIn mobile app",
    "Install the app and stay connected",
    # Phase 2.8: exam / schedule notifications
    "Update Regarding Your Wix Enter Exam Schedule",
    "Your exam schedule has been updated",
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


# ── Phase 2.8: New NOTIFICATION pattern safety tests ─────────────────────────

def test_job_alert_does_not_block_receipt():
    """A subject with both job language and billing language → RECEIPT wins."""
    subject = "Your LinkedIn Premium receipt — $29.99"
    assert match_pattern(subject) == PatternType.RECEIPT


def test_newsletter_does_not_block_renewal():
    """A subject containing subscription renewal language wins over newsletter."""
    subject = "Your Substack Pro newsletter subscription renewed - $8/mo"
    assert match_pattern(subject) == PatternType.RENEWAL


def test_job_opening_is_notification():
    """'Job opening' subject → NOTIFICATION."""
    assert match_pattern("New job opening: Senior Engineer") == PatternType.NOTIFICATION


def test_linkedin_invitation_is_notification():
    """LinkedIn connection invitation → NOTIFICATION."""
    assert match_pattern("Invitation to connect with Jane Doe") == PatternType.NOTIFICATION


def test_newsletter_content_is_notification():
    """New post / newsletter content email → NOTIFICATION."""
    assert match_pattern("New post from TechBlog in your inbox") == PatternType.NOTIFICATION


def test_app_install_prompt_is_notification():
    """App install prompt → NOTIFICATION."""
    assert match_pattern("Download the app and get started") == PatternType.NOTIFICATION


def test_exam_schedule_is_notification():
    """Exam schedule notification → NOTIFICATION."""
    assert match_pattern("Your assessment schedule has been updated") == PatternType.NOTIFICATION


# ── Phase 2.9: Promotional offer-price patterns ───────────────────────────────

def test_for_only_price_is_promotional():
    """'for only $X' upgrade offer language → PROMOTIONAL."""
    assert match_pattern("Get Pro for only $72") == PatternType.PROMOTIONAL


def test_only_price_is_promotional():
    """'only $X/month' upsell language → PROMOTIONAL."""
    assert match_pattern("Upgrade today — only $9.99/month") == PatternType.PROMOTIONAL


def test_just_price_is_promotional():
    """'just $X/month' offer language → PROMOTIONAL."""
    assert match_pattern("Stay protected — just $12/month") == PatternType.PROMOTIONAL


def test_starting_at_price_is_promotional():
    """'starting at $X' offer language → PROMOTIONAL."""
    assert match_pattern("Plans starting at $9.99/month") == PatternType.PROMOTIONAL


def test_get_plan_for_price_is_promotional():
    """'Get Pro for $X' upgrade offer → PROMOTIONAL (one-word plan name)."""
    assert match_pattern("Get Pro for $72") == PatternType.PROMOTIONAL


def test_receipt_beats_only_language():
    """A genuine receipt containing 'only $X charged' → RECEIPT wins (higher priority)."""
    assert match_pattern("Your receipt — only $12.90 charged") == PatternType.RECEIPT


def test_renewal_beats_just_language():
    """A genuine renewal notice with 'just $X/month' language → RENEWAL wins over PROMOTIONAL.
    Note: RENEWAL is checked before PROMOTIONAL in match_pattern(), so it wins."""
    assert match_pattern("Your subscription renewed — just $9.99/month") == PatternType.RENEWAL


# ── Phase 3.1: New RECEIPT patterns (payment processed/complete) ──────────────

def test_payment_processed_is_receipt():
    """'Payment processed' Stripe-style subject → RECEIPT."""
    assert match_pattern("Payment processed for your subscription") == PatternType.RECEIPT


def test_payment_complete_is_receipt():
    """'Payment complete' subject → RECEIPT."""
    assert match_pattern("Payment complete — thank you") == PatternType.RECEIPT


def test_payment_completed_is_receipt():
    """'Payment completed' (past tense, adjacent) → RECEIPT."""
    assert match_pattern("Payment completed — thank you for subscribing") == PatternType.RECEIPT


# ── Phase 3.1: New NOTIFICATION patterns ─────────────────────────────────────

def test_linkedin_job_count_is_notification():
    """'3 new jobs' LinkedIn-style subject → NOTIFICATION."""
    assert match_pattern("3 new jobs in Tel Aviv this week") == PatternType.NOTIFICATION


def test_linkedin_jobs_matching_is_notification():
    """'Jobs matching your search' LinkedIn subject → NOTIFICATION."""
    assert match_pattern("Jobs matching your search: Software Engineer") == PatternType.NOTIFICATION


def test_jobs_for_you_is_notification():
    """'Jobs for you' digest subject → NOTIFICATION."""
    assert match_pattern("5 new jobs for you today") == PatternType.NOTIFICATION


def test_substack_latest_post_from_is_notification():
    """Substack 'new post from [Author]' format → NOTIFICATION."""
    assert match_pattern("New post from John Doe on Substack") == PatternType.NOTIFICATION


def test_substack_apostrophe_s_post_is_notification():
    """Author possessive 'Jane's latest post' format → NOTIFICATION."""
    assert match_pattern("Jane's latest post: How to build better habits") == PatternType.NOTIFICATION


def test_substack_latest_issue_from_is_notification():
    """Newsletter 'latest issue from' format → NOTIFICATION."""
    assert match_pattern("Latest issue from The Weekly Brief") == PatternType.NOTIFICATION


def test_zoom_meeting_invite_is_notification():
    """'Zoom Meeting Invitation' subject → NOTIFICATION."""
    assert match_pattern("Zoom Meeting Invitation: Q3 Planning Session") == PatternType.NOTIFICATION


def test_zoom_meeting_call_is_notification():
    """'Zoom call' invitation → NOTIFICATION."""
    assert match_pattern("Zoom call invite: Team standup tomorrow") == PatternType.NOTIFICATION


def test_invited_to_zoom_is_notification():
    """'Invited to a Zoom' subject → NOTIFICATION."""
    assert match_pattern("You've been invited to a Zoom meeting") == PatternType.NOTIFICATION


# ── Phase 3.1: Safety — billing patterns still beat new NOTIFICATION patterns ─

def test_receipt_beats_zoom_notification():
    """A real Zoom billing receipt must still be RECEIPT, not NOTIFICATION."""
    assert match_pattern("Your Zoom receipt - $14.99") == PatternType.RECEIPT


def test_receipt_beats_new_jobs_language():
    """'payment' in subject beats NOTIFICATION from job count language."""
    assert match_pattern("Payment confirmation for 3 new jobs posted") == PatternType.RECEIPT


# ── Phase 3.2: Hebrew billing support ────────────────────────────────────────

# --- Hebrew RECEIPT patterns ---

def test_hebrew_card_charged_is_receipt():
    """'כרטיסך חויב' (your card was charged) → RECEIPT."""
    assert match_pattern("כרטיסך חויב ₪49.90") == PatternType.RECEIPT


def test_hebrew_payment_confirmation_is_receipt():
    """'אישור תשלום' (payment confirmation) → RECEIPT."""
    assert match_pattern("אישור תשלום עבור המנוי שלך") == PatternType.RECEIPT


def test_hebrew_standing_order_is_receipt():
    """'הוראת קבע' (standing order / direct debit) → RECEIPT."""
    assert match_pattern("הוראת קבע בוצעה בהצלחה") == PatternType.RECEIPT


# --- Hebrew PROMOTIONAL patterns ---

def test_hebrew_sale_is_promotional():
    """'מבצע' (sale / special offer) → PROMOTIONAL."""
    assert match_pattern("מבצע מיוחד - שדרג עכשיו") == PatternType.PROMOTIONAL


def test_hebrew_discount_is_promotional():
    """'הנחה' (discount) → PROMOTIONAL."""
    assert match_pattern("הנחה של 50% לחודש הראשון") == PatternType.PROMOTIONAL


def test_hebrew_coupon_is_promotional():
    """'קופון' (coupon) → PROMOTIONAL."""
    assert match_pattern("קופון הנחה לחברים חדשים") == PatternType.PROMOTIONAL


# --- Hebrew NOTIFICATION patterns ---

def test_hebrew_job_ad_is_notification():
    """'דרושים' (jobs wanted / hiring) → NOTIFICATION."""
    assert match_pattern("דרושים מפתחים בכירים") == PatternType.NOTIFICATION


def test_hebrew_newsletter_is_notification():
    """'ניוזלטר' (newsletter) → NOTIFICATION."""
    assert match_pattern("ניוזלטר חודשי - עדכונים מהחברה") == PatternType.NOTIFICATION


def test_hebrew_event_invite_is_notification():
    """'הזמנה לכנס' (invitation to conference) → NOTIFICATION."""
    assert match_pattern("הזמנה לכנס שנתי 2026") == PatternType.NOTIFICATION


# --- Priority safety: RECEIPT beats Hebrew PROMOTIONAL / NOTIFICATION ---

def test_hebrew_receipt_beats_promotional():
    """קבלה (RECEIPT pattern) beats מבצע (PROMOTIONAL) — RECEIPT has higher priority."""
    assert match_pattern("קבלה מבצע ₪12.90") == PatternType.RECEIPT


def test_hebrew_receipt_beats_notification():
    """קבלה (RECEIPT pattern) beats דרושים (NOTIFICATION) — RECEIPT has higher priority."""
    assert match_pattern("קבלה על תשלום - דרושים") == PatternType.RECEIPT
