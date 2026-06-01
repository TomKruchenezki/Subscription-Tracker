"""
POST /api/email-records/{record_id}/dismiss — persist a Review Queue dismissal.
GET  /api/email-records/dismissed-ids       — return dismissed record IDs.

Privacy: dismissal stores only the record_id and correction_type ('DISMISSED_EMAIL').
No raw email content (subject, sender, snippet, body) is read or written.
"""
import logging
import os
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from backend.db.setup import (
    dismiss_email_record,
    get_dismissed_email_ids,
    mark_one_time,
    get_attachments_for_record,
    get_attachment_fields_for_record,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/email-records", tags=["email-records"])


def _get_db() -> sqlite3.Connection:
    """Dependency: open a DB connection for the request and close after."""
    import sqlite3 as _sqlite3
    db_path = os.getenv("DB_PATH", "data/subscriptions.db")
    conn = _sqlite3.connect(db_path)
    conn.row_factory = _sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def _source_provider_filter() -> str | None:
    """Return 'GMAIL' in Gmail mode; None in mock mode (show all)."""
    use_mock = os.getenv("USE_MOCK", "true").lower() not in ("false", "0", "no")
    return None if use_mock else "GMAIL"


@router.get("/dismissed-ids")
def get_dismissed_ids(
    conn: sqlite3.Connection = Depends(_get_db),
) -> list[str]:
    """Return a list of email record IDs that the user has dismissed.

    Used by ReviewQueue.tsx on page load to pre-populate the dismissed set,
    so previously dismissed records stay hidden across page reloads.

    Privacy-safe: returns only record_id strings (structured IDs), no raw content.
    """
    source_provider = _source_provider_filter()
    return sorted(get_dismissed_email_ids(conn, source_provider=source_provider))


@router.post("/{record_id}/mark-one-time")
def mark_record_one_time(
    record_id: str,
    conn: sqlite3.Connection = Depends(_get_db),
) -> dict[str, str | bool]:
    """Mark an email_record as a one-time payment (not a recurring subscription).

    Persists a MARKED_ONE_TIME correction in user_corrections.
    Affects future reprocessing: the record will be treated as a one-time event,
    not used to create a recurring subscription.
    Privacy-safe: stores only structured IDs and correction_type.
    """
    row = conn.execute(
        "SELECT record_id, sender_address FROM email_records WHERE record_id = ?", (record_id,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Email record not found")

    mark_one_time(
        conn,
        email_record_id=record_id,
        payment_event_id=None,
        sender_address=row["sender_address"],
    )
    conn.commit()
    return {"record_id": record_id, "marked_one_time": True}


@router.get("/{record_id}/attachments")
def list_record_attachments(
    record_id: str,
    conn: sqlite3.Connection = Depends(_get_db),
) -> list[dict]:
    """Return attachment metadata + structured PDF-derived evidence for an email_record.

    Phase 3.7. Safe structured fields only — no raw PDF text or bytes (those are never
    stored). Each item is the attachment metadata with an "extracted_fields" object
    (provider, amount, currency, dates, inferred_cycle, coded reason tokens) or null.
    """
    attachments = get_attachments_for_record(conn, record_id)
    fields = get_attachment_fields_for_record(conn, record_id)
    fields_by_attachment: dict[str, dict] = {}
    for f in fields:
        fields_by_attachment.setdefault(f["attachment_row_id"], dict(f))

    out: list[dict] = []
    for a in attachments:
        item = dict(a)
        item["extracted_fields"] = fields_by_attachment.get(a["attachment_row_id"])
        out.append(item)
    return out


@router.post("/{record_id}/dismiss")
def dismiss_record(
    record_id: str,
    conn: sqlite3.Connection = Depends(_get_db),
) -> dict[str, str | bool]:
    """Dismiss an email_record from the Review Queue (persist to DB).

    Sets email_records.user_dismissed=1 and inserts a DISMISSED_EMAIL entry
    in user_corrections for the audit trail.

    Privacy-safe: only touches the user_dismissed flag and structured IDs.
    No raw email content is accessed or stored.
    """
    found = dismiss_email_record(conn, record_id)
    if not found:
        raise HTTPException(status_code=404, detail="Email record not found")
    conn.commit()
    return {"record_id": record_id, "dismissed": True}
