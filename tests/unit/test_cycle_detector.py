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
