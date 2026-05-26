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
    insert_email_record,
)

logger = logging.getLogger(__name__)

AUTO_DETECT_THRESHOLD = float(os.getenv("AUTO_DETECT_THRESHOLD", "0.70"))
REVIEW_THRESHOLD = float(os.getenv("REVIEW_THRESHOLD", "0.40"))

_CATEGORY_MAP = {
    "Netflix": "STREAMING",
    "Spotify": "STREAMING",
    "Hulu": "STREAMING",
    "Disney+": "STREAMING",
    "Max": "STREAMING",
    "Amazon Prime Video": "STREAMING",
    "New York Times": "NEWS",
    "Substack": "NEWS",
    "DigitalOcean": "CLOUD",
    "Vercel": "CLOUD",
    "Microsoft 365": "CLOUD",
    "Apple": "CLOUD",
    "Dropbox": "CLOUD",
}


@dataclass
class DetectionResult:
    source_message_id: str
    disposition: str
    confidence_score: float
    subscription_id: str | None
    canonical_name: str | None


def process_email(conn: sqlite3.Connection, email: EmailMetadata) -> DetectionResult:
    """
    Run the 5-stage detection pipeline for one email.
    Writes to the database and returns a DetectionResult.
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

    # Use tier-provided canonical name for Tier 1 domains (more reliable)
    if canonical_name_from_tier:
        canonical_name = canonical_name_from_tier

    # Stage 4: Confidence scoring
    score = compute_score(tier, pattern, amount, billing_cycle)

    # Stage 5: Threshold decision → disposition
    disposition = score_to_disposition(score, AUTO_DETECT_THRESHOLD, REVIEW_THRESHOLD)

    logger.info("Processed %s: score=%.2f disposition=%s name=%s",
                email.source_message_id, score, disposition, canonical_name)

    subscription_id: str | None = None

    if disposition == "DETECTED":
        if pattern == PatternType.CANCELLATION:
            # Update existing subscription status to CANCELLED
            update_subscription_status(conn, canonical_name, "CANCELLED")
            # Find the subscription_id for the email record
            row = conn.execute(
                "SELECT subscription_id FROM subscriptions WHERE name = ?",
                (canonical_name,),
            ).fetchone()
            if row:
                subscription_id = row["subscription_id"]
            status = "CANCELLED"
        else:
            status = "ACTIVE"
            category = _CATEGORY_MAP.get(canonical_name, "SAAS")
            subscription_id = upsert_subscription(
                conn,
                name=canonical_name,
                amount=amount,
                currency=currency,
                billing_cycle=billing_cycle,
                category=category,
                status=status,
                source_provider=email.source_provider,
            )

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
            email_date=email.email_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            amount_extracted=amount,
            currency_extracted=currency if amount else None,
            confidence_score=score,
            disposition=disposition,
        )
        conn.commit()

    elif disposition == "FLAGGED":
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
            email_date=email.email_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            amount_extracted=amount,
            currency_extracted=currency if amount else None,
            confidence_score=score,
            disposition=disposition,
        )
        conn.commit()

    # IGNORED: nothing stored

    return DetectionResult(
        source_message_id=email.source_message_id,
        disposition=disposition,
        confidence_score=score,
        subscription_id=subscription_id,
        canonical_name=canonical_name,
    )
