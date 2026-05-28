import pytest
from backend.detector.confidence_scorer import compute_score, score_to_disposition
from backend.detector.pattern_library import PatternType


@pytest.mark.parametrize("tier, pattern, amount, cycle, expected_score, expected_disposition", [
    # Tier 1 + receipt + amount → 0.25 + 0.50 + 0.10 = 0.85 (DETECTED)
    (1, PatternType.RECEIPT,       9.99, "UNKNOWN",  0.85, "DETECTED"),
    # Tier 1 + renewal (no amount) → 0.25 + 0.50 = 0.75 (DETECTED)
    (1, PatternType.RENEWAL,       None, "UNKNOWN",  0.75, "DETECTED"),
    # Tier 1 + promotional → 0.25 - 0.30 = -0.05 → clamped 0.00 (IGNORED)
    (1, PatternType.PROMOTIONAL,   None, "UNKNOWN",  0.00, "IGNORED"),
    # Tier 2 + receipt (no amount) → 0.20 + 0.50 = 0.70 (DETECTED — billing processor receipt)
    (2, PatternType.RECEIPT,       None, "UNKNOWN",  0.70, "DETECTED"),
    # No match + receipt + amount → 0.00 + 0.50 + 0.10 = 0.60 (FLAGGED)
    (0, PatternType.RECEIPT,       9.99, "UNKNOWN",  0.60, "FLAGGED"),
    # No match + promotional → 0.00 - 0.30 = clamped 0.00 (IGNORED)
    (0, PatternType.PROMOTIONAL,   None, "UNKNOWN",  0.00, "IGNORED"),
    # Tier 1 only → 0.25 (IGNORED — billing evidence is required)
    (1, PatternType.NONE,          None, "UNKNOWN",  0.25, "IGNORED"),
])
def test_confidence_scorer(tier, pattern, amount, cycle, expected_score, expected_disposition):
    score = compute_score(tier, pattern, amount, cycle)
    assert score == pytest.approx(expected_score, abs=1e-9)
    assert score_to_disposition(score) == expected_disposition


def test_excluded_domain_scores_zero():
    score = compute_score(-1, PatternType.RECEIPT, 9.99, "MONTHLY")
    assert score == 0.0
    assert score_to_disposition(score) == "IGNORED"


def test_parser_cap_prevents_double_count():
    """Amount + cycle together must not exceed the 0.10 parser cap.
    With new weights: Tier 1 (0.25) + RECEIPT (0.50) + parser cap (0.10) = 0.85.
    Adding a cycle should not push it above 0.85.
    """
    score_both = compute_score(1, PatternType.RECEIPT, 9.99, "MONTHLY")
    score_amount_only = compute_score(1, PatternType.RECEIPT, 9.99, "UNKNOWN")
    # Both cap at 0.10 — combined should not exceed amount-only score
    assert score_both == pytest.approx(score_amount_only, abs=1e-9)
    # Confirm the capped value (0.25 + 0.50 + 0.10 = 0.85)
    assert score_both == pytest.approx(0.85, abs=1e-9)


# ── Phase 3.1: Parser score zeroed for NONE / NOTIFICATION ───────────────────

def test_none_pattern_with_amount_does_not_boost_score():
    """Parser score is zeroed when pattern is NONE — incidental body amount doesn't count.
    Tier 1 (0.25) + NONE (0.00) + amount (zeroed) = 0.25, not 0.35.
    Fixes the 72 false-positive FLAGGED emails from job alerts/newsletters."""
    score = compute_score(1, PatternType.NONE, 9.99, "UNKNOWN")
    assert score == pytest.approx(0.25, abs=1e-9)


def test_none_pattern_score_stays_below_forensic_threshold():
    """Tier 1 + NONE + amount must be below the forensic threshold (0.30) after fix.
    Before fix: 0.25 + 0.00 + 0.10 = 0.35 → FLAGGED (false positive).
    After fix:  0.25 + 0.00 + 0.00 = 0.25 → IGNORED."""
    score = compute_score(1, PatternType.NONE, 9.99, "UNKNOWN")
    assert score < 0.30


def test_receipt_pattern_with_amount_still_boosts():
    """Parser score still counts when billing signal is present (RECEIPT).
    Tier 1 (0.25) + RECEIPT (0.50) + amount (0.10) = 0.85 → unaffected."""
    score = compute_score(1, PatternType.RECEIPT, 9.99, "UNKNOWN")
    assert score == pytest.approx(0.85, abs=1e-9)


def test_notification_pattern_with_amount_no_boost():
    """NOTIFICATION + amount: parser score zeroed; result clamped to 0.00.
    Tier 1 (0.25) + NOTIFICATION (-0.45) + amount (zeroed) = -0.20 → clamped 0.00."""
    score = compute_score(1, PatternType.NOTIFICATION, 9.99, "UNKNOWN")
    assert score == pytest.approx(0.00, abs=1e-9)
