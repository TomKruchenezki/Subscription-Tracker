import pytest
from backend.parser.cycle_detector import detect_cycle


@pytest.mark.parametrize("subject, expected", [
    ("Your monthly subscription receipt",           "MONTHLY"),
    ("Charged per month",                           "MONTHLY"),
    ("Plan: $9.99/mo",                              "MONTHLY"),
    ("Month-to-month billing",                      "MONTHLY"),
    ("Annual subscription renewal",                 "ANNUAL"),
    ("Yearly billing notice",                       "ANNUAL"),
    ("Subscription: $99.00/yr",                     "ANNUAL"),
    ("12-month plan invoice",                       "ANNUAL"),
    ("Your weekly meal plan receipt",               "WEEKLY"),
    ("Charged per week",                            "WEEKLY"),
    ("Your subscription receipt",                   "UNKNOWN"),
    ("Account statement enclosed",                  "UNKNOWN"),
    # Annual takes priority over monthly if both appear
    ("Annual monthly billing notice",               "ANNUAL"),
    # Quarterly
    ("Quarterly billing statement",                 "QUARTERLY"),
    ("Charged every 3 months",                      "QUARTERLY"),
    ("3-month plan renewal",                        "QUARTERLY"),
])
def test_detect_cycle(subject, expected):
    assert detect_cycle(subject) == expected


def test_hebrew_monthly_cycle():
    assert detect_cycle("חיוב חודשי") == "MONTHLY"


def test_hebrew_annual_cycle():
    assert detect_cycle("חיוב שנתי") == "ANNUAL"


def test_hebrew_quarterly_cycle():
    assert detect_cycle("חיוב רבעוני") == "QUARTERLY"


def test_cycle_from_snippet_fallback():
    """Subject has no cycle keyword; snippet provides it."""
    result = detect_cycle(
        subject="חידוש מנוי",
        snippet="Your plan renews monthly — $9.99/mo",
    )
    assert result == "MONTHLY"


def test_quarterly_before_monthly_priority():
    """QUARTERLY is more specific than MONTHLY; checked first."""
    assert detect_cycle("quarterly billing every 3 months") == "QUARTERLY"


# ── Context-gated cycle detection (Phase 2.7) ─────────────────────────────────

def test_weekly_standalone_without_billing_context_is_unknown():
    """'weekly' alone (no billing context) must NOT infer WEEKLY cycle."""
    assert detect_cycle("Your Grammarly Weekly Writing Report") == "UNKNOWN"


def test_weekly_with_billing_context_is_weekly():
    """'weekly' near a billing word fires normally."""
    assert detect_cycle("Your weekly subscription charge") == "WEEKLY"


def test_monthly_standalone_without_billing_context_is_unknown():
    """'monthly' alone (no billing context) must NOT infer MONTHLY cycle."""
    assert detect_cycle("Monthly career digest from LinkedIn") == "UNKNOWN"


def test_monthly_with_billing_context_is_monthly():
    """'monthly' near a billing word fires normally."""
    assert detect_cycle("Your monthly plan renews $12.99") == "MONTHLY"


def test_per_week_is_always_strong():
    """'per week' positional construction fires regardless of billing context."""
    assert detect_cycle("Service fee: $9.99 per week") == "WEEKLY"


def test_per_month_is_always_strong():
    """'per month' positional construction fires regardless of billing context."""
    assert detect_cycle("$9.99 per month") == "MONTHLY"


def test_receipt_is_sufficient_billing_context_for_weekly():
    """'receipt' is a billing context word; 'weekly' + 'receipt' = WEEKLY."""
    assert detect_cycle("Your weekly meal plan receipt") == "WEEKLY"


def test_subscription_is_sufficient_billing_context_for_monthly():
    """'subscription' is a billing context word; 'monthly' + 'subscription' = MONTHLY."""
    assert detect_cycle("Your monthly subscription renews soon") == "MONTHLY"


def test_renewal_is_sufficient_billing_context_for_monthly():
    """'renewal' is a billing context word; 'monthly' + 'renewal' = MONTHLY."""
    assert detect_cycle("Renewal: your monthly plan") == "MONTHLY"


def test_weekly_writing_stats_no_billing_context():
    """Grammarly-style email: 'weekly' in non-billing context stays UNKNOWN."""
    assert detect_cycle("Grammarly Weekly — Your writing activity this week") == "UNKNOWN"


def test_monthly_newsletter_no_billing_context():
    """LinkedIn-style: 'monthly' in newsletter context stays UNKNOWN."""
    assert detect_cycle("Monthly newsletter: top stories for you") == "UNKNOWN"


# ── Phase 3.1: ANNUAL and QUARTERLY context-gating ───────────────────────────

def test_annual_without_billing_context_returns_unknown():
    """'annual' alone with no billing words → UNKNOWN.
    Prevents Spotify HTML body ('Save with Annual plan') from triggering ANNUAL."""
    assert detect_cycle("Your annual performance review") == "UNKNOWN"


def test_annual_with_billing_context_returns_annual():
    """'annual' + billing word in same text → ANNUAL."""
    assert detect_cycle("Your annual subscription renews") == "ANNUAL"


def test_per_year_always_fires():
    """'/year' is a strong positional pattern — fires without billing context."""
    assert detect_cycle("Plan costs $9.99/year") == "ANNUAL"


def test_yr_always_fires():
    """'/yr' is a strong positional pattern — fires without billing context."""
    assert detect_cycle("$99/yr") == "ANNUAL"


def test_yearly_requires_billing_context():
    """'yearly' without billing words → UNKNOWN."""
    assert detect_cycle("Set your yearly goals here") == "UNKNOWN"


def test_yearly_with_billing_context_returns_annual():
    """'yearly' + billing word → ANNUAL."""
    assert detect_cycle("Yearly plan fee: $99") == "ANNUAL"


def test_quarterly_without_billing_context_returns_unknown():
    """'quarterly' without billing words → UNKNOWN.
    Prevents 'Q3 quarterly business review' from misclassifying."""
    assert detect_cycle("Q3 quarterly business review") == "UNKNOWN"


def test_quarterly_with_billing_context_returns_quarterly():
    """'quarterly' + billing word → QUARTERLY."""
    assert detect_cycle("Quarterly billing: $29.99 charged") == "QUARTERLY"


def test_every_3_months_always_fires():
    """'every 3 months' is a strong positional pattern — fires without billing context."""
    assert detect_cycle("Billed every 3 months") == "QUARTERLY"


def test_hebrew_quarterly_requires_billing_context():
    """Hebrew 'רבעוני' + Hebrew billing word 'חיוב' → QUARTERLY.
    'חיוב' (charge/billing) is in the Hebrew billing context list."""
    assert detect_cycle("חיוב רבעוני") == "QUARTERLY"


def test_spotify_body_text_annual_mention_does_not_override_monthly():
    """Core regression: Spotify billing body has 'annual' in plan comparison section
    but the actual charge is monthly. With context-gating, 'annual' requires a billing
    context word in the SAME text. When body_text is checked after subject/snippet,
    the subject/snippet already return MONTHLY from the /mo positional pattern."""
    subject = "חידוש מנוי Spotify"  # Hebrew: "Spotify subscription renewal"
    snippet = "₪12.90/mo — Premium"  # /mo is a strong MONTHLY signal
    body_text = "Save with Annual plan — switch to annual and save 15%"
    result = detect_cycle(subject, snippet=snippet, body_text=body_text)
    assert result == "MONTHLY"


# ── Phase 3.2: Hebrew billing support ────────────────────────────────────────

def test_hebrew_weekly_cycle():
    """שבועי (weekly, Hebrew) with billing context word 'חיוב' → WEEKLY."""
    assert detect_cycle("חיוב שבועי") == "WEEKLY"


def test_hebrew_every_month_is_monthly():
    """כל חודש (every month, Hebrew) → MONTHLY (strong positional pattern)."""
    assert detect_cycle("כל חודש ₪9.90") == "MONTHLY"


def test_hebrew_every_year_is_annual():
    """כל שנה (every year, Hebrew) → ANNUAL (strong positional pattern)."""
    assert detect_cycle("כל שנה ₪99") == "ANNUAL"


# ── Phase 3.3B: body_text weak pattern restriction ────────────────────────────
#
# Weak patterns (standalone "annual", "weekly", "monthly" + billing context) must NOT
# fire from body_text. Billing receipt bodies almost always contain billing context words,
# so allowing weak patterns from body_text causes systematic misclassification
# (e.g., Spotify monthly receipt body mentioning "annual plan" → ANNUAL).
# Only strong positional patterns (/year, per month, /week, etc.) fire from body_text.

def test_annual_weak_in_body_text_only_returns_unknown():
    """'annual' + billing context in body_text only (neutral subject/snippet) → UNKNOWN.

    Phase 3.3B fix: weak ANNUAL pattern must be suppressed for body_text.
    Before fix: this returned ANNUAL, causing Spotify monthly receipts to get ANNUAL cycle.
    """
    result = detect_cycle(
        subject="קבלה על תשלום",           # "receipt for payment" — no cycle word
        snippet=None,
        body_text="Save with Annual plan — switch to annual and save. Subscription billed monthly.",
    )
    # 'annual' + 'Subscription' (billing context) in body_text must NOT fire ANNUAL
    # 'monthly' + 'billed' (billing context) in body_text must NOT fire MONTHLY (weak)
    # No strong positional pattern (/year, per year, /mo, etc.) → UNKNOWN
    assert result == "UNKNOWN", (
        f"Weak 'annual' in body_text + billing context must not fire ANNUAL cycle. "
        f"Got {result!r}. This is the Phase 3.3B Spotify $1.07/mo root cause fix."
    )


def test_annual_strong_in_body_text_does_fire():
    """'/year' (strong positional) in body_text still fires ANNUAL.

    Strong patterns are not restricted to subject/snippet — they fire from any source.
    """
    result = detect_cycle(
        subject="Your receipt",
        snippet=None,
        body_text="You were charged $99.00/year for your plan.",
    )
    assert result == "ANNUAL", (
        f"Strong '/year' pattern must fire from body_text. Got {result!r}."
    )


def test_weekly_weak_in_body_text_only_returns_unknown():
    """'weekly' + billing context in body_text only (neutral subject/snippet) → UNKNOWN.

    Phase 3.3B fix: weak WEEKLY pattern must be suppressed for body_text.
    Before fix: this returned WEEKLY, causing Zoom receipts with marketing text to get WEEKLY.
    """
    result = detect_cycle(
        subject="Payment Processed",        # no cycle word
        snippet=None,
        body_text="Your weekly subscription includes unlimited meeting minutes. Payment receipt.",
    )
    assert result == "UNKNOWN", (
        f"Weak 'weekly' in body_text + billing context must not fire WEEKLY cycle. "
        f"Got {result!r}. This is the Zoom WEEKLY misclassification fix."
    )


def test_per_week_strong_in_body_text_does_fire():
    """'per week' (strong positional) in body_text still fires WEEKLY."""
    result = detect_cycle(
        subject="Your receipt",
        snippet=None,
        body_text="Charged $9.99 per week.",
    )
    assert result == "WEEKLY", (
        f"Strong 'per week' must fire from body_text. Got {result!r}."
    )


def test_monthly_weak_in_body_text_only_returns_unknown():
    """'monthly' + billing context in body_text only → UNKNOWN (weak pattern suppressed)."""
    result = detect_cycle(
        subject="Your receipt",             # no cycle keyword in subject
        snippet=None,
        body_text="This is a monthly subscription charge for your account. Thank you.",
    )
    assert result == "UNKNOWN", (
        f"Weak 'monthly' in body_text must not fire (subject/snippet have no cycle signal). "
        f"Got {result!r}."
    )


def test_monthly_strong_in_body_text_does_fire():
    """/mo in body_text still fires MONTHLY (strong positional pattern)."""
    result = detect_cycle(
        subject="Your receipt",
        snippet=None,
        body_text="Your plan: $9.99/mo",
    )
    assert result == "MONTHLY", (
        f"Strong '/mo' must fire from body_text. Got {result!r}."
    )


def test_subject_wins_over_body_text_weak():
    """When subject has a strong signal, body_text weak patterns don't interfere."""
    result = detect_cycle(
        subject="Your monthly subscription renewal",
        snippet=None,
        body_text="Annual plan available — switch today. Your subscription payment was processed.",
    )
    # Subject provides MONTHLY via 'monthly' + 'subscription' (billing context in subject)
    assert result == "MONTHLY", (
        f"Subject-level 'monthly' signal must win. Got {result!r}."
    )


def test_spotify_monthly_receipt_body_annual_mention():
    """Realistic Spotify regression: monthly receipt email with 'annual' in body → UNKNOWN or MONTHLY.

    If the subject/snippet have the billing cycle clearly (e.g. ₪12.90/mo in snippet),
    MONTHLY is returned. If not (subject only says 'receipt'), and body says 'annual plan',
    the correct result is UNKNOWN — not ANNUAL.
    """
    # Case 1: subject/snippet have explicit monthly signal → MONTHLY
    result_with_snippet = detect_cycle(
        subject="קבלה - Spotify Premium",
        snippet="₪12.90/mo — חיוב חודשי",   # /mo + Hebrew 'monthly' (strong)
        body_text="Save 15% with Annual plan. Annual subscription available.",
    )
    assert result_with_snippet == "MONTHLY"

    # Case 2: only subject, no snippet, body mentions "annual" + "subscription" (billing context)
    # → body_text weak pattern suppressed → UNKNOWN (not ANNUAL)
    result_body_only = detect_cycle(
        subject="קבלה - Spotify Premium",
        snippet=None,
        body_text="Upgrade to Annual plan — save 15%. Your subscription is billed. Receipt enclosed.",
    )
    assert result_body_only == "UNKNOWN", (
        f"'annual' + 'subscription' in body_text only must not infer ANNUAL cycle. "
        f"Got {result_body_only!r}. This prevents Spotify ÷12 bug."
    )
