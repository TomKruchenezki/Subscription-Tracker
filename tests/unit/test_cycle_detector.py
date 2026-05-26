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
])
def test_detect_cycle(subject, expected):
    assert detect_cycle(subject) == expected
