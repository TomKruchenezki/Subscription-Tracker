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
    # Phase 3.6: detection quality + account alias
    detection_state: str | None = None
    account_alias: str | None = None    # 8-char SHA-256 prefix of source_account_id
    # Phase 3.8: multi-account — list of all unique account aliases from linked email_records
    account_aliases: list[str] = []


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
    user_dismissed: int = 0  # Phase 3.5: 1 if user dismissed this from Review Queue
    # Phase 3.6: explanation fields (structured summaries, no raw email content)
    decision_reason: str | None = None
    evidence_summary: str | None = None
    missing_evidence: str | None = None
    suggested_action: str | None = None
    detection_state: str | None = None
    account_alias: str | None = None  # 8-char SHA-256 prefix of source_account_id
    # Phase 3.7: True when this record has one or more parsed/seen attachments.
    # Detailed attachment + PDF evidence is available at GET /{record_id}/attachments.
    has_attachment: bool = False
    # Phase 3.8: processor/merchant separation + cycle confidence
    sender_domain: str | None = None
    payment_processor: str | None = None      # canonical processor name, e.g. "Cardcom"
    merchant_name_candidate: str | None = None  # structured candidate — never raw body text
    is_processor_email: int = 0               # 1 if sender is a known payment processor
    gmail_account_id: str | None = None       # opaque account identifier
    cycle_source: str | None = None           # which evidence source produced the cycle
    cycle_confidence: str | None = None       # STRONG | WEAK | NONE


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
    unconfirmed_count: int = 0   # Phase 3.4: count of UNKNOWN-status subscriptions
    has_mock_data: bool = False   # True only when USE_MOCK=false and MOCK rows exist in DB
    monthly_costs_by_currency: dict[str, float] = {}   # per-currency monthly totals (Phase 3.3)
