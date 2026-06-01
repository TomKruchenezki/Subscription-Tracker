"""
Detects billing cycle from subject-line keywords, with fallback to snippet and body_text.
Returns a CycleResult(cycle, cycle_source, cycle_confidence).

cycle values: MONTHLY | ANNUAL | QUARTERLY | WEEKLY | UNKNOWN
cycle_source: where the winning match was found
cycle_confidence: STRONG (positional patterns) | WEAK (context-word patterns) | NONE (no match)

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

Weak-cycle safety (Phase 3.8):
  WEAK matches from snippet or subject context words should not override a known
  monthly charge for Tier 1 providers. The caller (detector.py) is responsible for
  applying the gate: when cycle_confidence == "WEAK" and the provider is Tier 1, the
  billing_cycle is set to UNKNOWN instead of using the weak guess.
"""
import re
from dataclasses import dataclass
from typing import Literal

BillingCycle = Literal["MONTHLY", "ANNUAL", "QUARTERLY", "WEEKLY", "UNKNOWN"]
CycleConfidence = Literal["STRONG", "WEAK", "NONE"]


@dataclass(frozen=True)
class CycleResult:
    """Return value from detect_cycle().

    cycle:            The detected billing cycle string, or UNKNOWN.
    cycle_source:     Which text field and pattern strength produced the match.
                      One of: subject_positional | subject_context |
                               snippet_positional | snippet_context |
                               body_positional | none
    cycle_confidence: STRONG (positional match) | WEAK (context-word match) | NONE (no match)
    """
    cycle: BillingCycle
    cycle_source: str
    cycle_confidence: CycleConfidence


# ── Billing context word gate ──────────────────────────────────────────────────

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

# ── Pattern lists ──────────────────────────────────────────────────────────────

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

# ── No-match sentinel ──────────────────────────────────────────────────────────

_NO_MATCH = CycleResult(cycle="UNKNOWN", cycle_source="none", cycle_confidence="NONE")


def detect_cycle(
    subject: str,
    snippet: str | None = None,
    body_text: str | None = None,
) -> CycleResult:
    """Return CycleResult(cycle, cycle_source, cycle_confidence).

    Falls back to snippet then body_text if no result found in subject.
    Priority: subject → snippet → body_text.

    cycle_confidence == STRONG: positional pattern matched (reliable).
    cycle_confidence == WEAK:   context-word pattern matched (less reliable;
        callers should apply a Tier 1 override gate — see detector.py).

    body_text restriction: weak patterns (standalone "annual", "weekly", etc.) are
    NOT applied to body_text. Billing receipt bodies almost always contain billing
    context words, so a weak pattern like "annual" + "subscription" in body_text
    would misclassify a monthly Spotify charge that mentions "annual plan" incidentally.
    Only strong positional patterns (/year, per month, etc.) fire from body_text.
    """
    # (source_label, is_body_text, text) triples — label carries origin for CycleResult.
    sources: list[tuple[str, bool, str]] = [("subject", False, subject)]
    if snippet:
        sources.append(("snippet", False, snippet))
    if body_text:
        sources.append(("body", True, body_text))

    for source_label, is_body_text, text in sources:

        # Compute billing context once per text (shared by all weak patterns below).
        has_billing = bool(_BILLING_CONTEXT_RE.search(text))

        # QUARTERLY — strong patterns fire regardless of source
        for pattern in _QUARTERLY_STRONG:
            if pattern.search(text):
                return CycleResult("QUARTERLY", f"{source_label}_positional", "STRONG")
        # QUARTERLY — weak patterns: subject/snippet only
        if not is_body_text:
            for pattern in _QUARTERLY_WEAK:
                if pattern.search(text) and has_billing:
                    return CycleResult("QUARTERLY", f"{source_label}_context", "WEAK")

        # ANNUAL — strong patterns fire regardless of source
        for pattern in _ANNUAL_STRONG:
            if pattern.search(text):
                return CycleResult("ANNUAL", f"{source_label}_positional", "STRONG")
        # ANNUAL — weak patterns: subject/snippet only
        # body_text exclusion prevents "annual savings" or "Save with Annual plan" in a
        # monthly billing email body from misclassifying the cycle.
        if not is_body_text:
            for pattern in _ANNUAL_WEAK:
                if pattern.search(text) and has_billing:
                    return CycleResult("ANNUAL", f"{source_label}_context", "WEAK")

        # MONTHLY — strong patterns fire regardless of source
        for pattern in _MONTHLY_STRONG:
            if pattern.search(text):
                return CycleResult("MONTHLY", f"{source_label}_positional", "STRONG")
        # MONTHLY — weak patterns: subject/snippet only
        if not is_body_text:
            for pattern in _MONTHLY_WEAK:
                if pattern.search(text) and has_billing:
                    return CycleResult("MONTHLY", f"{source_label}_context", "WEAK")

        # WEEKLY — strong patterns fire regardless of source
        for pattern in _WEEKLY_STRONG:
            if pattern.search(text):
                return CycleResult("WEEKLY", f"{source_label}_positional", "STRONG")
        # WEEKLY — weak patterns: subject/snippet only
        if not is_body_text:
            for pattern in _WEEKLY_WEAK:
                if pattern.search(text) and has_billing:
                    return CycleResult("WEEKLY", f"{source_label}_context", "WEAK")

    return _NO_MATCH
