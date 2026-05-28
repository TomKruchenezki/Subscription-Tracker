"""
Detects billing cycle from subject-line keywords, with fallback to snippet and body_text.
Returns one of: MONTHLY | ANNUAL | QUARTERLY | WEEKLY | UNKNOWN

Snippet and body_text are accepted as secondary/tertiary inputs and are used only
for extraction — they are NEVER stored, logged, or returned as raw values.
Priority: subject → snippet → body_text.

Context-gating:
  Standalone words like "annual", "yearly", "quarterly", "weekly", and "monthly" fire
  only when a billing context word (payment, charge, subscription, renew, invoice,
  receipt, plan, fee, etc.) also appears in the same text.  This prevents body_text
  from a billing email containing incidental mentions (e.g. "Save with Annual plan"
  in a monthly Spotify receipt) from misclassifying the billing cycle.
  Positional constructions ("/mo", "per month", "every week", "/year", "per year")
  are treated as strong signals and fire regardless of surrounding context.
"""
import re
from typing import Literal

BillingCycle = Literal["MONTHLY", "ANNUAL", "QUARTERLY", "WEEKLY", "UNKNOWN"]

# Billing context words that make standalone cycle keywords meaningful.
# A text must contain at least one of these for a "weak" cycle pattern to fire.
# English terms use word boundaries; Hebrew billing words are appended as alternates
# (Hebrew does not use ASCII word boundaries, but space-delimited matching works).
_BILLING_CONTEXT_RE = re.compile(
    r"\b(paid?|pay(?:ment|ing)?|charge[sd]?|charging|billing|billed|bill"
    r"|invoice[sd]?|invoicing|receipt|subscription|subscri(?:be|bed|bing)"
    r"|renew(?:al|ed|ing|s)?|plan|membership|cost|price|fee|dues?|tariff)\b"
    r"|חיוב|תשלום|קבלה|חשבונית|מנוי|חידוש|מחיר|עלות",  # Hebrew billing words
    re.IGNORECASE,
)

# Strong QUARTERLY patterns: positional/compound — fire regardless of context.
_QUARTERLY_STRONG = [
    re.compile(r"\bevery\s+(3|three)\s+months?\b", re.IGNORECASE),
    re.compile(r"\b3[\s-]month\b", re.IGNORECASE),
]

# Weak QUARTERLY pattern: standalone word — requires billing context in same text.
# "Q3 quarterly business review" → UNKNOWN; "quarterly billing" → QUARTERLY.
_QUARTERLY_WEAK = [
    re.compile(r"\bquarterly\b", re.IGNORECASE),
    re.compile(r"\bרבעוני\b"),              # quarterly (Hebrew)
]

# Strong ANNUAL patterns: positional/compound — fire regardless of context.
_ANNUAL_STRONG = [
    re.compile(r"\bper\s+year\b", re.IGNORECASE),
    re.compile(r"/yr\b", re.IGNORECASE),
    re.compile(r"/year\b", re.IGNORECASE),
    re.compile(r"\b1[\s-]year\b", re.IGNORECASE),
    re.compile(r"\b12[\s-]month\b", re.IGNORECASE),
    re.compile(r"\bשנתי\b"),               # annual/yearly (Hebrew)
    re.compile(r"\bכל\s+שנה\b"),           # every year (Hebrew, positional — strong)
]

# Weak ANNUAL patterns: standalone words — require billing context in same text.
# "annual savings" or "annual plan comparison" in body_text → UNKNOWN.
# "annual subscription renews" → ANNUAL (billing context present).
_ANNUAL_WEAK = [
    re.compile(r"\bannual\b", re.IGNORECASE),
    re.compile(r"\byearly\b", re.IGNORECASE),
]

# Strong MONTHLY patterns: positional/compound constructions that inherently imply billing.
# Fire regardless of surrounding context.
_MONTHLY_STRONG = [
    re.compile(r"\bper\s+month\b", re.IGNORECASE),
    re.compile(r"/mo\b", re.IGNORECASE),
    re.compile(r"\bmonth-to-month\b", re.IGNORECASE),
    re.compile(r"\bevery?\s+month\b", re.IGNORECASE),
    re.compile(r"\bחודשי\b"),              # monthly (Hebrew)
    re.compile(r"\bכל\s+חודש\b"),          # every month (Hebrew, positional — strong)
]

# Weak MONTHLY pattern: standalone word — requires billing context in same text.
_MONTHLY_WEAK = [
    re.compile(r"\bmonthly\b", re.IGNORECASE),
]

# Strong WEEKLY patterns: positional constructions — fire regardless of context.
_WEEKLY_STRONG = [
    re.compile(r"\bper\s+week\b", re.IGNORECASE),
    re.compile(r"/week\b", re.IGNORECASE),
    re.compile(r"\bevery\s+week\b", re.IGNORECASE),
]

# Weak WEEKLY pattern: standalone word — requires billing context in same text.
_WEEKLY_WEAK = [
    re.compile(r"\bweekly\b", re.IGNORECASE),
    re.compile(r"\bשבועי\b"),              # weekly (Hebrew, weak — requires billing context)
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

    Standalone cycle words (monthly, weekly) require a billing context word
    (payment, subscription, renew, etc.) in the same text to fire.
    Positional constructions (/mo, per month, every week, /yr) are always strong.
    """
    texts = [subject]
    if snippet:
        texts.append(snippet)
    if body_text:
        texts.append(body_text)

    for text in texts:
        # Compute billing context once per text (shared by all weak patterns below).
        has_billing = bool(_BILLING_CONTEXT_RE.search(text))

        # QUARTERLY — strong patterns fire regardless of context
        for pattern in _QUARTERLY_STRONG:
            if pattern.search(text):
                return "QUARTERLY"
        # QUARTERLY — weak patterns require billing context
        for pattern in _QUARTERLY_WEAK:
            if pattern.search(text) and has_billing:
                return "QUARTERLY"

        # ANNUAL — strong patterns fire regardless of context
        for pattern in _ANNUAL_STRONG:
            if pattern.search(text):
                return "ANNUAL"
        # ANNUAL — weak patterns require billing context
        # Prevents "annual savings" or "annual plan comparison" in body_text from
        # misclassifying a monthly charge (e.g. Spotify ₪12.90/month).
        for pattern in _ANNUAL_WEAK:
            if pattern.search(text) and has_billing:
                return "ANNUAL"

        # MONTHLY — strong patterns first (always fire)
        for pattern in _MONTHLY_STRONG:
            if pattern.search(text):
                return "MONTHLY"
        # MONTHLY — weak pattern: requires billing context
        for pattern in _MONTHLY_WEAK:
            if pattern.search(text) and has_billing:
                return "MONTHLY"

        # WEEKLY — strong patterns first (always fire)
        for pattern in _WEEKLY_STRONG:
            if pattern.search(text):
                return "WEEKLY"
        # WEEKLY — weak pattern: requires billing context
        for pattern in _WEEKLY_WEAK:
            if pattern.search(text) and has_billing:
                return "WEEKLY"

    return "UNKNOWN"
