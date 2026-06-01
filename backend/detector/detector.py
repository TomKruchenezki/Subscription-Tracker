"""
5-stage detection pipeline: takes an EmailMetadata, runs all stages,
writes results to the database, and returns a DetectionResult.
"""
import logging
import os
import sqlite3
import uuid as _uuid
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
    insert_payment_event,
    # Phase 3.6: correction-awareness
    get_relabeled_name,
    is_sender_blocked,
    # Phase 3.7: attachment / PDF-derived evidence
    insert_attachment,
    insert_attachment_fields,
    is_event_marked_one_time,
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
    "Google Play": "CLOUD",
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
    PatternType.RECEIPT:        None,           # resolved at runtime (subscription_started or renewal_charge)
    PatternType.RENEWAL:        None,           # resolved at runtime (subscription_started or renewal_charge)
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

# Maps email_record event_type → payment_events event_type.
# Only real financial/lifecycle events produce payment_events.
# "subscription_candidate" and None produce no payment_event.
_EMAIL_EVENT_TO_PAYMENT_EVENT: dict[str, str] = {
    "subscription_started": "subscription_charge",
    "renewal_charge":       "renewal_charge",
    "refund":               "refund",
    "cancellation":         "cancellation",
    "trial_started":        "trial_started",
    "trial_ending":         "trial_ended",
    "failed_payment":       "failed_payment",
    "price_change":         "price_change",
}


def _map_payment_event_type(email_event_type: str | None) -> str | None:
    """Convert email_record event_type to payment_events event_type.

    Returns None when no payment_event should be created:
    - "subscription_candidate" → None (ambiguous, not a confirmed financial event)
    - "unknown_payment" → None (FLAGGED without confirmed amount; no value as payment_event)
    - None → None

    This replaces the old pattern-based _map_to_payment_event_type() which incorrectly
    mapped PatternType.NONE → "unknown_payment", causing every email_record to get a
    payment_event. Now we derive from email_record event_type which already has full context
    (was_created, disposition, tier).
    """
    return _EMAIL_EVENT_TO_PAYMENT_EVENT.get(email_event_type or "", None)


@dataclass
class DetectionResult:
    source_message_id: str
    disposition: str
    confidence_score: float
    subscription_id: str | None
    canonical_name: str | None
    event_type: str | None


# ── Phase 3.6: Explanation field helpers ─────────────────────────────────────
# All helpers build structured summaries from detection variables only.
# No raw email subject, body text, HTML, snippet, or sender address is stored.

_PATTERN_LABELS: dict = {
    PatternType.RECEIPT:        "billing receipt",
    PatternType.RENEWAL:        "renewal/subscription keyword",
    PatternType.CANCELLATION:   "cancellation keyword",
    PatternType.REFUND:         "refund keyword",
    PatternType.TRIAL_STARTED:  "trial started",
    PatternType.TRIAL_END:      "trial ending",
    PatternType.FAILED_PAYMENT: "payment failure",
    PatternType.PROMOTIONAL:    "promotional content",
    PatternType.NOTIFICATION:   "account notification",
    PatternType.PRICE_CHANGE:   "price change",
    PatternType.NONE:           "no billing keyword",
}

_CURRENCY_SYMS: dict = {
    "USD": "$", "ILS": "₪", "EUR": "€", "GBP": "£",
    "JPY": "¥", "CAD": "CA$", "AUD": "A$",
}


def _build_decision_reason(
    tier: int,
    pattern: PatternType,
    amount: float | None,
    currency: str | None,
    billing_cycle: str,
    score: float,
    disposition: str,
    canonical_name: str,
) -> str:
    """Structured, privacy-safe summary of WHY this email got this disposition.

    Uses only structured detection variables — never raw subject, body, or sender address.
    """
    tier_str = {1: "known provider", 2: "billing processor", -1: "excluded domain"}.get(
        tier, "unknown sender"
    )
    pat_str = _PATTERN_LABELS.get(pattern, "unknown pattern")
    if amount is not None:
        sym = _CURRENCY_SYMS.get(currency or "USD", (currency or "") + " ")
        amt_str = f"{sym}{amount:.2f}"
    else:
        amt_str = "no amount"
    cyc_str = billing_cycle.lower() if billing_cycle not in ("UNKNOWN", None) else "unknown cycle"
    return (
        f"{tier_str} ({canonical_name}) | {pat_str} | {amt_str} | "
        f"{cyc_str} | score={score:.2f} → {disposition}"
    )


def _build_evidence_summary(
    tier: int,
    pattern: PatternType,
    amount: float | None,
    currency: str | None,
    billing_cycle: str,
    canonical_name: str,
) -> str:
    """List of positive signals that were found. Never includes raw email content."""
    parts: list[str] = []
    if tier == 1:
        parts.append(f"known subscription service: {canonical_name}")
    elif tier == 2:
        parts.append("billing processor domain")
    if pattern in _STRONG_BILLING_PATTERNS:
        parts.append("billing receipt or renewal keyword in subject")
    elif pattern not in (PatternType.NONE, PatternType.NOTIFICATION, PatternType.PROMOTIONAL):
        parts.append(_PATTERN_LABELS.get(pattern, pattern.name.lower()))
    if amount is not None:
        sym = _CURRENCY_SYMS.get(currency or "USD", (currency or "") + " ")
        parts.append(f"amount extracted: {sym}{amount:.2f}")
    if billing_cycle not in ("UNKNOWN", None):
        parts.append(f"{billing_cycle.lower()} billing cycle detected")
    return "; ".join(parts) if parts else "no positive evidence found"


def _build_missing_evidence(
    tier: int,
    pattern: PatternType,
    amount: float | None,
    billing_cycle: str,
    disposition: str,
) -> str | None:
    """What additional evidence would strengthen confidence. Never raw content."""
    parts: list[str] = []
    if tier == 0:
        parts.append("sender not in known provider list")
    if amount is None:
        parts.append("amount not found in subject (may be in attachment)")
    if billing_cycle in ("UNKNOWN", None):
        parts.append("billing cycle not detected")
    if pattern == PatternType.NONE:
        parts.append("no billing keyword in subject")
    if disposition == "FLAGGED" and tier == 0:
        parts.append("unverified sender domain")
    return "; ".join(parts) if parts else None


def _build_suggested_action(
    tier: int,
    pattern: PatternType,
    amount: float | None,
    billing_cycle: str,
    disposition: str,
    needs_attachment: bool,
    sender_blocked: bool = False,
) -> str | None:
    """Privacy-safe recommended user action for this email."""
    if sender_blocked:
        return "Sender was previously rejected — confirm if this is a new subscription"
    if disposition == "DETECTED" and amount is not None and billing_cycle not in ("UNKNOWN", None):
        return None  # Fully confirmed — no action needed
    if needs_attachment:
        return "Check attachment for invoice amount, then confirm subscription"
    if disposition == "DETECTED" and amount is None:
        return "Add amount manually to activate cost tracking"
    if pattern == PatternType.REFUND:
        return "Mark as refund — not a subscription"
    if pattern == PatternType.CANCELLATION:
        return "Subscription cancelled — verify in Subscriptions tab"
    if disposition == "FLAGGED" and amount is not None:
        return "Confirm as subscription or mark as one-time payment"
    if disposition == "FLAGGED":
        return "Review: confirm if subscription, or dismiss if irrelevant"
    return None


def _compute_email_detection_state(
    tier: int,
    pattern: PatternType,
    amount: float | None,
    billing_cycle: str,
    disposition: str,
    needs_attachment: bool,
    event_type: str | None,
) -> str:
    """Map detection signals to a granular per-email detection_state."""
    if event_type == "refund":
        return "REFUND"
    if event_type == "cancellation":
        return "CANCELLATION"
    if event_type in ("trial_started", "trial_ending"):
        return "TRIAL"
    if needs_attachment:
        return "NEEDS_ATTACHMENT_REVIEW"
    if disposition == "IGNORED":
        return "IGNORED"
    if disposition == "DETECTED":
        if tier == 1 and amount is not None and billing_cycle not in ("UNKNOWN", None):
            return "CONFIRMED_SUBSCRIPTION"
        if tier == 1 and pattern in _STRONG_BILLING_PATTERNS:
            return "LIKELY_SUBSCRIPTION"
        if amount is not None:
            return "POSSIBLE_SUBSCRIPTION"
        return "LIKELY_SUBSCRIPTION"
    # FLAGGED
    if pattern in (PatternType.RECEIPT, PatternType.RENEWAL) and amount is not None:
        return "POSSIBLE_SUBSCRIPTION"
    return "NEEDS_USER_REVIEW"


def _email_to_sub_detection_state(email_ds: str) -> str | None:
    """Map per-email detection_state to the subscription-level detection_state."""
    return {
        "CONFIRMED_SUBSCRIPTION":  "CONFIRMED_ACTIVE",
        "LIKELY_SUBSCRIPTION":     "LIKELY_SUBSCRIPTION",
        "POSSIBLE_SUBSCRIPTION":   "POSSIBLE_SUBSCRIPTION",
        "NEEDS_ATTACHMENT_REVIEW": "NEEDS_ATTACHMENT_REVIEW",
        "NEEDS_USER_REVIEW":       "NEEDS_USER_REVIEW",
    }.get(email_ds)


# ── Phase 3.7: PDF / attachment evidence helpers ──────────────────────────────

def _best_pdf_evidence(attachments: list):
    """Pick the most useful parsed PDF evidence from an email's attachments, or None.

    Preference order: evidence with an amount, then evidence with recurring signals.
    Each attachment is a dict carrying an optional ephemeral "evidence" (PdfEvidence).
    """
    best = None
    for att in attachments or []:
        ev = att.get("evidence") if isinstance(att, dict) else None
        if ev is None:
            continue
        if best is None:
            best = ev
            continue
        if getattr(ev, "amount", None) is not None and getattr(best, "amount", None) is None:
            best = ev
        elif (
            getattr(ev, "amount", None) is not None
            and getattr(best, "amount", None) is not None
            and ev.has_recurring_evidence()
            and not best.has_recurring_evidence()
        ):
            best = ev
    return best


def _join_tokens(tokens) -> str | None:
    """Join coded reason tokens with ';' — never raw text."""
    s = ";".join(t for t in (tokens or []) if t)
    return s or None


def _join_note(existing: str | None, note: str) -> str:
    return (existing + "; " + note) if existing else note


def _has_unparsed_pdf(attachments: list) -> bool:
    for a in attachments or []:
        if (
            isinstance(a, dict)
            and (a.get("detected_attachment_type") or "").startswith("PDF")
            and a.get("processing_status") in ("PARSE_FAILED", "SKIPPED")
        ):
            return True
    return False


def _persist_attachments(conn, record_id: str, email, provider: str) -> None:
    """Persist email_attachments + attachment_extracted_fields for a freshly-inserted record.

    Stores structured metadata + coded reason tokens only — never raw PDF text or bytes.
    """
    for att in email.attachments or []:
        if not isinstance(att, dict):
            continue
        ev = att.get("evidence")
        row_id = insert_attachment(
            conn,
            email_record_id=record_id,
            source_message_id=email.source_message_id,
            source_account_id=email.source_account_id,
            gmail_attachment_id=att.get("gmail_attachment_id"),
            filename=att.get("filename"),
            mime_type=att.get("mime_type"),
            size_bytes=att.get("size_bytes"),
            detected_attachment_type=att.get("detected_attachment_type"),
            processing_status=att.get("processing_status", "PENDING"),
            parser_version=getattr(ev, "parser_version", None),
        )
        if ev is not None:
            insert_attachment_fields(
                conn,
                attachment_row_id=row_id,
                email_record_id=record_id,
                source_message_id=email.source_message_id,
                provider=getattr(ev, "provider", None) or provider,
                product_name=getattr(ev, "product_name", None),
                amount=getattr(ev, "amount", None),
                currency=getattr(ev, "currency", None),
                invoice_date=getattr(ev, "invoice_date", None),
                payment_date=getattr(ev, "payment_date", None),
                billing_period_start=getattr(ev, "billing_period_start", None),
                billing_period_end=getattr(ev, "billing_period_end", None),
                inferred_cycle=getattr(ev, "inferred_cycle", None),
                tax_amount=getattr(ev, "tax_amount", None),
                invoice_number=getattr(ev, "invoice_number", None),
                subscription_indicators=_join_tokens(getattr(ev, "subscription_indicators", None)),
                evidence_reasons=_join_tokens(getattr(ev, "evidence_reasons", None)),
                missing_evidence=_join_tokens(getattr(ev, "missing_evidence", None)),
                penalty_reasons=_join_tokens(getattr(ev, "penalty_reasons", None)),
                confidence_score=getattr(ev, "confidence_score", 0.0),
                extraction_status=getattr(ev, "extraction_status", None),
                parser_version=getattr(ev, "parser_version", None),
            )


def _make_short_evidence(
    event_type: str | None,
    name: str,
    amount: float | None,
    currency: str | None,
    billing_cycle: str,
) -> str | None:
    if not event_type:
        return None
    cur = currency or "USD"
    amt = f"{cur} {amount:.2f}" if amount else ""
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
    persist_attachments: bool = True,
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
        persist_attachments: When True (live scan), persist email_attachments +
                          attachment_extracted_fields rows for any parsed PDFs on a
                          freshly-inserted record. Reprocessing passes False — it
                          reconstructs PDF evidence from stored rows for scoring only
                          and must not duplicate them.
    """
    # Stage 1: Sender domain lookup
    domain = email.sender_address.split("@", 1)[-1].lower() if "@" in email.sender_address else email.sender_address
    tier, canonical_name_from_tier = get_tier(domain)

    # Stage 2: Subject pattern match
    pattern = match_pattern(email.subject)

    # Stage 3: Parser outputs
    parsed = parse_email_metadata(email)
    amount = parsed["amount"]
    currency = parsed["currency"]    # None when not extracted — preserves native currency (e.g. ILS)
    billing_cycle = parsed["billing_cycle"]
    # Apple product disambiguation: resolve_sender uses subject to refine "Apple" →
    # "Apple Music", "iCloud+", "App Store", etc. The subject is passed here only
    # for this lookup — it is not stored in payment_events or subscriptions.
    # Always call with subject so product-specific names are used (parse_email calls
    # resolve_sender without subject, so we re-resolve here to pick up subject refinement).
    from backend.parser.sender_resolver import resolve_sender as _resolve
    canonical_name = (
        _resolve(email.sender_address, email.subject)
        or canonical_name_from_tier
        or "Unknown"
    )

    # Phase 3.6: Apply sender-level user corrections before scoring/subscription creation.
    # 1. Relabel: if user corrected this sender's canonical name, use their version.
    relabeled = get_relabeled_name(conn, email.sender_address)
    if relabeled:
        canonical_name = relabeled

    # 2. Blocked sender: if user previously rejected a subscription from this sender,
    #    skip subscription creation later (email_record is still stored with explanation).
    sender_blocked = is_sender_blocked(conn, email.sender_address)

    # 3. One-time: if the user marked THIS message's event as a one-time payment, never
    #    (re)create a subscription from it. Re-applied on reprocess so the decision sticks.
    marked_one_time = is_event_marked_one_time(conn, email.source_message_id)

    # Phase 3.7: PDF/attachment evidence. When the subject/snippet/body yielded no amount,
    # a parsed PDF invoice/receipt can supply it. Guardrail (user requirement): a PDF
    # receipt alone does NOT confer a billing cycle, so it cannot reach CONFIRMED unless
    # the PDF carries genuine recurring evidence (a billing period or recurring wording,
    # which is what produces inferred_cycle). A refund PDF never fills a charge amount.
    pdf_ev = _best_pdf_evidence(email.attachments)
    pdf_amount_used = False
    if pdf_ev is not None:
        if amount is None and getattr(pdf_ev, "amount", None) is not None and not pdf_ev.is_refund():
            amount = pdf_ev.amount
            currency = pdf_ev.currency
            pdf_amount_used = True
        if billing_cycle in ("UNKNOWN", None) and getattr(pdf_ev, "inferred_cycle", None):
            billing_cycle = pdf_ev.inferred_cycle

    # Stage 4: Confidence scoring
    score = compute_score(tier, pattern, amount, billing_cycle)

    # Stage 5: Threshold decision → disposition
    # If sender is blocked, downgrade DETECTED to FLAGGED so subscription creation is skipped.
    effective_review_threshold = review_threshold if review_threshold is not None else REVIEW_THRESHOLD
    raw_disposition = score_to_disposition(score, AUTO_DETECT_THRESHOLD, effective_review_threshold)
    # A blocked sender OR a user one-time mark prevents auto subscription creation:
    # both downgrade DETECTED → FLAGGED so the strong-billing branch is never taken.
    disposition = (
        "FLAGGED"
        if ((sender_blocked or marked_one_time) and raw_disposition == "DETECTED")
        else raw_disposition
    )

    logger.info("Processed %s: score=%.2f disposition=%s name=%s",
                email.source_message_id, score, disposition, canonical_name)

    email_date_str = email.email_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    event_type: str | None = None
    subscription_id: str | None = None

    # Phase 3.6: Pre-compute explanation fields.
    # These will be set more precisely inside the DETECTED/FLAGGED branches once
    # event_type and needs_attachment are known. These are defaults.
    _needs_attachment_precompute = bool(
        tier == 1 and amount is None and pattern in _STRONG_BILLING_PATTERNS
    )
    _decision_reason = _build_decision_reason(
        tier, pattern, amount, currency, billing_cycle, score, disposition, canonical_name
    )
    _evidence_summary = _build_evidence_summary(
        tier, pattern, amount, currency, billing_cycle, canonical_name
    )
    _missing_evidence = _build_missing_evidence(tier, pattern, amount, billing_cycle, disposition)
    _suggested_action = _build_suggested_action(
        tier, pattern, amount, billing_cycle, disposition,
        _needs_attachment_precompute, sender_blocked
    )

    # Phase 3.7: surface the PDF's contribution in the (path-shared) explanation fields.
    if pdf_ev is not None:
        if pdf_amount_used:
            _evidence_summary = _join_note(_evidence_summary, "amount from PDF invoice")
        if getattr(pdf_ev, "billing_period_start", None) and getattr(pdf_ev, "billing_period_end", None):
            _evidence_summary = _join_note(_evidence_summary, "billing period from PDF")
        if pdf_ev.is_refund():
            _missing_evidence = _join_note(_missing_evidence, "PDF indicates a refund, not a charge")
    if _has_unparsed_pdf(email.attachments):
        _missing_evidence = _join_note(_missing_evidence, "PDF attached but not parsed (needs review)")

    # detection_state computed after event_type is known (updated below in each branch)
    new_record_id: str | None = None

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
                _email_ds_for_sub = _compute_email_detection_state(
                    tier, pattern, amount, billing_cycle, disposition,
                    _needs_attachment_precompute, event_type,
                )
                subscription_id, was_created = upsert_subscription(
                    conn, name=canonical_name, amount=amount, currency=currency,
                    billing_cycle=billing_cycle,
                    category=_CATEGORY_MAP.get(canonical_name, "SAAS"),
                    status=effective_status, source_provider=email.source_provider,
                    source_account_id=email.source_account_id,
                    detection_state=_email_to_sub_detection_state(_email_ds_for_sub),
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
        _email_detection_state = _compute_email_detection_state(
            tier, pattern, amount, billing_cycle, disposition,
            _needs_attachment_precompute, event_type,
        )
        _final_suggested = _build_suggested_action(
            tier, pattern, amount, billing_cycle, disposition,
            _needs_attachment_precompute, sender_blocked,
        )
        new_record_id = insert_email_record(
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
            decision_reason=_decision_reason,
            evidence_summary=_evidence_summary,
            missing_evidence=_missing_evidence,
            suggested_action=_final_suggested,
            detection_state=_email_detection_state,
        )
        # Write a payment_event only for confirmed financial/lifecycle events.
        # Derive type from email_record event_type (not from pattern) — it already has
        # full context (was_created, disposition, tier) and avoids the old bug where
        # every PatternType.NONE email created an "unknown_payment" event.
        pe_event_type = _map_payment_event_type(event_type)
        if pe_event_type is not None:
            pe_id = str(_uuid.uuid5(_uuid.NAMESPACE_URL, f"{email.source_message_id}:{pe_event_type}"))
            # is_recurring_candidate: only when there is a confirmed subscription charge or renewal
            # with a known amount — not just any RECEIPT/RENEWAL pattern.
            is_recurring = int(
                pe_event_type in ("subscription_charge", "renewal_charge") and amount is not None
            )
            is_one_time = int(
                pattern == PatternType.RECEIPT and tier == 0 and billing_cycle == "UNKNOWN"
                and amount is not None
            )
            # needs_attachment_review: Tier 1 + financial pattern + no extractable amount.
            # The charge is real but the amount is likely in an attached PDF/invoice.
            # Flags this event for the Phase 3.5 attachment-parsing queue.
            needs_attachment = int(
                tier == 1
                and amount is None
                and pattern in _STRONG_BILLING_PATTERNS
            )
            insert_payment_event(
                conn,
                event_id=pe_id,
                source_message_id=email.source_message_id,
                source_provider=email.source_provider,
                source_account_id=email.source_account_id,
                event_type=pe_event_type,
                amount=amount,
                currency=currency,
                merchant_name=canonical_name,
                event_date=email_date_str,
                is_recurring_candidate=is_recurring,
                is_one_time_candidate=is_one_time,
                subscription_id=subscription_id,
                confidence_score=score,
                needs_attachment_review=needs_attachment,
                decision_reason=_decision_reason,
            )
        conn.commit()

    elif disposition == "FLAGGED":
        if pattern in (PatternType.RECEIPT, PatternType.RENEWAL):
            event_type = "unknown_payment"
        else:
            event_type = _PATTERN_TO_EVENT_TYPE.get(pattern)
        short_evidence = _make_short_evidence(event_type, canonical_name, amount, currency, billing_cycle)
        _flagged_detection_state = _compute_email_detection_state(
            tier, pattern, amount, billing_cycle, disposition,
            _needs_attachment_precompute, event_type,
        )
        if marked_one_time:
            _flagged_detection_state = "ONE_TIME_PAYMENT"
        _flagged_suggested = _build_suggested_action(
            tier, pattern, amount, billing_cycle, disposition,
            _needs_attachment_precompute, sender_blocked,
        )
        new_record_id = insert_email_record(
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
            decision_reason=_decision_reason,
            evidence_summary=_evidence_summary,
            missing_evidence=_missing_evidence,
            suggested_action=_flagged_suggested,
            detection_state=_flagged_detection_state,
        )
        # Write payment_event for FLAGGED emails only when a real financial signal exists:
        # - amount must be confirmed (None → no payment value to record)
        # - event_type must map to a known financial event (NONE and NOTIFICATION → None)
        # This prevents the FLAGGED path from mirroring all 69 FLAGGED email_records as
        # "unknown_payment" events, which made payment_events == email_records in count.
        if amount is not None and event_type is not None:
            pe_event_type_flagged = _map_payment_event_type(event_type)
            if pe_event_type_flagged is not None:
                pe_id = str(_uuid.uuid5(_uuid.NAMESPACE_URL, f"{email.source_message_id}:{pe_event_type_flagged}"))
                insert_payment_event(
                    conn,
                    event_id=pe_id,
                    source_message_id=email.source_message_id,
                    source_provider=email.source_provider,
                    source_account_id=email.source_account_id,
                    event_type=pe_event_type_flagged,
                    amount=amount,
                    currency=currency,
                    merchant_name=canonical_name,
                    event_date=email_date_str,
                    is_recurring_candidate=0,  # FLAGGED = unconfirmed sender; never auto-recurring
                    is_one_time_candidate=1 if marked_one_time else int(billing_cycle == "UNKNOWN"),
                    subscription_id=None,   # FLAGGED events never link to subscriptions
                    confidence_score=score,
                    decision_reason=_decision_reason,
                    user_marked_one_time=int(marked_one_time),
                )
        conn.commit()

    # IGNORED: nothing stored

    # Phase 3.7: persist attachment metadata + structured PDF evidence for a freshly
    # inserted record. new_record_id is None when the email already existed (re-scan
    # dedup) or was IGNORED — so attachments are never duplicated. Reprocessing passes
    # persist_attachments=False (it reconstructs evidence from stored rows for scoring).
    if persist_attachments and new_record_id and email.attachments:
        _persist_attachments(conn, new_record_id, email, canonical_name)
        conn.commit()

    return DetectionResult(
        source_message_id=email.source_message_id,
        disposition=disposition,
        confidence_score=score,
        subscription_id=subscription_id,
        canonical_name=canonical_name,
        event_type=event_type,
    )
