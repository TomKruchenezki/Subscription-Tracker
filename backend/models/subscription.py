from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel


class SubscriptionResponse(BaseModel):
    subscription_id: str
    name: str
    service_url: str | None
    amount: float | None
    currency: str
    billing_cycle: Literal["MONTHLY", "ANNUAL", "WEEKLY", "UNKNOWN"]
    next_renewal: date | None
    category: Literal["STREAMING", "SAAS", "NEWS", "CLOUD", "OTHER"]
    status: Literal["ACTIVE", "CANCELLED", "PAUSED", "TRIAL", "UNKNOWN"]
    first_seen: datetime
    last_seen: datetime
    source_provider: str
    first_charge_date: datetime | None
    last_charge_date: datetime | None
    cancelled_at: datetime | None
    trial_ends_at: datetime | None


class EmailRecordResponse(BaseModel):
    record_id: str
    subscription_id: str | None
    source_provider: str
    source_account_id: str
    source_account_email: str
    sender_address: str
    sender_name: str | None
    subject: str
    email_date: datetime
    amount_extracted: float | None
    currency_extracted: str | None
    confidence_score: float
    disposition: Literal["DETECTED", "FLAGGED", "IGNORED"]
    event_type: str | None
    billing_period_start: datetime | None
    billing_period_end: datetime | None
    short_evidence: str | None


class ScanResult(BaseModel):
    scanned: int
    detected: int
    flagged: int
    ignored: int
    content_access_level: str = "metadata_plus_snippet"


class Summary(BaseModel):
    total_monthly_cost: float
    currency: str
    active_count: int
    detected_count: int
    flagged_count: int
