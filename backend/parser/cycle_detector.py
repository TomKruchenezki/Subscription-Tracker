"""
Detects billing cycle from subject-line keywords, with fallback to snippet.
Returns one of: MONTHLY | ANNUAL | QUARTERLY | WEEKLY | UNKNOWN

Snippet is accepted as a secondary input and is used only for extraction —
it is NEVER stored, logged, or returned as a raw value.
"""
import re
from typing import Literal

BillingCycle = Literal["MONTHLY", "ANNUAL", "QUARTERLY", "WEEKLY", "UNKNOWN"]

_QUARTERLY_PATTERNS = [
    re.compile(r"\bquarterly\b", re.IGNORECASE),
    re.compile(r"\bevery\s+(3|three)\s+months?\b", re.IGNORECASE),
    re.compile(r"\b3[\s-]month\b", re.IGNORECASE),
    re.compile(r"\bרבעוני\b"),              # quarterly (Hebrew)
]

_ANNUAL_PATTERNS = [
    re.compile(r"\bannual\b", re.IGNORECASE),
    re.compile(r"\byearly\b", re.IGNORECASE),
    re.compile(r"\bper\s+year\b", re.IGNORECASE),
    re.compile(r"/yr\b", re.IGNORECASE),
    re.compile(r"/year\b", re.IGNORECASE),
    re.compile(r"\b1[\s-]year\b", re.IGNORECASE),
    re.compile(r"\b12[\s-]month\b", re.IGNORECASE),
    re.compile(r"\bשנתי\b"),               # annual/yearly (Hebrew)
]

_MONTHLY_PATTERNS = [
    re.compile(r"\bmonthly\b", re.IGNORECASE),
    re.compile(r"\bper\s+month\b", re.IGNORECASE),
    re.compile(r"/mo\b", re.IGNORECASE),
    re.compile(r"\bmonth-to-month\b", re.IGNORECASE),
    re.compile(r"\bevery?\s+month\b", re.IGNORECASE),
    re.compile(r"\bחודשי\b"),              # monthly (Hebrew)
]

_WEEKLY_PATTERNS = [
    re.compile(r"\bweekly\b", re.IGNORECASE),
    re.compile(r"\bper\s+week\b", re.IGNORECASE),
    re.compile(r"/week\b", re.IGNORECASE),
    re.compile(r"\bevery\s+week\b", re.IGNORECASE),
]


def detect_cycle(subject: str, snippet: str | None = None) -> BillingCycle:
    """Return billing cycle detected from subject keywords, or UNKNOWN.

    Falls back to snippet if subject yields no result. Snippet is
    processing-time only — never stored or logged.
    """
    texts = [subject]
    if snippet:
        texts.append(snippet)

    for text in texts:
        # Check QUARTERLY first (more specific than MONTHLY)
        for pattern in _QUARTERLY_PATTERNS:
            if pattern.search(text):
                return "QUARTERLY"

        for pattern in _ANNUAL_PATTERNS:
            if pattern.search(text):
                return "ANNUAL"

        for pattern in _MONTHLY_PATTERNS:
            if pattern.search(text):
                return "MONTHLY"

        for pattern in _WEEKLY_PATTERNS:
            if pattern.search(text):
                return "WEEKLY"

    return "UNKNOWN"
