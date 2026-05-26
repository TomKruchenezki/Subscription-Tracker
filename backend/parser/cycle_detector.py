"""
Detects billing cycle from subject-line keywords.
Returns one of: MONTHLY | ANNUAL | WEEKLY | UNKNOWN
"""
import re
from typing import Literal

BillingCycle = Literal["MONTHLY", "ANNUAL", "WEEKLY", "UNKNOWN"]

_MONTHLY_PATTERNS = [
    re.compile(r"\bmonthly\b", re.IGNORECASE),
    re.compile(r"\bper\s+month\b", re.IGNORECASE),
    re.compile(r"/mo\b", re.IGNORECASE),
    re.compile(r"\bmonth-to-month\b", re.IGNORECASE),
    re.compile(r"\beverv?\s+month\b", re.IGNORECASE),
]

_ANNUAL_PATTERNS = [
    re.compile(r"\bannual\b", re.IGNORECASE),
    re.compile(r"\byearly\b", re.IGNORECASE),
    re.compile(r"\bper\s+year\b", re.IGNORECASE),
    re.compile(r"/yr\b", re.IGNORECASE),
    re.compile(r"/year\b", re.IGNORECASE),
    re.compile(r"\b1[\s-]year\b", re.IGNORECASE),
    re.compile(r"\b12[\s-]month\b", re.IGNORECASE),
]

_WEEKLY_PATTERNS = [
    re.compile(r"\bweekly\b", re.IGNORECASE),
    re.compile(r"\bper\s+week\b", re.IGNORECASE),
    re.compile(r"/week\b", re.IGNORECASE),
    re.compile(r"\bevery\s+week\b", re.IGNORECASE),
]


def detect_cycle(subject: str) -> BillingCycle:
    """Return billing cycle detected from subject keywords, or UNKNOWN."""
    for pattern in _ANNUAL_PATTERNS:
        if pattern.search(subject):
            return "ANNUAL"

    for pattern in _MONTHLY_PATTERNS:
        if pattern.search(subject):
            return "MONTHLY"

    for pattern in _WEEKLY_PATTERNS:
        if pattern.search(subject):
            return "WEEKLY"

    return "UNKNOWN"
