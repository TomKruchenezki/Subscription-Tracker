"""
Async scan router — background scan job with progress tracking.

POST /api/scan/start  → creates a scan_job record, spawns a background thread,
                        returns {scan_id, status, mode, scan_range} immediately.

GET  /api/scan/status/{scan_id}  → reads from scan_jobs table, returns progress.

The background thread (_run_scan_job) does the full forensic scan in batches of
BATCH_SIZE=50 messages. Progress (processed_count, detected, flagged, ignored,
body_fetched, body_skipped) is written to scan_jobs after each batch.

Smart body-fetch triage: _should_fetch_body() in gmail.py skips format="full"
for NOTIFICATION subjects, excluded domains, and PROMOTIONAL+Tier0 senders — the
three categories that will always be IGNORED regardless of body content (~94% of
emails in a typical forensic scan). Billing candidates always get body fetched.

Privacy: This router logs only counts and the first 8 chars of scan_id.
No subjects, sender addresses, or email content appears in any log line.
"""
import json
import logging
import math
import os
import threading
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.api.routers._db import ensure_db, get_conn
from backend.db.setup import (
    create_scan_job,
    get_active_gmail_account,
    get_running_scan_jobs,
    get_scan_job,
    update_scan_job,
)
from backend.detector.detector import process_email

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Constants ────────────────────────────────────────────────────────────────

BATCH_SIZE = 50

_RANGE_DAYS: dict[str, int] = {
    "1m":  30,
    "3m":  90,
    "6m":  180,
    "1y":  365,
    "2y":  730,
    "5y":  1825,
}

_MODE_REVIEW_THRESHOLD: dict[str, float] = {
    "quick":    0.50,
    "deep":     0.40,
    "forensic": 0.30,
}

_MODE_CONTENT_ACCESS: dict[str, str] = {
    "quick":    "metadata_plus_snippet",
    "deep":     "metadata_plus_snippet",
    "forensic": "body_text_ephemeral",
}


# ── Response model ────────────────────────────────────────────────────────────

class ScanJobStatus(BaseModel):
    scan_id: str
    mode: str
    scan_range: str | None
    content_access_level: str
    status: str
    total_ids: int
    processed_count: int
    detected_count: int
    flagged_count: int
    ignored_count: int
    body_fetched_count: int
    body_skipped_count: int
    body_failed_count: int
    error_message: str | None
    created_at: str
    started_at: str | None
    completed_at: str | None
    last_activity_at: str | None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/api/scan/start", response_model=ScanJobStatus)
def start_scan(
    mode: Literal["quick", "deep", "forensic"] = Query(
        "forensic",
        description="Scan depth. Forensic uses background job + progress tracking.",
    ),
    scan_range: Literal["1m", "3m", "6m", "1y", "2y", "5y"] | None = Query(
        None,
        description="Shorthand scan range (e.g. '1y' = last 365 days).",
    ),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
):
    """Start a background scan job. Returns immediately with a scan_id.

    Poll GET /api/scan/status/{scan_id} for live progress updates.

    Returns 409 if no active Gmail account is connected (mock mode is not
    supported for background scans — use POST /api/scan for mock mode).
    """
    ensure_db()

    use_mock = os.getenv("USE_MOCK", "true").lower() not in {"false", "0", "no"}
    if use_mock:
        raise HTTPException(
            status_code=400,
            detail=(
                "Background scan requires USE_MOCK=false. "
                "Use POST /api/scan for mock-mode scanning."
            ),
        )

    # Resolve date range
    effective_date_from = date_from
    if scan_range and not date_from:
        effective_date_from = datetime.now(timezone.utc) - timedelta(days=_RANGE_DAYS[scan_range])

    db_path = os.getenv("DB_PATH", "data/subscriptions.db")
    content_access_level = _MODE_CONTENT_ACCESS[mode]
    review_threshold = _MODE_REVIEW_THRESHOLD.get(mode, 0.40)

    with get_conn() as conn:
        account_row = get_active_gmail_account(conn)
        if account_row is None:
            raise HTTPException(
                status_code=409,
                detail=(
                    "No active Gmail account connected. "
                    "Visit /accounts to connect Gmail first."
                ),
            )
        account_id = account_row["account_id"]

        scan_id = str(uuid.uuid4())
        create_scan_job(
            conn,
            scan_id=scan_id,
            account_id=account_id,
            mode=mode,
            scan_range=scan_range,
            content_access_level=content_access_level,
        )
        conn.commit()

    logger.info(
        "[Scan %s] Created: mode=%s range=%s access=%s account=%s",
        scan_id[:8], mode, scan_range, content_access_level, account_id[:8] if account_id else "n/a",
    )

    # Spawn background thread — daemon=True so it doesn't block server shutdown
    t = threading.Thread(
        target=_run_scan_job,
        args=(scan_id, db_path, account_id, mode, scan_range,
              effective_date_from, date_to, review_threshold, content_access_level),
        daemon=True,
    )
    t.start()

    # Return the initial job status
    with get_conn() as conn:
        row = get_scan_job(conn, scan_id)

    return _row_to_status(row)


@router.get("/api/scan/status/{scan_id}", response_model=ScanJobStatus)
def get_scan_status(scan_id: str):
    """Poll for background scan job progress.

    Returns 404 if the scan_id is unknown.
    """
    ensure_db()
    with get_conn() as conn:
        row = get_scan_job(conn, scan_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Scan job {scan_id!r} not found.")
    return _row_to_status(row)


# ── Background worker ─────────────────────────────────────────────────────────

def _run_scan_job(
    scan_id: str,
    db_path: str,
    account_id: str,
    mode: str,
    scan_range: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
    review_threshold: float,
    content_access_level: str,
) -> None:
    """Background scan worker. Runs in a daemon thread.

    Phase 1 — Collect: calls fetch_ids() to get all message IDs across passes.
    Phase 2 — Process: works through IDs in batches of BATCH_SIZE, fetching
               metadata + (optionally) body, calling process_email(), committing
               and updating scan_jobs progress after each batch.

    Privacy: this function logs only counts and the first 8 chars of scan_id.
    No subjects, sender addresses, account IDs, or email content is logged.
    """
    from backend.db.setup import get_connection
    from backend.sources.gmail import GmailEmailSource, _should_fetch_body

    conn = get_connection(db_path)
    tag = scan_id[:8]   # short prefix for log lines — not identifying

    try:
        # ── Phase 1: Collect message IDs ──────────────────────────────────────
        logger.info("[Scan %s] Phase 1: collecting message IDs (mode=%s)", tag, mode)
        update_scan_job(conn, scan_id, status="collecting", started_at=_now())
        conn.commit()

        source = GmailEmailSource(account_id=account_id)
        msg_ids = source.fetch_ids(date_from=date_from, date_to=date_to, mode=mode)

        update_scan_job(
            conn, scan_id,
            status="processing",
            total_ids=len(msg_ids),
            collected_ids=json.dumps(msg_ids),
        )
        conn.commit()
        logger.info("[Scan %s] Phase 1 done: %d unique IDs", tag, len(msg_ids))

        # ── Phase 2: Process in batches ───────────────────────────────────────
        fetch_body = content_access_level == "body_text_ephemeral"
        detected = flagged = ignored = 0
        body_fetched = body_skipped = body_failed = 0
        num_batches = math.ceil(len(msg_ids) / BATCH_SIZE) if msg_ids else 0

        for batch_idx, i in enumerate(range(0, len(msg_ids), BATCH_SIZE)):
            batch = msg_ids[i : i + BATCH_SIZE]

            for msg_id in batch:
                metadata = source._fetch_metadata(msg_id)
                if metadata is None:
                    continue

                if fetch_body:
                    if _should_fetch_body(metadata):
                        body = source._fetch_body(msg_id)
                        metadata.body_text = body
                        if body:
                            body_fetched += 1
                        else:
                            body_failed += 1
                    else:
                        body_skipped += 1

                result = process_email(conn, metadata, review_threshold=review_threshold)
                if result.disposition == "DETECTED":
                    detected += 1
                elif result.disposition == "FLAGGED":
                    flagged += 1
                else:
                    ignored += 1

            conn.commit()

            processed_so_far = min(i + len(batch), len(msg_ids))
            update_scan_job(
                conn, scan_id,
                processed_count=processed_so_far,
                detected_count=detected,
                flagged_count=flagged,
                ignored_count=ignored,
                body_fetched_count=body_fetched,
                body_skipped_count=body_skipped,
                body_failed_count=body_failed,
            )
            conn.commit()

            logger.info(
                "[Scan %s] Batch %d/%d: processed=%d det=%d flagged=%d ignored=%d "
                "body_fetched=%d body_skipped=%d",
                tag, batch_idx + 1, num_batches,
                processed_so_far, detected, flagged, ignored,
                body_fetched, body_skipped,
            )

        # ── Done ──────────────────────────────────────────────────────────────
        update_scan_job(conn, scan_id, status="completed", completed_at=_now())
        conn.commit()
        logger.info(
            "[Scan %s] Complete: %d processed | det=%d flagged=%d ignored=%d | "
            "body_fetched=%d body_skipped=%d body_failed=%d",
            tag, len(msg_ids), detected, flagged, ignored,
            body_fetched, body_skipped, body_failed,
        )

    except Exception as exc:
        logger.error("[Scan %s] Failed: %s — %s", tag, type(exc).__name__, str(exc)[:200])
        try:
            update_scan_job(
                conn, scan_id,
                status="failed",
                error_message=str(exc)[:500],
            )
            conn.commit()
        except Exception:
            pass
    finally:
        conn.close()


# ── Startup interrupt recovery ────────────────────────────────────────────────

def mark_interrupted_jobs(db_path: str) -> None:
    """Mark any collecting/processing jobs as 'interrupted'.

    Called from the FastAPI lifespan hook on server startup. If the server
    was restarted mid-scan, any in-flight jobs are marked interrupted.
    The user can safely re-run — email_records dedup prevents double-counting.
    """
    from backend.db.setup import get_connection
    conn = get_connection(db_path)
    try:
        jobs = get_running_scan_jobs(conn)
        if not jobs:
            return
        for job in jobs:
            update_scan_job(
                conn, job["scan_id"],
                status="interrupted",
                error_message="Server restarted during scan. Safe to re-run.",
            )
        conn.commit()
        logger.info(
            "Startup: marked %d interrupted scan job(s) (server restart recovery)",
            len(jobs),
        )
    finally:
        conn.close()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _row_to_status(row: object) -> ScanJobStatus:
    return ScanJobStatus(
        scan_id=row["scan_id"],
        mode=row["mode"],
        scan_range=row["scan_range"],
        content_access_level=row["content_access_level"],
        status=row["status"],
        total_ids=row["total_ids"] or 0,
        processed_count=row["processed_count"] or 0,
        detected_count=row["detected_count"] or 0,
        flagged_count=row["flagged_count"] or 0,
        ignored_count=row["ignored_count"] or 0,
        body_fetched_count=row["body_fetched_count"] or 0,
        body_skipped_count=row["body_skipped_count"] or 0,
        body_failed_count=row["body_failed_count"] or 0,
        error_message=row["error_message"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        last_activity_at=row["last_activity_at"],
    )


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
