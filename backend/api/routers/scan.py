from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Query

from backend.api.routers._db import get_conn, ensure_db
from backend.sources.factory import get_email_source
from backend.detector.detector import process_email
from backend.db.setup import get_summary
from backend.models.subscription import ScanResult, Summary

router = APIRouter()

# ── Scan range shortcuts ──────────────────────────────────────────────────────
_RANGE_DAYS: dict[str, int] = {
    "1m":  30,
    "3m":  90,
    "6m":  180,
    "1y":  365,
    "2y":  730,
    "5y":  1825,
}

# ── Mode-specific detection thresholds ───────────────────────────────────────
# Override the env-var default at runtime; lower threshold = more in Review Queue.
_MODE_REVIEW_THRESHOLD: dict[str, float] = {
    "quick":    0.50,
    "deep":     0.40,
    "forensic": 0.30,
}


@router.post("/api/scan", response_model=ScanResult)
def run_scan(
    mode: Literal["quick", "deep", "forensic"] = Query(
        "deep",
        description="Scan depth: quick (passes 1-2), deep (1-4), forensic (all 6 passes)",
    ),
    scan_range: Literal["1m", "3m", "6m", "1y", "2y", "5y"] | None = Query(
        None,
        description="Shorthand scan range. Overrides date_from when provided.",
    ),
    date_from: datetime | None = Query(
        None,
        description="Scan emails on or after this date (ISO 8601). Ignored if scan_range is set.",
    ),
    date_to: datetime | None = Query(
        None,
        description="Scan emails on or before this date (ISO 8601).",
    ),
):
    """Run the detection pipeline against the configured email source.

    Mode controls which Gmail query passes are executed and the minimum confidence
    threshold for the Review Queue:
      - quick:    passes 1–2, threshold 0.50 (lowest noise)
      - deep:     passes 1–4, threshold 0.40 (recommended)
      - forensic: passes 1–6, threshold 0.30 (maximum recall)

    scan_range shortcuts (e.g. "3m" = last 90 days) take precedence over date_from.
    """
    ensure_db()

    # Resolve date_from from scan_range shortcut
    effective_date_from = date_from
    if scan_range:
        effective_date_from = datetime.now(timezone.utc) - timedelta(days=_RANGE_DAYS[scan_range])

    review_threshold = _MODE_REVIEW_THRESHOLD.get(mode, 0.40)

    source = get_email_source()
    emails = source.fetch(
        date_from=effective_date_from,
        date_to=date_to,
        mode=mode,
    )

    counts = {"scanned": 0, "detected": 0, "flagged": 0, "ignored": 0}

    with get_conn() as conn:
        for email in emails:
            result = process_email(conn, email, review_threshold=review_threshold)
            counts["scanned"] += 1
            if result.disposition == "DETECTED":
                counts["detected"] += 1
            elif result.disposition == "FLAGGED":
                counts["flagged"] += 1
            else:
                counts["ignored"] += 1

    return ScanResult(**counts)


@router.get("/api/summary", response_model=Summary)
def get_spending_summary():
    ensure_db()
    with get_conn() as conn:
        data = get_summary(conn)
    return Summary(**data)
