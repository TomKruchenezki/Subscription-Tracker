"""
GET /api/payment-events — list payment events with optional filters.

Privacy: this endpoint returns only safe structured fields from payment_events.
No raw email content (subject, sender_address, snippet, body_text, body_html)
is present in payment_events and therefore cannot appear in responses.
"""
import logging
import os
import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, Query

from fastapi import Body, HTTPException
from backend.db.setup import (
    get_payment_events, link_payment_event, unlink_payment_event,
    # Phase 3.6
    mark_one_time, relabel_provider,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/payment-events", tags=["payment-events"])


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
    """Return 'GMAIL' when USE_MOCK=false, None otherwise (mock mode shows all)."""
    use_mock = os.getenv("USE_MOCK", "true").lower() not in ("false", "0", "no")
    return None if use_mock else "GMAIL"


@router.get("")
def list_payment_events(
    event_type: str | None = Query(None, description="Filter by event_type (e.g. renewal_charge)"),
    is_recurring_candidate: int | None = Query(None, description="1 = recurring candidates only"),
    is_one_time_candidate: int | None = Query(None, description="1 = one-time candidates only"),
    limit: int = Query(200, ge=1, le=1000, description="Maximum events to return"),
    conn: sqlite3.Connection = Depends(_get_db),
) -> list[dict[str, Any]]:
    """List payment events. Returns safe structured fields only — no raw email content.

    Payment events are individual financial/lifecycle signals detected from emails:
    subscription_charge, renewal_charge, refund, cancellation, trial_started, etc.

    Privacy note: this endpoint cannot expose raw email content because payment_events
    table stores only canonical merchant names and structured financial data.
    """
    source_provider = _source_provider_filter()
    rows = get_payment_events(
        conn,
        source_provider=source_provider,
        event_type=event_type,
        is_recurring_candidate=is_recurring_candidate,
        is_one_time_candidate=is_one_time_candidate,
        limit=limit,
    )
    return [dict(row) for row in rows]


@router.post("/{event_id}/link")
def link_event_to_subscription(
    event_id: str,
    subscription_id: str = Body(..., embed=True),
    conn: sqlite3.Connection = Depends(_get_db),
) -> dict[str, str]:
    """Link a payment_event to a subscription_id (manual correction).

    Useful when the scanner detected a charge but couldn't link it automatically.
    Privacy-safe: operates only on structured IDs, no raw content involved.
    """
    found = link_payment_event(conn, event_id, subscription_id)
    if not found:
        raise HTTPException(status_code=404, detail="Payment event not found")
    conn.commit()
    return {"event_id": event_id, "subscription_id": subscription_id}


@router.post("/{event_id}/unlink")
def unlink_event_from_subscription(
    event_id: str,
    conn: sqlite3.Connection = Depends(_get_db),
) -> dict[str, str | None]:
    """Remove subscription link from a payment_event (manual correction).

    Sets subscription_id = NULL — the event remains in the table as orphaned.
    """
    found = unlink_payment_event(conn, event_id)
    if not found:
        raise HTTPException(status_code=404, detail="Payment event not found")
    conn.commit()
    return {"event_id": event_id, "subscription_id": None}


@router.post("/{event_id}/mark-one-time")
def mark_event_one_time(
    event_id: str,
    conn: sqlite3.Connection = Depends(_get_db),
) -> dict[str, Any]:
    """Mark a payment_event as a one-time purchase (not a recurring subscription).

    Persists a MARKED_ONE_TIME correction in user_corrections so the decision
    survives reprocessing. Sets user_marked_one_time=1 on the payment_event.
    Privacy-safe: stores only structured IDs and correction_type.
    """
    row = conn.execute(
        """SELECT pe.event_id, pe.source_message_id, er.record_id, er.sender_address
           FROM payment_events pe
           LEFT JOIN email_records er ON er.source_message_id = pe.source_message_id
           WHERE pe.event_id = ?""",
        (event_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Payment event not found")

    mark_one_time(
        conn,
        email_record_id=row["record_id"],
        payment_event_id=event_id,
        sender_address=row["sender_address"],
    )
    conn.commit()
    return {"event_id": event_id, "user_marked_one_time": True}


@router.post("/{event_id}/relabel")
def relabel_payment_event_merchant(
    event_id: str,
    new_name: str = Body(..., embed=True),
    conn: sqlite3.Connection = Depends(_get_db),
) -> dict[str, Any]:
    """Relabel the merchant_name on a payment_event and persist a sender-level correction.

    Future scans / reprocessing will use the corrected name for emails from this sender.
    Privacy-safe: stores only the new canonical name and the sender_address as structured data.
    """
    row = conn.execute(
        """SELECT pe.event_id, pe.merchant_name, er.sender_address
           FROM payment_events pe
           LEFT JOIN email_records er ON er.source_message_id = pe.source_message_id
           WHERE pe.event_id = ?""",
        (event_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Payment event not found")

    conn.execute(
        "UPDATE payment_events SET merchant_name=? WHERE event_id=?",
        (new_name, event_id),
    )
    relabel_provider(
        conn,
        new_name=new_name,
        subscription_id=None,
        sender_address=row["sender_address"],
    )
    conn.commit()
    return {"event_id": event_id, "merchant_name": new_name}
