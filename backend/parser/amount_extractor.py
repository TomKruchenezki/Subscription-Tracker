"""
Extracts a subscription amount and currency from an email subject line,
with fallback to the Gmail snippet and then body_text when the subject yields no result.

Only returns amounts in the plausible subscription range: $0.99 – $9,999.99.
Returns (None, None) for:
  - promotional subjects ("50% off"),
  - non-monetary contexts (profile views, writing suggestions, connection counts, etc.),
  - out-of-range amounts,
  - text with no detectable amount.

Snippet and body_text are accepted as secondary/tertiary inputs and are used only
for extraction — they are NEVER stored, logged, or returned as raw values.
Priority: subject → snippet → body_text.
"""
import html
import re

# Promotional patterns to reject before extracting amounts
_PROMO_PATTERNS = [
    re.compile(r"\b\d+%\s*off\b", re.IGNORECASE),
    re.compile(r"\bsave\s+\d+%\b", re.IGNORECASE),
    re.compile(r"\b(get|earn)\s+\d+%\b", re.IGNORECASE),
    re.compile(r"\b\d+%\s+(discount|savings)\b", re.IGNORECASE),
]

# Non-monetary context patterns: when any of these match, the text contains
# numbers that look like prices but are actually statistics, IDs, or other
# non-billing quantities. Reject ALL amount extraction from such text.
_NON_MONETARY_PATTERNS = [
    # Social/profile metrics (LinkedIn, Twitter, etc.)
    re.compile(r"\b\d+\s*(searches?|profile\s+views?|connections?|followers?|endorsements?)\b", re.IGNORECASE),
    re.compile(r"\b(searches?|views?|connections?|followers?|results?|impressions?)\s+(this|in\s+the)\s+(week|month|year|last)\b", re.IGNORECASE),
    re.compile(r"\bappeared\s+in\s+\d+\s+search", re.IGNORECASE),
    re.compile(r"\d+\s+(people\s+)?viewed\s+your\b", re.IGNORECASE),
    re.compile(r"\byour\s+(profile|post|article)\s+(was\s+)?(viewed|liked|commented|shared)\s+\d+", re.IGNORECASE),
    # Writing/productivity stats (Grammarly, etc.)
    re.compile(r"\b\d+\s+(writing\s+)?(suggestions?|corrections?|improvements?|issues?|errors?|alerts?|fixes?)\b", re.IGNORECASE),
    re.compile(r"\b\d+\s+(words?\s+(written|typed|used)?|characters?|pages?\s+written)\b", re.IGNORECASE),
    re.compile(r"\bwriting\s+(score|report|stats?|activity|highlights?)\b", re.IGNORECASE),
    # Booking / reference / ID patterns — numbers that are identifiers, not prices
    re.compile(r"\b(booking|reference|order|confirmation|ticket|case|transaction|invoice)\s+(?:#|no\.?|number|num|id)?\s*\d{5,}\b", re.IGNORECASE),
    re.compile(r"\b[A-Z]{2,6}-\d{4,}\b"),  # reference codes like TXN-20240115, INV-2024001
]

# Currency symbol / code → ISO 4217 code
_CURRENCY_MAP = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "¥": "JPY",
    "₹": "INR",
    "₪": "ILS",
    "CAD": "CAD",
    "AUD": "AUD",
    "USD": "USD",
    "EUR": "EUR",
    "GBP": "GBP",
    "JPY": "JPY",
    "INR": "INR",
    "ILS": "ILS",
}

_AMOUNT_RE = re.compile(
    r"(?P<sym>[$€£¥₹₪])(?P<amount>\d{1,5}(?:\.\d{1,2})?)"
    r"|(?P<amount2>\d{1,5}(?:\.\d{1,2})?)\s*(?P<code>USD|EUR|GBP|CAD|AUD|JPY|INR|ILS)",
    re.IGNORECASE,
)

_MIN_AMOUNT = 0.99
_MAX_AMOUNT = 9_999.99   # raised from 999.99 to capture annual enterprise plans


def _clean_snippet(text: str) -> str:
    """Unescape HTML entities that Gmail includes in snippets (e.g. &amp; &#39;)."""
    return html.unescape(text)


def _extract_from_text(text: str) -> tuple[float | None, str | None]:
    """Inner extraction logic — shared between subject, snippet, and body_text paths."""
    # Reject promotional contexts
    for promo in _PROMO_PATTERNS:
        if promo.search(text):
            return (None, None)

    # Reject non-monetary contexts (stats, IDs, social metrics)
    for non_monetary in _NON_MONETARY_PATTERNS:
        if non_monetary.search(text):
            return (None, None)

    for match in _AMOUNT_RE.finditer(text):
        if match.group("sym"):
            raw = float(match.group("amount"))
            currency = _CURRENCY_MAP.get(match.group("sym"), "USD")
        else:
            raw = float(match.group("amount2"))
            currency = _CURRENCY_MAP.get(match.group("code").upper(), "USD")

        if _MIN_AMOUNT <= raw <= _MAX_AMOUNT:
            return (raw, currency)

    return (None, None)


def extract_amount(
    subject: str,
    snippet: str | None = None,
    body_text: str | None = None,
) -> tuple[float | None, str | None]:
    """Return (amount, currency_code) or (None, None).

    Tries subject first, then snippet, then body_text.
    All inputs are processing-time only — never stored or logged.
    Priority: subject → snippet → body_text.

    Non-monetary context guard: if a text contains profile-view counts,
    writing statistics, booking reference numbers, or other non-monetary
    quantities, amount extraction is suppressed for that text only.
    """
    result = _extract_from_text(subject)
    if result != (None, None):
        return result

    if snippet:
        result = _extract_from_text(_clean_snippet(snippet))
        if result != (None, None):
            return result

    if body_text:
        result = _extract_from_text(_clean_snippet(body_text))
        if result != (None, None):
            return result

    return (None, None)
