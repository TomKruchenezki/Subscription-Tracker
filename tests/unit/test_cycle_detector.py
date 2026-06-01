import pytest
from backend.parser.cycle_detector import detect_cycle, CycleResult


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
    assert detect_cycle(subject).cycle == expected


def test_hebrew_monthly_cycle():
    assert detect_cycle("חיוב חודשי").cycle == "MONTHLY"


def test_hebrew_annual_cycle():
    assert detect_cycle("חיוב שנתי").cycle == "ANNUAL"


def test_hebrew_quarterly_cycle():
    assert detect_cycle("חיוב רבעוני").cycle == "QUARTERLY"


def test_cycle_from_snippet_fallback():
    """Subject has no cycle keyword; snippet provides it."""
    result = detect_cycle(
        subject="חידוש מנוי",
        snippet="Your plan renews monthly — $9.99/mo",
    )
    assert result.cycle == "MONTHLY"


def test_quarterly_before_monthly_priority():
    """QUARTERLY is more specific than MONTHLY; checked first."""
    assert detect_cycle("quarterly billing every 3 months").cycle == "QUARTERLY"


# ── Context-gated cycle detection (Phase 2.7) ─────────────────────────────────

def test_weekly_standalone_without_billing_context_is_unknown():
    """'weekly' alone (no billing context) must NOT infer WEEKLY cycle."""
    assert detect_cycle("Your Grammarly Weekly Writing Report").cycle == "UNKNOWN"


def test_weekly_with_billing_context_is_weekly():
    """'weekly' near a billing word fires normally."""
    assert detect_cycle("Your weekly subscription charge").cycle == "WEEKLY"


def test_monthly_standalone_without_billing_context_is_unknown():
    """'monthly' alone (no billing context) must NOT infer MONTHLY cycle."""
    assert detect_cycle("Monthly career digest from LinkedIn").cycle == "UNKNOWN"


def test_monthly_with_billing_context_is_monthly():
    """'monthly' near a billing word fires normally."""
    assert detect_cycle("Your monthly plan renews $12.99").cycle == "MONTHLY"


def test_per_week_is_always_strong():
    """'per week' positional construction fires regardless of billing context."""
    assert detect_cycle("Service fee: $9.99 per week").cycle == "WEEKLY"


def test_per_month_is_always_strong():
    """'per month' positional construction fires regardless of billing context."""
    assert detect_cycle("$9.99 per month").cycle == "MONTHLY"


def test_receipt_is_sufficient_billing_context_for_weekly():
    """'receipt' is a billing context word; 'weekly' + 'receipt' = WEEKLY."""
    assert detect_cycle("Your weekly meal plan receipt").cycle == "WEEKLY"


def test_subscription_is_sufficient_billing_context_for_monthly():
    """'subscription' is a billing context word; 'monthly' + 'subscription' = MONTHLY."""
    assert detect_cycle("Your monthly subscription renews soon").cycle == "MONTHLY"


def test_renewal_is_sufficient_billing_context_for_monthly():
    """'renewal' is a billing context word; 'monthly' + 'renewal' = MONTHLY."""
    assert detect_cycle("Renewal: your monthly plan").cycle == "MONTHLY"


def test_weekly_writing_stats_no_billing_context():
    """Grammarly-style email: 'weekly' in non-billing context stays UNKNOWN."""
    assert detect_cycle("Grammarly Weekly — Your writing activity this week").cycle == "UNKNOWN"


def test_monthly_newsletter_no_billing_context():
    """LinkedIn-style: 'monthly' in newsletter context stays UNKNOWN."""
    assert detect_cycle("Monthly newsletter: top stories for you").cycle == "UNKNOWN"


# ── Phase 3.1: ANNUAL and QUARTERLY context-gating ───────────────────────────

def test_annual_without_billing_context_returns_unknown():
    """'annual' alone with no billing words → UNKNOWN."""
    assert detect_cycle("Your annual performance review").cycle == "UNKNOWN"


def test_annual_with_billing_context_returns_annual():
    """'annual' + billing word in same text → ANNUAL."""
    assert detect_cycle("Your annual subscription renews").cycle == "ANNUAL"


def test_per_year_always_fires():
    """'/year' is a strong positional pattern — fires without billing context."""
    assert detect_cycle("Plan costs $9.99/year").cycle == "ANNUAL"


def test_yr_always_fires():
    """'/yr' is a strong positional pattern — fires without billing context."""
    assert detect_cycle("$99/yr").cycle == "ANNUAL"


def test_yearly_requires_billing_context():
    """'yearly' without billing words → UNKNOWN."""
    assert detect_cycle("Set your yearly goals here").cycle == "UNKNOWN"


def test_yearly_with_billing_context_returns_annual():
    """'yearly' + billing word → ANNUAL."""
    assert detect_cycle("Yearly plan fee: $99").cycle == "ANNUAL"


def test_quarterly_without_billing_context_returns_unknown():
    """'quarterly' without billing words → UNKNOWN."""
    assert detect_cycle("Q3 quarterly business review").cycle == "UNKNOWN"


def test_quarterly_with_billing_context_returns_quarterly():
    """'quarterly' + billing word → QUARTERLY."""
    assert detect_cycle("Quarterly billing: $29.99 charged").cycle == "QUARTERLY"


def test_every_3_months_always_fires():
    """'every 3 months' is a strong positional pattern — fires without billing context."""
    assert detect_cycle("Billed every 3 months").cycle == "QUARTERLY"


def test_hebrew_quarterly_requires_billing_context():
    """Hebrew 'רבעוני' + Hebrew billing word 'חיוב' → QUARTERLY."""
    assert detect_cycle("חיוב רבעוני").cycle == "QUARTERLY"


def test_spotify_body_text_annual_mention_does_not_override_monthly():
    """Core regression: Spotify billing body has 'annual' in plan comparison section
    but the actual charge is monthly. With context-gating, 'annual' requires a billing
    context word in the SAME text. When body_text is checked after subject/snippet,
    the subject/snippet already return MONTHLY from the /mo positional pattern."""
    subject = "חידוש מנוי Spotify"  # Hebrew: "Spotify subscription renewal"
    snippet = "₪12.90/mo — Premium"  # /mo is a strong MONTHLY signal
    body_text = "Save with Annual plan — switch to annual and save 15%"
    result = detect_cycle(subject, snippet=snippet, body_text=body_text)
    assert result.cycle == "MONTHLY"


# ── Phase 3.2: Hebrew billing support ────────────────────────────────────────

def test_hebrew_weekly_cycle():
    """שבועי (weekly, Hebrew) with billing context word 'חיוב' → WEEKLY."""
    assert detect_cycle("חיוב שבועי").cycle == "WEEKLY"


def test_hebrew_every_month_is_monthly():
    """כל חודש (every month, Hebrew) → MONTHLY (strong positional pattern)."""
    assert detect_cycle("כל חודש ₪9.90").cycle == "MONTHLY"


def test_hebrew_every_year_is_annual():
    """כל שנה (every year, Hebrew) → ANNUAL (strong positional pattern)."""
    assert detect_cycle("כל שנה ₪99").cycle == "ANNUAL"


# ── Phase 3.3B: body_text weak pattern restriction ────────────────────────────

def test_annual_weak_in_body_text_only_returns_unknown():
    """'annual' + billing context in body_text only (neutral subject/snippet) → UNKNOWN."""
    result = detect_cycle(
        subject="קבלה על תשלום",
        snippet=None,
        body_text="Save with Annual plan — switch to annual and save. Subscription billed monthly.",
    )
    assert result.cycle == "UNKNOWN", (
        f"Weak 'annual' in body_text + billing context must not fire ANNUAL cycle. "
        f"Got {result.cycle!r}. This is the Phase 3.3B Spotify $1.07/mo root cause fix."
    )


def test_annual_strong_in_body_text_does_fire():
    """'/year' (strong positional) in body_text still fires ANNUAL."""
    result = detect_cycle(
        subject="Your receipt",
        snippet=None,
        body_text="You were charged $99.00/year for your plan.",
    )
    assert result.cycle == "ANNUAL", (
        f"Strong '/year' pattern must fire from body_text. Got {result.cycle!r}."
    )


def test_weekly_weak_in_body_text_only_returns_unknown():
    """'weekly' + billing context in body_text only → UNKNOWN."""
    result = detect_cycle(
        subject="Payment Processed",
        snippet=None,
        body_text="Your weekly subscription includes unlimited meeting minutes. Payment receipt.",
    )
    assert result.cycle == "UNKNOWN", (
        f"Weak 'weekly' in body_text + billing context must not fire WEEKLY cycle. "
        f"Got {result.cycle!r}."
    )


def test_per_week_strong_in_body_text_does_fire():
    """'per week' (strong positional) in body_text still fires WEEKLY."""
    result = detect_cycle(
        subject="Your receipt",
        snippet=None,
        body_text="Charged $9.99 per week.",
    )
    assert result.cycle == "WEEKLY", (
        f"Strong 'per week' must fire from body_text. Got {result.cycle!r}."
    )


def test_monthly_weak_in_body_text_only_returns_unknown():
    """'monthly' + billing context in body_text only → UNKNOWN."""
    result = detect_cycle(
        subject="Your receipt",
        snippet=None,
        body_text="This is a monthly subscription charge for your account. Thank you.",
    )
    assert result.cycle == "UNKNOWN", (
        f"Weak 'monthly' in body_text must not fire. Got {result.cycle!r}."
    )


def test_monthly_strong_in_body_text_does_fire():
    """/mo in body_text still fires MONTHLY (strong positional pattern)."""
    result = detect_cycle(
        subject="Your receipt",
        snippet=None,
        body_text="Your plan: $9.99/mo",
    )
    assert result.cycle == "MONTHLY", (
        f"Strong '/mo' must fire from body_text. Got {result.cycle!r}."
    )


def test_subject_wins_over_body_text_weak():
    """When subject has a strong signal, body_text weak patterns don't interfere."""
    result = detect_cycle(
        subject="Your monthly subscription renewal",
        snippet=None,
        body_text="Annual plan available — switch today. Your subscription payment was processed.",
    )
    assert result.cycle == "MONTHLY", (
        f"Subject-level 'monthly' signal must win. Got {result.cycle!r}."
    )


def test_spotify_monthly_receipt_body_annual_mention():
    """Realistic Spotify regression: monthly receipt email with 'annual' in body."""
    result_with_snippet = detect_cycle(
        subject="קבלה - Spotify Premium",
        snippet="₪12.90/mo — חיוב חודשי",
        body_text="Save 15% with Annual plan. Annual subscription available.",
    )
    assert result_with_snippet.cycle == "MONTHLY"

    result_body_only = detect_cycle(
        subject="קבלה - Spotify Premium",
        snippet=None,
        body_text="Upgrade to Annual plan — save 15%. Your subscription is billed. Receipt enclosed.",
    )
    assert result_body_only.cycle == "UNKNOWN", (
        f"'annual' + 'subscription' in body_text only must not infer ANNUAL cycle. "
        f"Got {result_body_only.cycle!r}."
    )


# ── Phase 3.8: CycleResult fields and weak-cycle confidence ──────────────────

def test_cycle_result_has_expected_fields():
    """CycleResult returns all three fields."""
    result = detect_cycle("Your monthly subscription renews")
    assert isinstance(result, CycleResult)
    assert result.cycle == "MONTHLY"
    assert result.cycle_source == "subject_context"
    assert result.cycle_confidence == "WEAK"


def test_strong_positional_gives_strong_confidence():
    """/mo in subject → STRONG confidence."""
    result = detect_cycle("Plan: $9.99/mo")
    assert result.cycle == "MONTHLY"
    assert result.cycle_source == "subject_positional"
    assert result.cycle_confidence == "STRONG"


def test_context_word_gives_weak_confidence():
    """'annual' + billing context in subject → WEAK confidence."""
    result = detect_cycle("Your annual subscription renews")
    assert result.cycle == "ANNUAL"
    assert result.cycle_source == "subject_context"
    assert result.cycle_confidence == "WEAK"


def test_no_cycle_returns_none_confidence():
    """No cycle detected → cycle_confidence NONE, source none."""
    result = detect_cycle("Your account statement")
    assert result.cycle == "UNKNOWN"
    assert result.cycle_source == "none"
    assert result.cycle_confidence == "NONE"


def test_per_year_gives_strong_confidence():
    """'/year' positional → STRONG confidence."""
    result = detect_cycle("$99/year plan")
    assert result.cycle == "ANNUAL"
    assert result.cycle_confidence == "STRONG"


def test_snippet_positional_strong():
    """Snippet /mo → source snippet_positional, STRONG."""
    result = detect_cycle("Receipt", snippet="₪12.90/mo")
    assert result.cycle == "MONTHLY"
    assert result.cycle_source == "snippet_positional"
    assert result.cycle_confidence == "STRONG"


def test_snippet_context_weak():
    """Snippet 'monthly subscription' → source snippet_context, WEAK."""
    result = detect_cycle("Your receipt", snippet="monthly subscription charge")
    assert result.cycle == "MONTHLY"
    assert result.cycle_source == "snippet_context"
    assert result.cycle_confidence == "WEAK"


def test_body_strong_still_fires():
    """'/mo' in body_text → body_positional, STRONG (strong patterns fire from body)."""
    result = detect_cycle("Receipt", snippet=None, body_text="Plan: $9.99/mo")
    assert result.cycle == "MONTHLY"
    assert result.cycle_source == "body_positional"
    assert result.cycle_confidence == "STRONG"


def test_spotify_annual_regression_weak_confidence():
    """Spotify annual regression: snippet 'annual subscription' → WEAK.
    A Tier 1 caller should override this to UNKNOWN (gate applied in detector.py)."""
    result = detect_cycle("קבלה - Spotify Premium", snippet="annual subscription renews")
    assert result.cycle == "ANNUAL"
    assert result.cycle_confidence == "WEAK"


def test_subject_strong_wins_over_snippet_weak():
    """Subject /mo (STRONG) wins before snippet 'annual subscription' is checked."""
    result = detect_cycle(
        subject="₪12.90/mo Spotify Premium",
        snippet="annual subscription renews",
    )
    assert result.cycle == "MONTHLY"
    assert result.cycle_confidence == "STRONG"
    assert result.cycle_source == "subject_positional"
