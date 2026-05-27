"""
5-stage detection pipeline: takes an EmailMetadata, runs all stages,
writes results to the database, and returns a DetectionResult.
"""
import logging
import os
import sqlite3
from dataclasses import dataclass

from backend.models.email_metadata import EmailMetadata
from backend.detector.sender_list import get_tier
from backend.detector.pattern_library import match_pattern, PatternType
from backend.detector.confidence_scorer import compute_score, score_to_disposition
from backend.parser import parse_email_metadata
from backend.db.setup import (
    upsert_subscription,
    update_subscription_status,
    update_subscription_lifecycle,
    insert_email_record,
)

logger = logging.getLogger(__name__)

AUTO_DETECT_THRESHOLD = float(os.getenv("AUTO_DETECT_THRESHOLD", "0.70"))
REVIEW_THRESHOLD = float(os.getenv("REVIEW_THRESHOLD", "0.40"))

_CATEGORY_MAP = {
    # Streaming
    "Netflix": "STREAMING",
    "Spotify": "STREAMING",
    "Hulu": "STREAMING",
    "Disney+": "STREAMING",
    "Max": "STREAMING",
    "Amazon Prime Video": "STREAMING",
    "YouTube Premium": "STREAMING",
    # News / Publishing
    "New York Times": "NEWS",
    "Substack": "NEWS",
    # Cloud / Storage / Security
    "DigitalOcean": "CLOUD",
    "Vercel": "CLOUD",
    "Microsoft 365": "CLOUD",
    "Apple": "CLOUD",
    "Google One": "CLOUD",
    "Google": "CLOUD",
    "Dropbox": "CLOUD",
    "NordVPN": "CLOUD",
    "Bitwarden": "CLOUD",
    # SAAS / Productivity
    "OpenAI": "SAAS",
    "ChatGPT": "SAAS",
    "Claude": "SAAS",
    "GitHub": "SAAS",
    "GitHub Copilot": "SAAS",
    "Notion": "SAAS",
    "Figma": "SAAS",
    "Zoom": "SAAS",
    "Slack": "SAAS",
    "Atlassian": "SAAS",
    "1Password": "SAAS",
    "Adobe Creative Cloud": "SAAS",
    "Monday.com": "SAAS",
    "Airtable": "SAAS",
    "Canva": "SAAS",
    "Wix": "SAAS",
    "Grammarly": "SAAS",
    "LinkedIn Premium": "SAAS",
    "Udemy": "SAAS",
    "Coursera": "SAAS",
    "PayPal": "OTHER",
}

# Patterns that constitute strong billing evidence — these create/keep ACTIVE subscriptions.
# All other patterns reaching DETECTED do not auto-create ACTIVE; they produce
# event_type="subscription_candidate" or the pattern-specific event type, without
# changing subscription status.
_STRONG_BILLING_PATTERNS = frozenset({PatternType.RECEIPT, PatternType.RENEWAL})

_PATTERN_TO_EVENT_TYPE: dict[PatternType, str | None] = {
    PatternType.RECEIPT:        None,           # resolved at runtime
    PatternType.RENEWAL:        None,           # resolved at runtime
    PatternType.TRIAL_END:      "trial_ending",
    PatternType.TRIAL_STARTED:  "trial_started",
    PatternType.CANCELLATION:   "cancellation",
    PatternType.FAILED_PAYMENT: "failed_payment",
    PatternType.REFUND:         "refund",
    PatternType.PRICE_CHANGE:   "price_change",
    PatternType.PROMOTIONAL:    None,
    PatternType.NOTIFICATION:   None,
    PatternType.NONE:           None,
}


@dataclass
class DetectionResult:
    source_message_id: str
    disposition: str
    confidence_score: float
    subscription_id: str | None
    canonical_name: str | None
    event_type: str | None


def _make_short_evidence(
    event_type: str | None,
    name: str,
    amount: float | None,
    currency: str,
    billing_cycle: str,
) -> str | None:
    if not event_type:
        return None
    amt = f"{currency} {amount:.2f}" if amount else ""
    cyc = f"/{billing_cycle.lower()}" if billing_cycle not in ("UNKNOWN", None) and amount else ""
    templates: dict[str, str | None] = {
        "subscription_started": f"New subscription: {amt}{cyc} from {name}",
        "renewal_charge":       f"Renewal: {amt}{cyc} from {name}",
        "trial_started":        f"Trial started: {name}",
        "trial_ending":         f"Trial ending: {name}" + (f" — then {amt}{cyc}" if amt else ""),
        "cancellation":         f"Cancelled: {name}",
        "refund":               f"Refund: {amt} from {name}" if amt else f"Refund from {name}",
        "failed_payment":       f"Payment failed: {name}" + (f" ({amt})" if amt else ""),
        "price_change":         f"Price change: {name}" + (f" → {amt}{cyc}" if amt else ""),
        "unknown_payment":      f"Payment: {amt} from {name}" if amt else None,
    }
    return templates.get(event_type)


def process_email(
    conn: sqlite3.Connection,
    email: EmailMetadata,
    review_threshold: float | None = None,
) -> DetectionResult:
    """
    Run the 5-stage detection pipeline for one email.
    Writes to the database and returns a DetectionResult.

    Args:
        conn: Active DB connection.
        email: Normalised email metadata from any EmailSource.
        review_threshold: Override the REVIEW_THRESHOLD env var for this call.
                          Scan modes pass mode-specific thresholds (quick=0.50,
                          deep=0.40, forensic=0.30). None → use env var default.
    """
    # Stage 1: Sender domain lookup
    domain = email.sender_address.split("@", 1)[-1].lower() if "@" in email.sender_address else email.sender_address
    tier, canonical_name_from_tier = get_tier(domain)

    # Stage 2: Subject pattern match
    pattern = match_pattern(email.subject)

    # Stage 3: Parser outputs
    parsed = parse_email_metadata(email)
    amount = parsed["amount"]
    currency = parsed["currency"] or "USD"
    billing_cycle = parsed["billing_cycle"]
    canonical_name = parsed["canonical_name"] or canonical_name_from_tier or "Unknown"

    if canonical_name_from_tier:
        canonical_name = canonical_name_from_tier

    # Stage 4: Confidence scoring
    score = compute_score(tier, pattern, amount, billing_cycle)

    # Stage 5: Threshold decision → disposition
    effective_review_threshold = review_threshold if review_threshold is not None else REVIEW_THRESHOLD
    disposition = score_to_disposition(score, AUTO_DETECT_THRESHOLD, effective_review_threshold)

    logger.info("Processed %s: score=%.2f disposition=%s name=%s",
                email.source_message_id, score, disposition, canonical_name)

    email_date_str = email.email_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    event_type: str | None = None
    subscription_id: str | None = None

    if disposition == "DETECTED":

        if pattern == PatternType.CANCELLATION:
            update_subscription_status(conn, canonical_name, "CANCELLED")
            row = conn.execute(
                "SELECT subscription_id FROM subscriptions WHERE name = ?",
                (canonical_name,),
            ).fetchone()
            if row:
                subscription_id = row["subscription_id"]
                update_subscription_lifecycle(conn, subscription_id, cancelled_at=email_date_str)
            event_type = "cancellation"

        elif pattern == PatternType.TRIAL_END:
            existing = conn.execute(
                "SELECT subscription_id FROM subscriptions WHERE name = ?",
                (canonical_name,),
            ).fetchone()
            if existing:
                subscription_id = existing["subscription_id"]
            else:
                subscription_id, _ = upsert_subscription(
                    conn, name=canonical_name, amount=amount, currency=currency,
                    billing_cycle=billing_cycle,
                    category=_CATEGORY_MAP.get(canonical_name, "SAAS"),
                    status="TRIAL", source_provider=email.source_provider,
                )
            event_type = "trial_ending"
            if subscription_id:
                update_subscription_lifecycle(conn, subscription_id, trial_ends_at=email_date_str)

        elif pattern == PatternType.TRIAL_STARTED:
            subscription_id, _ = upsert_subscription(
                conn, name=canonical_name, amount=amount, currency=currency,
                billing_cycle=billing_cycle,
                category=_CATEGORY_MAP.get(canonical_name, "SAAS"),
                status="TRIAL", source_provider=email.source_provider,
            )
            event_type = "trial_started"

        else:
            # RECEIPT, RENEWAL → strong evidence: create/keep ACTIVE subscription.
            # All other patterns (REFUND, FAILED_PAYMENT, PRICE_CHANGE, NONE) → do NOT
            # auto-create ACTIVE; produce event_type only, link to existing sub if any.
            if pattern in _STRONG_BILLING_PATTERNS:
                # ACTIVE requires an extracted amount. Without one, create as UNKNOWN —
                # upgrades to ACTIVE automatically when a later receipt provides an amount.
                effective_status = "ACTIVE" if amount is not None else "UNKNOWN"
                subscription_id, was_created = upsert_subscription(
                    conn, name=canonical_name, amount=amount, currency=currency,
                    billing_cycle=billing_cycle,
                    category=_CATEGORY_MAP.get(canonical_name, "SAAS"),
                    status=effective_status, source_provider=email.source_provider,
                )
                event_type = "subscription_started" if was_created else "renewal_charge"
                update_subscription_lifecycle(
                    conn, subscription_id,
                    first_charge_date=email_date_str,
                    last_charge_date=email_date_str,
                )
            else:
                # Weak/ambiguous evidence — look up existing subscription if any,
                # but do NOT create a new ACTIVE subscription from this signal alone.
                existing = conn.execute(
                    "SELECT subscription_id FROM subscriptions WHERE name = ? "
                    "AND source_provider = ?",
                    (canonical_name, email.source_provider),
                ).fetchone()
                if existing:
                    subscription_id = existing["subscription_id"]
                    # Don't change status of the existing subscription

                if pattern == PatternType.NONE:
                    event_type = "subscription_candidate"
                else:
                    event_type = _PATTERN_TO_EVENT_TYPE.get(pattern, "unknown_payment")

        short_evidence = _make_short_evidence(event_type, canonical_name, amount, currency, billing_cycle)
        insert_email_record(
            conn,
            source_message_id=email.source_message_id,
            source_provider=email.source_provider,
            source_account_id=email.source_account_id,
            source_account_email=email.source_account_email,
            subscription_id=subscription_id,
            sender_address=email.sender_address,
            sender_name=email.sender_name,
            subject=email.subject,
            email_date=email_date_str,
            amount_extracted=amount,
            currency_extracted=currency if amount else None,
            confidence_score=score,
            disposition=disposition,
            event_type=event_type,
            billing_period_start=None,
            billing_period_end=None,
            short_evidence=short_evidence,
        )
        conn.commit()

    elif disposition == "FLAGGED":
        if pattern in (PatternType.RECEIPT, PatternType.RENEWAL):
            event_type = "unknown_payment"
        else:
            event_type = _PATTERN_TO_EVENT_TYPE.get(pattern)
        short_evidence = _make_short_evidence(event_type, canonical_name, amount, currency, billing_cycle)
        insert_email_record(
            conn,
            source_message_id=email.source_message_id,
            source_provider=email.source_provider,
            source_account_id=email.source_account_id,
            source_account_email=email.source_account_email,
            subscription_id=None,
            sender_address=email.sender_address,
            sender_name=email.sender_name,
            subject=email.subject,
            email_date=email_date_str,
            amount_extracted=amount,
            currency_extracted=currency if amount else None,
            confidence_score=score,
            disposition=disposition,
            event_type=event_type,
            billing_period_start=None,
            billing_period_end=None,
            short_evidence=short_evidence,
        )
        conn.commit()

    # IGNORED: nothing stored

    return DetectionResult(
        source_message_id=email.source_message_id,
        disposition=disposition,
        confidence_score=score,
        subscription_id=subscription_id,
        canonical_name=canonical_name,
        event_type=event_type,
    )
