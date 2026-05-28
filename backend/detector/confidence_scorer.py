"""
Weighted confidence scoring formula → score in [0.0, 1.0].

Design principle (Phase 2.8): billing/subscription language is the PRIMARY signal;
provider/domain is SUPPORTING evidence only. Before Phase 2.8 the Tier 1 weight (0.60)
was the dominant factor, causing every email from a known domain to reach the FLAGGED
threshold even with zero billing evidence. The rebalance inverts this: billing patterns
now carry the most weight, and provider alone (Tier 1 = 0.25) falls below all thresholds.

Weights:
  Tier 1 sender:   +0.25  (was 0.60 — provider is supporting evidence only)
  Tier 2 sender:   +0.20  (was 0.30 — payment processor is supporting evidence only)
  Receipt/invoice: +0.50  (was 0.30 — primary billing signal)
  Renewal:         +0.50  (was 0.25 — explicit recurring billing)
  Cancellation:    +0.50  (was 0.20 — explicit lifecycle event)
  Trial started:   +0.45  (was 0.20 — clear subscription relationship)
  Trial end:       +0.45  (was 0.20 — clear subscription relationship)
  Refund:          +0.45  (was 0.25 — implies prior billing relationship)
  Failed payment:  +0.45  (was 0.20 — implies billing relationship)
  Price change:    +0.25  (was 0.15 — informational, weak)
  Promotional:     -0.30  (unchanged)
  Notification:    -0.45  (was -0.35 — stronger suppression)
  Parser (amount detected): +0.10 (capped — see note below)
  Parser (cycle detected):  +0.05 (included in same cap)
  Combined parser cap:       0.10

Note on parser cap: amount (+0.10) and cycle (+0.05) are corroborating
evidence for the same signal. Capping at 0.10 prevents over-weighting parser
output relative to sender and subject signals. Do not remove the cap.

Note on parser score and NONE/NOTIFICATION: parser_score is zeroed when
pattern is NONE or NOTIFICATION. An incidental dollar amount found in the
body_text of a job alert, newsletter, or social notification is not billing
evidence. Without this guard, Tier 1 + NONE + body amount = 0.35, which
exceeds the forensic threshold (0.30) and incorrectly places non-billing
emails in the Review Queue.

Note on NOTIFICATION weight: -0.45 ensures Tier 1 (0.25) + NOTIFICATION =
-0.20, clamped to 0.00 → IGNORED in all modes. Billing patterns (RECEIPT,
RENEWAL, etc.) have higher priority in match_pattern() and always win over
NOTIFICATION, so legitimate billing emails from Tier 1 senders are unaffected.

Key score landmarks (new weights):
  Tier 1 + NONE, no amount:  0.25 → IGNORED all modes
  Tier 1 + NONE + amount:    0.25 → IGNORED all modes (parser score zeroed — see below)
  Tier 1 + RECEIPT + amount: 0.85 → DETECTED
  Tier 1 + CANCELLATION:     0.75 → DETECTED
  Tier 1 + TRIAL_STARTED:    0.70 → DETECTED (at threshold — no amount needed)
  Tier 2 + RECEIPT, no amt:  0.70 → DETECTED (billing processor receipt is strong)
  Tier 0 + RECEIPT + amount: 0.60 → FLAGGED all modes
"""
from backend.detector.pattern_library import PatternType

TIER_WEIGHTS = {1: 0.25, 2: 0.20, 0: 0.00}

PATTERN_WEIGHTS = {
    PatternType.RECEIPT:        0.50,
    PatternType.RENEWAL:        0.50,
    PatternType.CANCELLATION:   0.50,
    PatternType.TRIAL_STARTED:  0.45,
    PatternType.TRIAL_END:      0.45,
    PatternType.REFUND:         0.45,
    PatternType.FAILED_PAYMENT: 0.45,
    PatternType.PRICE_CHANGE:   0.25,
    PatternType.PROMOTIONAL:   -0.30,
    PatternType.NOTIFICATION:  -0.45,
    PatternType.NONE:           0.00,
}

_AMOUNT_DELTA = 0.10
_CYCLE_DELTA = 0.05
_PARSER_CAP = 0.10


def compute_score(
    tier: int,
    pattern: PatternType,
    amount: float | None,
    billing_cycle: str,
) -> float:
    """
    Returns a confidence score in [0.0, 1.0].
    tier: 1 (Tier 1 domain), 2 (Tier 2 domain), 0 (no match), -1 (excluded)
    """
    if tier == -1:
        return 0.0

    tier_score = TIER_WEIGHTS.get(tier, 0.0)
    pattern_score = PATTERN_WEIGHTS.get(pattern, 0.0)

    amount_delta = _AMOUNT_DELTA if amount is not None else 0.0
    cycle_delta = _CYCLE_DELTA if billing_cycle != "UNKNOWN" else 0.0
    parser_score = min(amount_delta + cycle_delta, _PARSER_CAP)

    # Parser score only counts when there is subject-level billing evidence.
    # NONE and NOTIFICATION patterns indicate no billing language in the subject;
    # an amount or cycle found only in body_text is not reliable billing evidence.
    if pattern in (PatternType.NONE, PatternType.NOTIFICATION):
        parser_score = 0.0

    raw = tier_score + pattern_score + parser_score
    return max(0.0, min(1.0, raw))


def score_to_disposition(score: float, auto_detect_threshold: float = 0.70,
                          review_threshold: float = 0.40) -> str:
    """Convert a confidence score to a disposition string."""
    if score >= auto_detect_threshold:
        return "DETECTED"
    if score >= review_threshold:
        return "FLAGGED"
    return "IGNORED"
