from fastapi import APIRouter, HTTPException, Query
from backend.api.routers._db import get_conn
from backend.db.setup import get_subscriptions, get_subscription_by_id, get_email_records, get_records_for_subscription
from backend.models.subscription import SubscriptionResponse, EmailRecordResponse
from datetime import datetime

router = APIRouter()


def _parse_dt(s: str | None) -> datetime | None:
    if s is None:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _row_to_subscription(row) -> dict:
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
    }


def _row_to_record(row) -> dict:
    return {
        "record_id":            row["record_id"],
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
    }


@router.get("/api/subscriptions", response_model=list[SubscriptionResponse])
def list_subscriptions(status: str | None = Query(None)):
    with get_conn() as conn:
        rows = get_subscriptions(conn, status=status)
    return [SubscriptionResponse(**_row_to_subscription(r)) for r in rows]


@router.get("/api/subscriptions/{subscription_id}")
def get_subscription(subscription_id: str):
    with get_conn() as conn:
        sub = get_subscription_by_id(conn, subscription_id)
        if sub is None:
            raise HTTPException(status_code=404, detail="Subscription not found")
        records = get_records_for_subscription(conn, subscription_id)

    return {
        "subscription": SubscriptionResponse(**_row_to_subscription(sub)),
        "email_records": [EmailRecordResponse(**_row_to_record(r)) for r in records],
    }


@router.get("/api/email-records", response_model=list[EmailRecordResponse])
def list_email_records(disposition: str | None = Query(None)):
    with get_conn() as conn:
        rows = get_email_records(conn, disposition=disposition)
    return [EmailRecordResponse(**_row_to_record(r)) for r in rows]
