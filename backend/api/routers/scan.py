from datetime import datetime
from fastapi import APIRouter, Query
from backend.api.routers._db import get_conn, ensure_db
from backend.sources.factory import get_email_source
from backend.detector.detector import process_email
from backend.db.setup import get_summary
from backend.models.subscription import ScanResult, Summary

router = APIRouter()


@router.post("/api/scan", response_model=ScanResult)
def run_scan(
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
):
    """Run the detection pipeline against the configured email source."""
    ensure_db()
    source = get_email_source()
    emails = source.fetch(date_from=date_from, date_to=date_to)

    counts = {"scanned": 0, "detected": 0, "flagged": 0, "ignored": 0}

    with get_conn() as conn:
        for email in emails:
            result = process_email(conn, email)
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
