import os
from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel
from backend.api.routers._db import get_conn
from backend.db.setup import (
    get_subscriptions, get_subscription_by_id, get_email_records,
    get_records_for_subscription,
    create_subscription_manual, update_subscription_fields, delete_subscription,
    # Phase 3.6
    relabel_provider, merge_subscriptions, account_alias,
)
from backend.models.subscription import SubscriptionResponse, EmailRecordResponse
from datetime import datetime

router = APIRouter()


def _source_provider_filter() -> str | None:
    """Return 'GMAIL' when running in Gmail mode, None in mock mode.

    In Gmail mode (USE_MOCK=false), endpoints should only return GMAIL rows so
    that leftover MOCK rows from earlier test scans don't inflate counts or
    pollute the Review Queue.
    """
    use_mock = os.getenv("USE_MOCK", "true").lower() not in {"false", "0", "no"}
    return None if use_mock else "GMAIL"


def _parse_dt(s: str | None) -> datetime | None:
    if s is None:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _row_to_subscription(row) -> dict:
    row_keys = row.keys() if hasattr(row, "keys") else []
    return {
        "subscription_id":  row["subscription_id"],
        "name":             row["name"],
        "service_url":      row["service_url"],
        "amount":           row["amount"],
        "currency":         row["currency"],
        "billing_cycle":    row["billing_cycle"],
        "next_renewal":     row["next_renewal"],
        "category":         row["category"],
        "status":           row["status"],
        "first_seen":       _parse_dt(row["first_seen"]),
        "last_seen":        _parse_dt(row["last_seen"]),
        "source_provider":  row["source_provider"],
        "first_charge_date": _parse_dt(row["first_charge_date"]),
        "last_charge_date":  _parse_dt(row["last_charge_date"]),
        "cancelled_at":      _parse_dt(row["cancelled_at"]),
        "trial_ends_at":     _parse_dt(row["trial_ends_at"]),
        # Phase 3.6: detection quality + account alias
        "detection_state":   row["detection_state"] if "detection_state" in row_keys else None,
        "account_alias":     account_alias(row["source_account_id"] if "source_account_id" in row_keys else None),
    }


def _attachment_record_ids(conn) -> set:
    """Return the set of email_record_ids that have at least one attachment.

    One query for the whole list (avoids N per-row lookups). Returns an empty set on
    a pre-3.7 DB where the table does not exist.
    """
    try:
        return {
            r["email_record_id"]
            for r in conn.execute(
                "SELECT DISTINCT email_record_id FROM email_attachments "
                "WHERE email_record_id IS NOT NULL"
            ).fetchall()
        }
    except Exception:
        return set()


def _row_to_record(row, has_attachment: bool = False) -> dict:
    return {
        "record_id":            row["record_id"],
        "has_attachment":       has_attachment,
        "subscription_id":      row["subscription_id"],
        "source_provider":      row["source_provider"],
        "source_account_id":    row["source_account_id"],
        "source_account_email": row["source_account_email"],
        "sender_address":       row["sender_address"],
        "sender_name":          row["sender_name"],
        "subject":              row["subject"],
        "email_date":           _parse_dt(row["email_date"]),
        "amount_extracted":     row["amount_extracted"],
        "currency_extracted":   row["currency_extracted"],
        "confidence_score":     row["confidence_score"],
        "disposition":          row["disposition"],
        "event_type":           row["event_type"],
        "billing_period_start": _parse_dt(row["billing_period_start"]),
        "billing_period_end":   _parse_dt(row["billing_period_end"]),
        "short_evidence":       row["short_evidence"],
        "user_dismissed":       row["user_dismissed"] if "user_dismissed" in row.keys() else 0,
        # Phase 3.6: explanation fields + detection_state + account_alias
        "decision_reason":      row["decision_reason"] if "decision_reason" in row.keys() else None,
        "evidence_summary":     row["evidence_summary"] if "evidence_summary" in row.keys() else None,
        "missing_evidence":     row["missing_evidence"] if "missing_evidence" in row.keys() else None,
        "suggested_action":     row["suggested_action"] if "suggested_action" in row.keys() else None,
        "detection_state":      row["detection_state"] if "detection_state" in row.keys() else None,
        "account_alias":        account_alias(row["source_account_id"] if "source_account_id" in row.keys() else None),
    }


@router.get("/api/subscriptions", response_model=list[SubscriptionResponse])
def list_subscriptions(status: str | None = Query(None)):
    with get_conn() as conn:
        rows = get_subscriptions(conn, status=status,
                                 source_provider=_source_provider_filter())
    return [SubscriptionResponse(**_row_to_subscription(r)) for r in rows]


@router.get("/api/subscriptions/{subscription_id}")
def get_subscription(subscription_id: str):
    with get_conn() as conn:
        sub = get_subscription_by_id(conn, subscription_id)
        if sub is None:
            raise HTTPException(status_code=404, detail="Subscription not found")
        records = get_records_for_subscription(conn, subscription_id)
        att_ids = _attachment_record_ids(conn)

    return {
        "subscription": SubscriptionResponse(**_row_to_subscription(sub)),
        "email_records": [
            EmailRecordResponse(**_row_to_record(r, r["record_id"] in att_ids)) for r in records
        ],
    }


@router.get("/api/email-records", response_model=list[EmailRecordResponse])
def list_email_records(
    disposition: str | None = Query(None),
    include_dismissed: bool = Query(False, description="Include user-dismissed records (default: excluded)"),
):
    with get_conn() as conn:
        rows = get_email_records(
            conn,
            disposition=disposition,
            source_provider=_source_provider_filter(),
            include_dismissed=include_dismissed,
        )
        att_ids = _attachment_record_ids(conn)
    return [EmailRecordResponse(**_row_to_record(r, r["record_id"] in att_ids)) for r in rows]


# ── Manual CRUD ───────────────────────────────────────────────────────────────

class CreateSubscriptionRequest(BaseModel):
    name: str
    amount: float | None = None
    currency: str = "USD"
    billing_cycle: str = "UNKNOWN"
    category: str = "OTHER"
    status: str = "ACTIVE"
    service_url: str | None = None


class UpdateSubscriptionRequest(BaseModel):
    name: str | None = None
    amount: float | None = None
    currency: str | None = None
    billing_cycle: str | None = None
    status: str | None = None
    category: str | None = None
    service_url: str | None = None


@router.post("/api/subscriptions", status_code=201)
def create_subscription(body: CreateSubscriptionRequest):
    """Manually create a subscription. Used when the scanner missed a real subscription."""
    import os as _os
    source_provider = "GMAIL" if _os.getenv("USE_MOCK", "true").lower() in {"false", "0", "no"} else "MOCK"
    with get_conn() as conn:
        sub_id = create_subscription_manual(
            conn,
            name=body.name,
            amount=body.amount,
            currency=body.currency,
            billing_cycle=body.billing_cycle,
            category=body.category,
            status=body.status,
            service_url=body.service_url,
            source_provider=source_provider,
        )
        conn.commit()
        row = get_subscription_by_id(conn, sub_id)
    return SubscriptionResponse(**_row_to_subscription(row))


@router.post("/api/subscriptions/{subscription_id}/update")
def update_subscription(subscription_id: str, body: UpdateSubscriptionRequest):
    """Update editable fields on a subscription (amount, currency, cycle, status, name)."""
    with get_conn() as conn:
        found = update_subscription_fields(
            conn,
            subscription_id,
            name=body.name,
            amount=body.amount,
            currency=body.currency,
            billing_cycle=body.billing_cycle,
            status=body.status,
            category=body.category,
            service_url=body.service_url,
        )
        if not found:
            raise HTTPException(status_code=404, detail="Subscription not found")
        conn.commit()
        row = get_subscription_by_id(conn, subscription_id)
    return SubscriptionResponse(**_row_to_subscription(row))


@router.delete("/api/subscriptions/{subscription_id}", status_code=204)
def delete_subscription_endpoint(subscription_id: str):
    """Delete a subscription (manual false-positive removal). Payment events are unlinked."""
    with get_conn() as conn:
        found = delete_subscription(conn, subscription_id)
        if not found:
            raise HTTPException(status_code=404, detail="Subscription not found")
        conn.commit()


@router.post("/api/subscriptions/{subscription_id}/relabel")
def relabel_subscription_endpoint(
    subscription_id: str,
    new_name: str = Body(..., embed=True),
):
    """Rename a subscription's provider/product canonical name.

    Persists a sender-level RELABELED correction so future scans and
    reprocessing use the corrected name for emails from the same sender.
    Privacy-safe: stores only the new canonical name and subscription ID.
    """
    with get_conn() as conn:
        row = get_subscription_by_id(conn, subscription_id)
        if not row:
            raise HTTPException(status_code=404, detail="Subscription not found")
        # Find the sender_address from a linked email_record for sender-level correction
        linked = conn.execute(
            "SELECT sender_address FROM email_records WHERE subscription_id=? LIMIT 1",
            (subscription_id,),
        ).fetchone()
        sender_addr = linked["sender_address"] if linked else None
        relabel_provider(
            conn,
            new_name=new_name,
            subscription_id=subscription_id,
            sender_address=sender_addr,
        )
        conn.commit()
        updated = get_subscription_by_id(conn, subscription_id)
    return SubscriptionResponse(**_row_to_subscription(updated))


@router.post("/api/subscriptions/{subscription_id}/merge")
def merge_subscription_endpoint(
    subscription_id: str,
    target_subscription_id: str = Body(..., embed=True),
):
    """Merge this subscription into target_subscription_id.

    Moves all email_records and payment_events to the target, then deletes
    the source subscription. Useful for merging duplicate provider entries
    (e.g., 'Spotify' and 'Spotify Premium' into one record).
    Backend-only in Phase 3.6 — no merge UI yet.
    Privacy-safe: operates only on structured IDs.
    """
    with get_conn() as conn:
        found = merge_subscriptions(conn, subscription_id, target_subscription_id)
        if not found:
            raise HTTPException(status_code=404, detail="Source subscription not found")
        target = get_subscription_by_id(conn, target_subscription_id)
        if not target:
            raise HTTPException(status_code=404, detail="Target subscription not found")
        conn.commit()
    return {"merged_into": target_subscription_id}
