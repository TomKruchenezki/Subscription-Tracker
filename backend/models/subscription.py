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
    status: Literal["ACTIVE", "CANCELLED", "PAUSED"]
    first_seen: datetime
    last_seen: datetime
    source: Literal["MOCK", "GMAIL"]


class EmailRecordResponse(BaseModel):
    record_id: str
    subscription_id: str | None
    sender_address: str
    sender_name: str | None
    subject: str
    email_date: datetime
    amount_extracted: float | None
    currency_extracted: str | None
    confidence_score: float
    disposition: Literal["DETECTED", "FLAGGED", "IGNORED"]


class ScanResult(BaseModel):
    scanned: int
    detected: int
    flagged: int
    ignored: int


class Summary(BaseModel):
    total_monthly_cost: float
    currency: str
    active_count: int
    detected_count: int
    flagged_count: int
