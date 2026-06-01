import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _migration_version(sql: str) -> int | None:
    """Return the schema_version number inserted by this migration, or None.

    Every migration ends with:
        INSERT OR IGNORE INTO schema_version (version, ...) VALUES (N, ...)
    We extract N so init_db can skip migrations that are already applied.
    """
    m = re.search(
        r"INSERT\s+OR\s+IGNORE\s+INTO\s+schema_version[^;]*VALUES\s*\(\s*(\d+)",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    return int(m.group(1)) if m else None


def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(db_path: str) -> None:
    """Apply all pending migrations in order.

    Idempotent: migrations whose version is already recorded in schema_version
    are skipped, so calling init_db on an existing database is safe.
    """
    conn = get_connection(db_path)
    try:
        for sql_path in sorted(_MIGRATIONS_DIR.glob("*.sql")):
            sql = sql_path.read_text(encoding="utf-8")
            version = _migration_version(sql)
            if version is not None:
                try:
                    already = conn.execute(
                        "SELECT 1 FROM schema_version WHERE version = ?", (version,)
                    ).fetchone()
                    if already:
                        continue          # migration already applied — skip
                except sqlite3.OperationalError:
                    pass                  # schema_version doesn't exist yet — run it
            conn.executescript(sql)
        conn.commit()
    finally:
        conn.close()


# ── Subscriptions ────────────────────────────────────────────────────────────

def upsert_subscription(conn: sqlite3.Connection, *, name: str, amount: float | None,
                         currency: str, billing_cycle: str, category: str,
                         status: str, source_provider: str, service_url: str | None = None,
                         next_renewal: str | None = None,
                         detection_state: str | None = None,
                         source_account_id: str | None = None) -> tuple[str, bool]:
    """Insert or update a subscription by canonical name.
    Returns (subscription_id, was_created).

    detection_state: evidence quality (CONFIRMED_ACTIVE, LIKELY_SUBSCRIPTION, etc.).
    On update, detection_state is only upgraded (CONFIRMED_ACTIVE cannot be downgraded).
    source_account_id: which Gmail account produced this subscription (multi-account).
    """
    _DETECTION_RANK = {
        "CONFIRMED_ACTIVE": 5, "LIKELY_SUBSCRIPTION": 4, "POSSIBLE_SUBSCRIPTION": 3,
        "NEEDS_ATTACHMENT_REVIEW": 2, "NEEDS_USER_REVIEW": 1,
    }

    now = _now()
    row = conn.execute(
        "SELECT subscription_id, detection_state FROM subscriptions WHERE name = ?", (name,)
    ).fetchone()

    if row:
        sub_id = row["subscription_id"]
        existing_ds = row["detection_state"] if "detection_state" in row.keys() else None
        # Only upgrade detection_state, never downgrade (CONFIRMED_ACTIVE is sticky)
        new_ds = existing_ds
        if detection_state and _DETECTION_RANK.get(detection_state, 0) > _DETECTION_RANK.get(existing_ds or "", 0):
            new_ds = detection_state
        conn.execute(
            """UPDATE subscriptions
               SET amount = COALESCE(?, amount),
                   currency = COALESCE(?, currency),
                   billing_cycle = CASE WHEN ? != 'UNKNOWN' THEN ? ELSE billing_cycle END,
                   category = ?,
                   status = ?,
                   detection_state = COALESCE(?, detection_state),
                   last_seen = ?,
                   updated_at = ?
               WHERE subscription_id = ?""",
            (amount, currency, billing_cycle, billing_cycle, category, status,
             new_ds, now, now, sub_id),
        )
        return sub_id, False
    else:
        sub_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO subscriptions
               (subscription_id, name, service_url, amount, currency, billing_cycle,
                next_renewal, category, status, first_seen, last_seen, source_provider,
                source_account_id, detection_state, created_at, updated_at)
               VALUES (?, ?, ?, ?, COALESCE(?, 'USD'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (sub_id, name, service_url, amount, currency, billing_cycle,
             next_renewal, category, status, now, now, source_provider,
             source_account_id, detection_state, now, now),
        )
        return sub_id, True


def update_subscription_status(conn: sqlite3.Connection, name: str, status: str) -> None:
    now = _now()
    conn.execute(
        "UPDATE subscriptions SET status = ?, updated_at = ? WHERE name = ?",
        (status, now, name),
    )


def update_subscription_lifecycle(
    conn: sqlite3.Connection,
    subscription_id: str,
    *,
    first_charge_date: str | None = None,
    last_charge_date: str | None = None,
    cancelled_at: str | None = None,
    trial_ends_at: str | None = None,
) -> None:
    """Update lifecycle timestamp columns on a subscription.
    first_charge_date uses MIN semantics (earliest date seen ever).
    last_charge_date uses MAX semantics (most recent date seen).
    cancelled_at and trial_ends_at use COALESCE (set once; first write wins).
    Processing order does not matter — results are always correct regardless of
    whether emails are processed newest-first or oldest-first.
    """
    now = _now()
    fields = []
    params: list = []
    if first_charge_date is not None:
        # MIN: keep the earlier of stored vs new (first charge = oldest date ever seen)
        fields.append("""first_charge_date = CASE
            WHEN first_charge_date IS NULL OR ? < first_charge_date THEN ?
            ELSE first_charge_date
        END""")
        params.extend([first_charge_date, first_charge_date])
    if last_charge_date is not None:
        # MAX: keep the later of stored vs new (last charge = most recent date ever seen)
        fields.append("""last_charge_date = CASE
            WHEN last_charge_date IS NULL OR ? > last_charge_date THEN ?
            ELSE last_charge_date
        END""")
        params.extend([last_charge_date, last_charge_date])
    if cancelled_at is not None:
        fields.append("cancelled_at = COALESCE(cancelled_at, ?)")
        params.append(cancelled_at)
    if trial_ends_at is not None:
        fields.append("trial_ends_at = COALESCE(trial_ends_at, ?)")
        params.append(trial_ends_at)
    if not fields:
        return
    fields.append("updated_at = ?")
    params.append(now)
    params.append(subscription_id)
    conn.execute(
        f"UPDATE subscriptions SET {', '.join(fields)} WHERE subscription_id = ?",
        params,
    )


def get_subscriptions(
    conn: sqlite3.Connection,
    status: str | None = None,
    source_provider: str | None = None,
) -> list[sqlite3.Row]:
    conditions = []
    params: list = []
    if status:
        conditions.append("status = ?")
        params.append(status)
    if source_provider:
        conditions.append("source_provider = ?")
        params.append(source_provider)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return conn.execute(
        f"SELECT * FROM subscriptions {where} ORDER BY name", params
    ).fetchall()


def get_subscription_by_id(conn: sqlite3.Connection, subscription_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM subscriptions WHERE subscription_id = ?", (subscription_id,)
    ).fetchone()


def create_subscription_manual(
    conn: sqlite3.Connection,
    *,
    name: str,
    amount: float | None = None,
    currency: str = "USD",
    billing_cycle: str = "UNKNOWN",
    category: str = "OTHER",
    status: str = "ACTIVE",
    source_provider: str = "MOCK",
    service_url: str | None = None,
) -> str:
    """Insert a subscription created manually by the user. Returns subscription_id.

    This is distinct from upsert_subscription() — it always creates a new record
    without trying to merge with an existing subscription by name. Used by the
    manual CRUD API endpoint (POST /api/subscriptions).
    """
    now = _now()
    sub_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO subscriptions
           (subscription_id, name, service_url, amount, currency, billing_cycle,
            next_renewal, category, status, first_seen, last_seen, source_provider,
            created_at, updated_at)
           VALUES (?, ?, ?, ?, COALESCE(?, 'USD'), ?, NULL, ?, ?, ?, ?, ?, ?, ?)""",
        (sub_id, name, service_url, amount, currency, billing_cycle,
         category, status, now, now, source_provider, now, now),
    )
    return sub_id


def update_subscription_fields(
    conn: sqlite3.Connection,
    subscription_id: str,
    *,
    name: str | None = None,
    amount: float | None = None,
    currency: str | None = None,
    billing_cycle: str | None = None,
    status: str | None = None,
    category: str | None = None,
    service_url: str | None = None,
) -> bool:
    """Update specific fields on a subscription. Returns True if row was found.

    Only non-None arguments are updated. Used by POST /api/subscriptions/{id}/update.
    Allows users to correct amount, currency, cycle, status, or name.
    """
    row = conn.execute(
        "SELECT subscription_id FROM subscriptions WHERE subscription_id = ?",
        (subscription_id,),
    ).fetchone()
    if not row:
        return False

    now = _now()
    fields: list[str] = []
    params: list = []
    if name is not None:
        fields.append("name = ?"); params.append(name)
    if amount is not None:
        fields.append("amount = ?"); params.append(amount)
    if currency is not None:
        fields.append("currency = ?"); params.append(currency)
    if billing_cycle is not None:
        fields.append("billing_cycle = ?"); params.append(billing_cycle)
    if status is not None:
        fields.append("status = ?"); params.append(status)
    if category is not None:
        fields.append("category = ?"); params.append(category)
    if service_url is not None:
        fields.append("service_url = ?"); params.append(service_url)
    if not fields:
        return True  # nothing to update
    fields.append("updated_at = ?"); params.append(now)
    params.append(subscription_id)
    conn.execute(
        f"UPDATE subscriptions SET {', '.join(fields)} WHERE subscription_id = ?", params
    )
    return True


def delete_subscription(conn: sqlite3.Connection, subscription_id: str) -> bool:
    """Delete a subscription by ID. Returns True if it existed.

    payment_events.subscription_id is SET NULL on delete (FK ON DELETE SET NULL).
    email_records.subscription_id is CASCADE-deleted (FK ON DELETE CASCADE).
    Used by DELETE /api/subscriptions/{id} for manual false-positive removal.
    """
    row = conn.execute(
        "SELECT subscription_id FROM subscriptions WHERE subscription_id = ?",
        (subscription_id,),
    ).fetchone()
    if not row:
        return False
    conn.execute(
        "DELETE FROM subscriptions WHERE subscription_id = ?", (subscription_id,)
    )
    return True


def link_payment_event(
    conn: sqlite3.Connection,
    event_id: str,
    subscription_id: str,
) -> bool:
    """Set subscription_id on a payment_event. Returns True if event found."""
    row = conn.execute(
        "SELECT event_id FROM payment_events WHERE event_id = ?", (event_id,)
    ).fetchone()
    if not row:
        return False
    conn.execute(
        "UPDATE payment_events SET subscription_id = ? WHERE event_id = ?",
        (subscription_id, event_id),
    )
    return True


def unlink_payment_event(conn: sqlite3.Connection, event_id: str) -> bool:
    """Set subscription_id = NULL on a payment_event. Returns True if event found."""
    row = conn.execute(
        "SELECT event_id FROM payment_events WHERE event_id = ?", (event_id,)
    ).fetchone()
    if not row:
        return False
    conn.execute(
        "UPDATE payment_events SET subscription_id = NULL WHERE event_id = ?",
        (event_id,),
    )
    return True


# ── Email records ────────────────────────────────────────────────────────────

def insert_email_record(conn: sqlite3.Connection, *, source_message_id: str,
                         source_provider: str, source_account_id: str,
                         source_account_email: str, subscription_id: str | None,
                         sender_address: str, sender_name: str | None, subject: str,
                         email_date: str, amount_extracted: float | None,
                         currency_extracted: str | None, confidence_score: float,
                         disposition: str, event_type: str | None = None,
                         billing_period_start: str | None = None,
                         billing_period_end: str | None = None,
                         short_evidence: str | None = None,
                         # Phase 3.6: explanation fields (structured summaries, no raw content)
                         decision_reason: str | None = None,
                         evidence_summary: str | None = None,
                         missing_evidence: str | None = None,
                         suggested_action: str | None = None,
                         detection_state: str | None = None) -> str | None:
    """Insert an email record. Returns None if source_message_id already exists (dedup).

    Phase 3.6 adds 5 optional explanation fields. All must be structured summaries only —
    no raw subject, body, HTML, snippet, sender address, or PII.
    """
    existing = conn.execute(
        "SELECT record_id FROM email_records WHERE source_message_id = ?",
        (source_message_id,),
    ).fetchone()
    if existing:
        return None

    record_id = str(uuid.uuid4())
    now = _now()
    conn.execute(
        """INSERT INTO email_records
           (record_id, subscription_id, source_message_id, source_provider,
            source_account_id, source_account_email, sender_address, sender_name,
            subject, email_date, amount_extracted, currency_extracted,
            confidence_score, disposition, event_type, billing_period_start,
            billing_period_end, short_evidence,
            decision_reason, evidence_summary, missing_evidence, suggested_action,
            detection_state, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (record_id, subscription_id, source_message_id, source_provider,
         source_account_id, source_account_email, sender_address, sender_name,
         subject, email_date, amount_extracted, currency_extracted,
         confidence_score, disposition, event_type, billing_period_start,
         billing_period_end, short_evidence,
         decision_reason, evidence_summary, missing_evidence, suggested_action,
         detection_state, now),
    )
    return record_id


def get_email_records(
    conn: sqlite3.Connection,
    disposition: str | None = None,
    account_id: str | None = None,
    source_provider: str | None = None,
    include_dismissed: bool = False,
) -> list[sqlite3.Row]:
    """Return email_records with optional filters.

    By default (include_dismissed=False) user-dismissed records are excluded
    from results so the Review Queue stays clean after dismissal.
    Pass include_dismissed=True to include them (e.g. for validation report).
    """
    conditions = []
    params: list = []
    if disposition:
        conditions.append("disposition = ?")
        params.append(disposition)
    if account_id:
        conditions.append("source_account_id = ?")
        params.append(account_id)
    if source_provider:
        conditions.append("source_provider = ?")
        params.append(source_provider)
    if not include_dismissed:
        conditions.append("user_dismissed = 0")
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return conn.execute(
        f"SELECT * FROM email_records {where} ORDER BY email_date DESC", params
    ).fetchall()


def get_records_for_subscription(conn: sqlite3.Connection, subscription_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM email_records WHERE subscription_id = ? ORDER BY email_date DESC",
        (subscription_id,),
    ).fetchall()


# ── Summary ──────────────────────────────────────────────────────────────────

def get_summary(conn: sqlite3.Connection, source_provider: str | None = None) -> dict:
    """Return dashboard summary counts, optionally filtered by source_provider.

    When source_provider='GMAIL', also sets has_mock_data=True if any MOCK rows
    still exist in the database (they are excluded from counts but present in DB).
    """
    sp_clause = " AND source_provider = ?" if source_provider else ""
    sp_params: list = [source_provider] if source_provider else []

    active = conn.execute(
        "SELECT COUNT(*) as cnt, SUM(CASE WHEN billing_cycle='ANNUAL' THEN amount/12.0 ELSE amount END) as monthly "
        f"FROM subscriptions WHERE status = 'ACTIVE' AND amount IS NOT NULL{sp_clause}",
        sp_params,
    ).fetchone()

    flagged_count = conn.execute(
        f"SELECT COUNT(*) as cnt FROM email_records WHERE disposition = 'FLAGGED'{sp_clause}",
        sp_params,
    ).fetchone()["cnt"]

    detected_count = conn.execute(
        f"SELECT COUNT(*) as cnt FROM email_records WHERE disposition = 'DETECTED'{sp_clause}",
        sp_params,
    ).fetchone()["cnt"]

    # When in Gmail mode, also report whether any MOCK rows still exist in the DB
    # (they are excluded from the counts above but the user may want to clean them up)
    has_mock_data = False
    if source_provider == "GMAIL":
        has_mock_data = bool(
            conn.execute(
                "SELECT 1 FROM subscriptions WHERE source_provider = 'MOCK' "
                "UNION SELECT 1 FROM email_records WHERE source_provider = 'MOCK' LIMIT 1"
            ).fetchone()
        )

    # Per-currency totals for ACTIVE subscriptions with known amount
    currency_rows = conn.execute(
        "SELECT currency, "
        "SUM(CASE WHEN billing_cycle='ANNUAL' THEN amount/12.0 ELSE amount END) as monthly_total, "
        "COUNT(*) as cnt "
        f"FROM subscriptions WHERE status='ACTIVE' AND amount IS NOT NULL{sp_clause} "
        "GROUP BY currency ORDER BY monthly_total DESC",
        sp_params,
    ).fetchall()
    monthly_costs_by_currency = {r["currency"]: round(r["monthly_total"], 2) for r in currency_rows}
    # Backwards-compat: expose the largest-value currency as top-level
    top_currency = currency_rows[0]["currency"] if currency_rows else "USD"
    top_total = currency_rows[0]["monthly_total"] if currency_rows else (active["monthly"] or 0.0)

    # Count UNKNOWN-status subscriptions (detected but amount/cycle not yet confirmed).
    # Used by the dashboard to show "N unconfirmed subscriptions" instead of "$0.00"
    # when no ACTIVE subscriptions exist.
    unconfirmed_count = conn.execute(
        f"SELECT COUNT(*) as cnt FROM subscriptions WHERE status = 'UNKNOWN'{sp_clause}",
        sp_params,
    ).fetchone()["cnt"]

    return {
        "total_monthly_cost": round(top_total or 0.0, 2),
        "currency": top_currency,
        "active_count": active["cnt"],
        "detected_count": detected_count,
        "flagged_count": flagged_count,
        "has_mock_data": has_mock_data,
        "monthly_costs_by_currency": monthly_costs_by_currency,
        "unconfirmed_count": unconfirmed_count,
    }


# ── Connected accounts ────────────────────────────────────────────────────────

def get_connected_accounts(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return all active connected accounts ordered by creation date."""
    return conn.execute(
        "SELECT * FROM connected_accounts ORDER BY created_at"
    ).fetchall()


def get_connected_account(conn: sqlite3.Connection, account_id: str) -> sqlite3.Row | None:
    """Return a single connected account by ID, or None if not found."""
    return conn.execute(
        "SELECT * FROM connected_accounts WHERE account_id = ?", (account_id,)
    ).fetchone()


def get_active_gmail_account(conn: sqlite3.Connection) -> sqlite3.Row | None:
    """Return the first active GMAIL account (oldest by created_at), or None."""
    return conn.execute(
        """SELECT * FROM connected_accounts
           WHERE source_provider = 'GMAIL' AND is_active = 1
           ORDER BY created_at LIMIT 1"""
    ).fetchone()


def get_all_active_gmail_accounts(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return ALL active GMAIL accounts ordered by creation date.

    Used for multi-account scanning — iterates over every connected account.
    Returns a list (empty if no Gmail accounts connected).
    """
    return conn.execute(
        """SELECT * FROM connected_accounts
           WHERE source_provider = 'GMAIL' AND is_active = 1
           ORDER BY created_at"""
    ).fetchall()


def upsert_connected_account(
    conn: sqlite3.Connection,
    *,
    account_id: str,
    source_provider: str,
    account_email: str,
    display_name: str | None = None,
) -> None:
    """Insert or update a connected account record."""
    conn.execute(
        """INSERT INTO connected_accounts
               (account_id, source_provider, account_email, display_name, is_active)
               VALUES (?, ?, ?, ?, 1)
           ON CONFLICT(account_id) DO UPDATE SET
               account_email = excluded.account_email,
               display_name  = excluded.display_name,
               is_active     = 1""",
        (account_id, source_provider, account_email, display_name),
    )


def deactivate_connected_account(conn: sqlite3.Connection, account_id: str) -> None:
    """Mark an account as inactive (disconnect). Tokens must be deleted separately."""
    conn.execute(
        "UPDATE connected_accounts SET is_active = 0 WHERE account_id = ?",
        (account_id,),
    )


# ── Scan jobs ────────────────────────────────────────────────────────────────

def create_scan_job(
    conn: sqlite3.Connection,
    *,
    scan_id: str,
    account_id: str | None,
    mode: str,
    scan_range: str | None,
    content_access_level: str,
) -> None:
    """Create a new scan job record with status='pending'."""
    now = _now()
    conn.execute(
        """INSERT INTO scan_jobs
           (scan_id, account_id, mode, scan_range, content_access_level,
            status, created_at, last_activity_at)
           VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)""",
        (scan_id, account_id, mode, scan_range, content_access_level, now, now),
    )


def update_scan_job(conn: sqlite3.Connection, scan_id: str, **fields) -> None:
    """Update any subset of scan_jobs columns. Always sets last_activity_at=now.

    Example:
        update_scan_job(conn, sid, status="processing", processed_count=50)
    """
    if not fields:
        return
    now = _now()
    cols = list(fields.keys()) + ["last_activity_at"]
    vals = list(fields.values()) + [now, scan_id]
    set_clause = ", ".join(f"{c} = ?" for c in cols)
    conn.execute(
        f"UPDATE scan_jobs SET {set_clause} WHERE scan_id = ?",
        vals,
    )


def get_scan_job(conn: sqlite3.Connection, scan_id: str) -> sqlite3.Row | None:
    """Return a single scan job by ID, or None if not found."""
    return conn.execute(
        "SELECT * FROM scan_jobs WHERE scan_id = ?", (scan_id,)
    ).fetchone()


def get_running_scan_jobs(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return all scan jobs with status pending/collecting/processing."""
    return conn.execute(
        "SELECT * FROM scan_jobs WHERE status IN ('pending','collecting','processing')"
    ).fetchall()


# ── Payment events ────────────────────────────────────────────────────────────

def insert_payment_event(
    conn: sqlite3.Connection,
    *,
    event_id: str,
    source_message_id: str,
    source_provider: str,
    source_account_id: str,
    event_type: str,
    amount: float | None,
    currency: str | None,
    merchant_name: str,
    event_date: str,
    is_recurring_candidate: int,
    is_one_time_candidate: int,
    subscription_id: str | None,
    confidence_score: float,
    needs_attachment_review: int = 0,
    decision_reason: str | None = None,  # Phase 3.6: structured explanation
    user_marked_one_time: int = 0,       # Phase 3.7: re-applied on reprocess from corrections
) -> None:
    """Insert a payment event. INSERT OR IGNORE on event_id — safe for re-scans.

    Privacy: stores NO raw email content. merchant_name is the canonical name from
    sender_list.py (e.g. 'Spotify'), never the raw sender address or email subject.
    decision_reason is a structured summary (tier + pattern + score), never raw subject.

    needs_attachment_review=1 when: amount is NULL + Tier 1 sender + financial pattern.
    Signals that the charge amount is likely in an attached PDF/invoice (Phase 3.5 queue).
    """
    conn.execute(
        """INSERT OR IGNORE INTO payment_events
           (event_id, source_message_id, source_provider, source_account_id,
            event_type, amount, currency, merchant_name, event_date,
            is_recurring_candidate, is_one_time_candidate,
            subscription_id, confidence_score, needs_attachment_review, decision_reason,
            user_marked_one_time)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (event_id, source_message_id, source_provider, source_account_id,
         event_type, amount, currency, merchant_name, event_date,
         is_recurring_candidate, is_one_time_candidate,
         subscription_id, confidence_score, needs_attachment_review, decision_reason,
         user_marked_one_time),
    )


def get_payment_events(
    conn: sqlite3.Connection,
    source_message_id: str | None = None,
    merchant_name: str | None = None,
    subscription_id: str | None = None,
    event_type: str | None = None,
    source_provider: str | None = None,
    is_recurring_candidate: int | None = None,
    is_one_time_candidate: int | None = None,
    limit: int = 500,
) -> list[sqlite3.Row]:
    """Return payment events, optionally filtered. Safe fields only — no raw email content.

    Privacy: payment_events table contains no subject, sender_address, snippet, body_text,
    or body_html. merchant_name is the canonical name from sender_list.py (e.g. 'Spotify').
    """
    conditions = []
    params: list = []
    if source_message_id is not None:
        conditions.append("source_message_id = ?")
        params.append(source_message_id)
    if merchant_name is not None:
        conditions.append("merchant_name = ?")
        params.append(merchant_name)
    if subscription_id is not None:
        conditions.append("subscription_id = ?")
        params.append(subscription_id)
    if event_type is not None:
        conditions.append("event_type = ?")
        params.append(event_type)
    if source_provider is not None:
        conditions.append("source_provider = ?")
        params.append(source_provider)
    if is_recurring_candidate is not None:
        conditions.append("is_recurring_candidate = ?")
        params.append(is_recurring_candidate)
    if is_one_time_candidate is not None:
        conditions.append("is_one_time_candidate = ?")
        params.append(is_one_time_candidate)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return conn.execute(
        f"SELECT * FROM payment_events {where} ORDER BY event_date DESC LIMIT ?",
        params + [limit],
    ).fetchall()


# ── Attachments + PDF-derived evidence (Phase 3.7) ────────────────────────────

def insert_attachment(
    conn: sqlite3.Connection,
    *,
    attachment_row_id: str | None = None,
    email_record_id: str | None,
    source_message_id: str,
    source_account_id: str | None = None,
    gmail_attachment_id: str | None = None,
    filename: str | None = None,
    mime_type: str | None = None,
    size_bytes: int | None = None,
    detected_attachment_type: str | None = None,
    processing_status: str = "PENDING",
    parser_version: str | None = None,
) -> str:
    """Insert an email_attachments row (metadata only — no content). Returns the row id."""
    row_id = attachment_row_id or str(uuid.uuid4())
    now = _now()
    conn.execute(
        """INSERT INTO email_attachments
           (attachment_row_id, email_record_id, source_message_id, source_account_id,
            gmail_attachment_id, filename, mime_type, size_bytes,
            detected_attachment_type, processing_status, parser_version,
            created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (row_id, email_record_id, source_message_id, source_account_id,
         gmail_attachment_id, filename, mime_type, size_bytes,
         detected_attachment_type, processing_status, parser_version, now, now),
    )
    return row_id


def insert_attachment_fields(
    conn: sqlite3.Connection,
    *,
    field_row_id: str | None = None,
    attachment_row_id: str | None,
    email_record_id: str | None = None,
    source_message_id: str | None = None,
    provider: str | None = None,
    product_name: str | None = None,
    amount: float | None = None,
    currency: str | None = None,
    invoice_date: str | None = None,
    payment_date: str | None = None,
    billing_period_start: str | None = None,
    billing_period_end: str | None = None,
    inferred_cycle: str | None = None,
    tax_amount: float | None = None,
    invoice_number: str | None = None,
    subscription_indicators: str | None = None,
    evidence_reasons: str | None = None,
    missing_evidence: str | None = None,
    penalty_reasons: str | None = None,
    confidence_score: float = 0.0,
    extraction_status: str | None = None,
    parser_version: str | None = None,
) -> str:
    """Insert a structured PDF-derived evidence row.

    Privacy: stores NO raw PDF text. The *_indicators / *_reasons columns hold SHORT
    CODED TOKENS (e.g. 'amount_in_pdf;billing_period_found'), joined by the caller —
    never sentences or text copied from the PDF.
    """
    row_id = field_row_id or str(uuid.uuid4())
    conn.execute(
        """INSERT INTO attachment_extracted_fields
           (field_row_id, attachment_row_id, email_record_id, source_message_id,
            provider, product_name, amount, currency, invoice_date, payment_date,
            billing_period_start, billing_period_end, inferred_cycle, tax_amount,
            invoice_number, subscription_indicators, evidence_reasons, missing_evidence,
            penalty_reasons, confidence_score, extraction_status, parser_version, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (row_id, attachment_row_id, email_record_id, source_message_id,
         provider, product_name, amount, currency, invoice_date, payment_date,
         billing_period_start, billing_period_end, inferred_cycle, tax_amount,
         invoice_number, subscription_indicators, evidence_reasons, missing_evidence,
         penalty_reasons, confidence_score, extraction_status, parser_version, _now()),
    )
    return row_id


def get_attachments_for_record(conn: sqlite3.Connection, email_record_id: str) -> list[sqlite3.Row]:
    """Return email_attachments rows for an email_record (safe metadata only)."""
    return conn.execute(
        "SELECT * FROM email_attachments WHERE email_record_id = ? ORDER BY created_at",
        (email_record_id,),
    ).fetchall()


def get_attachments_for_message(conn: sqlite3.Connection, source_message_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM email_attachments WHERE source_message_id = ? ORDER BY created_at",
        (source_message_id,),
    ).fetchall()


def get_attachment_fields_for_record(conn: sqlite3.Connection, email_record_id: str) -> list[sqlite3.Row]:
    """Return structured PDF-derived evidence rows for an email_record (no raw text)."""
    return conn.execute(
        "SELECT * FROM attachment_extracted_fields WHERE email_record_id = ? ORDER BY created_at",
        (email_record_id,),
    ).fetchall()


def get_attachment_fields_for_message(conn: sqlite3.Connection, source_message_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM attachment_extracted_fields WHERE source_message_id = ? ORDER BY created_at",
        (source_message_id,),
    ).fetchall()


# ── User corrections (Phase 3.5) ──────────────────────────────────────────────

def insert_user_correction(
    conn: sqlite3.Connection,
    *,
    correction_id: str,
    email_record_id: str | None,
    subscription_id: str | None,
    correction_type: str,
    new_value: str | None = None,
    sender_address: str | None = None,  # Phase 3.6: sender-level scope
) -> None:
    """Insert a user correction entry (audit trail).

    Privacy: stores only structured IDs and correction_type.
    No raw email content is stored.

    correction_type values:
      'DISMISSED_EMAIL' — user dismissed from review queue (not a subscription)
      'CONFIRMED_SUB'   — user confirmed UNKNOWN subscription as real
      'REJECTED_SUB'    — user deleted/rejected subscription (false positive)
      'RELABELED'       — user corrected provider/product canonical name
    """
    conn.execute(
        """INSERT OR IGNORE INTO user_corrections
           (correction_id, email_record_id, subscription_id, sender_address, correction_type, new_value)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (correction_id, email_record_id, subscription_id, sender_address, correction_type, new_value),
    )


def dismiss_email_record(conn: sqlite3.Connection, record_id: str) -> bool:
    """Mark an email_record as user-dismissed (sets user_dismissed=1).

    Also inserts a DISMISSED_EMAIL correction for the audit trail.
    Returns True if the record was found, False if not found.

    Privacy-safe: only touches structured IDs and the user_dismissed flag.
    No raw email content is read or written.
    """
    import uuid as _uuid
    row = conn.execute(
        "SELECT record_id FROM email_records WHERE record_id = ?", (record_id,)
    ).fetchone()
    if row is None:
        return False

    conn.execute(
        "UPDATE email_records SET user_dismissed = 1 WHERE record_id = ?",
        (record_id,),
    )
    correction_id = str(_uuid.uuid4())
    insert_user_correction(
        conn,
        correction_id=correction_id,
        email_record_id=record_id,
        subscription_id=None,
        correction_type="DISMISSED_EMAIL",
    )
    return True


def get_dismissed_email_ids(
    conn: sqlite3.Connection,
    source_provider: str | None = None,
) -> set[str]:
    """Return set of record_ids where user_dismissed=1.

    Used by ReviewQueue on page load to filter already-dismissed records.
    """
    if source_provider:
        rows = conn.execute(
            "SELECT record_id FROM email_records WHERE user_dismissed=1 AND source_provider=?",
            (source_provider,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT record_id FROM email_records WHERE user_dismissed=1"
        ).fetchall()
    return {r[0] for r in rows}


def get_user_corrections(
    conn: sqlite3.Connection,
    correction_type: str | None = None,
    limit: int = 200,
) -> list[sqlite3.Row]:
    """Return user corrections, optionally filtered by type."""
    if correction_type:
        return conn.execute(
            "SELECT * FROM user_corrections WHERE correction_type=? ORDER BY created_at DESC LIMIT ?",
            (correction_type, limit),
        ).fetchall()
    return conn.execute(
        "SELECT * FROM user_corrections ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()


# ── Phase 3.6: Explainability + Correction-Awareness ─────────────────────────

import hashlib as _hashlib


def account_alias(account_id: str | None) -> str | None:
    """Return an 8-character SHA-256 prefix of account_id for privacy-safe display.

    The alias is deterministic: same account_id always produces the same alias.
    It does NOT expose the raw email address — only an irreversible short hash.
    Used in API responses and the validation report to identify accounts without
    revealing PII.
    """
    if not account_id:
        return None
    return _hashlib.sha256(account_id.encode()).hexdigest()[:8]


def get_relabeled_name(conn: sqlite3.Connection, sender_address: str) -> str | None:
    """Return the user-corrected canonical name for this sender, or None.

    If the user relabeled a provider (e.g., "Google" → "Google One"),
    this returns the corrected name so the detector can use it instead of
    the auto-resolved canonical name.
    """
    row = conn.execute(
        """SELECT new_value FROM user_corrections
           WHERE sender_address = ? AND correction_type = 'RELABELED'
           ORDER BY created_at DESC LIMIT 1""",
        (sender_address,),
    ).fetchone()
    return row["new_value"] if row else None


def is_sender_blocked(conn: sqlite3.Connection, sender_address: str) -> bool:
    """Return True if the user has a REJECTED_SUB correction for this sender.

    When True, the detector should not auto-create a new subscription from emails
    sent by this address — the user has explicitly said this sender is not a subscription.
    The email_record is still stored (for audit), but subscription creation is skipped.
    """
    row = conn.execute(
        """SELECT 1 FROM user_corrections
           WHERE sender_address = ? AND correction_type = 'REJECTED_SUB' LIMIT 1""",
        (sender_address,),
    ).fetchone()
    return row is not None


def is_event_marked_one_time(conn: sqlite3.Connection, source_message_id: str) -> bool:
    """Return True if the user marked this message's event as a one-time payment.

    Resolved via a MARKED_ONE_TIME correction linked (by email_record_id) to an
    email_record with this source_message_id. This lets reprocessing preserve the
    user's "not a recurring subscription" decision: when payment_events are deleted and
    recreated, the detector re-marks the event one-time and creates no subscription.
    Works identically for PDF-derived and subject/body-derived events.
    """
    row = conn.execute(
        """SELECT 1 FROM user_corrections uc
           JOIN email_records er ON er.record_id = uc.email_record_id
           WHERE uc.correction_type = 'MARKED_ONE_TIME'
             AND er.source_message_id = ? LIMIT 1""",
        (source_message_id,),
    ).fetchone()
    return row is not None


def mark_one_time(
    conn: sqlite3.Connection,
    *,
    email_record_id: str | None = None,
    payment_event_id: str | None = None,
    sender_address: str | None = None,
) -> None:
    """Mark an email_record/payment_event as a one-time payment (not a recurring subscription).

    Inserts a MARKED_ONE_TIME correction in user_corrections and sets
    payment_events.user_marked_one_time=1 if payment_event_id is given.

    Privacy: stores only structured IDs and correction_type, no raw email content.
    """
    correction_id = str(uuid.uuid4())
    insert_user_correction(
        conn,
        correction_id=correction_id,
        email_record_id=email_record_id,
        subscription_id=None,
        sender_address=sender_address,
        correction_type="MARKED_ONE_TIME",
    )
    if payment_event_id:
        conn.execute(
            "UPDATE payment_events SET user_marked_one_time=1 WHERE event_id=?",
            (payment_event_id,),
        )


def relabel_provider(
    conn: sqlite3.Connection,
    *,
    new_name: str,
    subscription_id: str | None = None,
    sender_address: str | None = None,
) -> None:
    """Relabel a provider/product canonical name and persist the correction.

    Updates the subscription name (if subscription_id given) and inserts a
    sender-level RELABELED correction so future scans/reprocessing use the
    corrected name for emails from this sender.
    """
    correction_id = str(uuid.uuid4())
    if subscription_id:
        conn.execute(
            "UPDATE subscriptions SET name=?, updated_at=? WHERE subscription_id=?",
            (new_name, _now(), subscription_id),
        )
    insert_user_correction(
        conn,
        correction_id=correction_id,
        email_record_id=None,
        subscription_id=subscription_id,
        sender_address=sender_address,
        correction_type="RELABELED",
        new_value=new_name,
    )


def merge_subscriptions(
    conn: sqlite3.Connection,
    source_subscription_id: str,
    target_subscription_id: str,
) -> bool:
    """Merge source subscription into target. Returns True if source was found.

    Moves all email_records and payment_events from source → target,
    then deletes the source subscription row. Inserts a MERGED correction
    for the audit trail.

    Privacy: operates only on structured IDs. No raw content is touched.
    """
    source = conn.execute(
        "SELECT subscription_id FROM subscriptions WHERE subscription_id=?",
        (source_subscription_id,),
    ).fetchone()
    if not source:
        return False

    conn.execute(
        "UPDATE email_records SET subscription_id=? WHERE subscription_id=?",
        (target_subscription_id, source_subscription_id),
    )
    conn.execute(
        "UPDATE payment_events SET subscription_id=? WHERE subscription_id=?",
        (target_subscription_id, source_subscription_id),
    )
    conn.execute(
        "DELETE FROM subscriptions WHERE subscription_id=?",
        (source_subscription_id,),
    )
    insert_user_correction(
        conn,
        correction_id=str(uuid.uuid4()),
        email_record_id=None,
        subscription_id=target_subscription_id,
        sender_address=None,
        correction_type="MERGED",
        new_value=source_subscription_id,
    )
    return True


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
