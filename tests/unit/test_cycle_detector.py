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
