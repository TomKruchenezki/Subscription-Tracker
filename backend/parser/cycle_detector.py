"""
Detects billing cycle from subject-line keywords, with fallback to snippet and body_text.
Returns one of: MONTHLY | ANNUAL | QUARTERLY | WEEKLY | UNKNOWN

Snippet and body_text are accepted as secondary/tertiary inputs and are used only
for extraction — they are NEVER stored, logged, or returned as raw values.
Priority: subject → snippet → body_text.
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


def detect_cycle(
    subject: str,
    snippet: str | None = None,
    body_text: str | None = None,
) -> BillingCycle:
    """Return billing cycle detected from subject keywords, or UNKNOWN.

    Falls back to snippet then body_text if no result found. All inputs are
    processing-time only — never stored or logged.
    Priority: subject → snippet → body_text.
    """
    texts = [subject]
    if snippet:
        texts.append(snippet)
    if body_text:
        texts.append(body_text)

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
