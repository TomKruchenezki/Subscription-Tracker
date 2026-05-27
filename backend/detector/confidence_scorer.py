"""
Weighted confidence scoring formula → score in [0.0, 1.0].

Weights:
  Tier 1 sender:   +0.60
  Tier 2 sender:   +0.30
  Receipt/invoice: +0.30
  Renewal:         +0.25
  Refund:          +0.25  (implies prior billing relationship)
  Trial end:       +0.20
  Trial started:   +0.20
  Cancellation:    +0.20
  Failed payment:  +0.20
  Price change:    +0.15  (informational, not transactional)
  Promotional:     -0.30
  Notification:    -0.35  (non-subscription signal: social alerts, policy updates, travel)
  Parser (amount detected): +0.10 (capped — see note below)
  Parser (cycle detected):  +0.05 (included in same cap)
  Combined parser cap:       0.10

Note on parser cap: amount (+0.10) and cycle (+0.05) are corroborating
evidence for the same signal. Capping at 0.10 prevents over-weighting parser
output relative to sender and subject signals. Do not remove the cap.

Note on NOTIFICATION weight: -0.35 (not -0.30) ensures Tier 1 + NOTIFICATION
= 0.60 - 0.35 = 0.25, which is below the forensic-mode threshold of 0.30.
With -0.30 it would be exactly 0.30 → FLAGGED. Billing patterns (RECEIPT,
RENEWAL, etc.) have higher priority in match_pattern() and always win over
NOTIFICATION, so legitimate billing emails from Tier 1 senders are unaffected.
"""
from backend.detector.pattern_library import PatternType

TIER_WEIGHTS = {1: 0.60, 2: 0.30, 0: 0.00}

PATTERN_WEIGHTS = {
    PatternType.RECEIPT:        0.30,
    PatternType.RENEWAL:        0.25,
    PatternType.REFUND:         0.25,
    PatternType.TRIAL_END:      0.20,
    PatternType.TRIAL_STARTED:  0.20,
    PatternType.CANCELLATION:   0.20,
    PatternType.FAILED_PAYMENT: 0.20,
    PatternType.PRICE_CHANGE:   0.15,
    PatternType.PROMOTIONAL:   -0.30,
    PatternType.NOTIFICATION:  -0.35,
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
