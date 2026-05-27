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
