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
                         next_renewal: str | None = None) -> tuple[str, bool]:
    """Insert or update a subscription by canonical name.
    Returns (subscription_id, was_created).
    """
    now = _now()
    row = conn.execute(
        "SELECT subscription_id FROM subscriptions WHERE name = ?", (name,)
    ).fetchone()

    if row:
        sub_id = row["subscription_id"]
        conn.execute(
            """UPDATE subscriptions
               SET amount = COALESCE(?, amount),
                   currency = COALESCE(?, currency),
                   billing_cycle = CASE WHEN ? != 'UNKNOWN' THEN ? ELSE billing_cycle END,
                   category = ?,
                   status = ?,
                   last_seen = ?,
                   updated_at = ?
               WHERE subscription_id = ?""",
            (amount, currency, billing_cycle, billing_cycle, category, status, now, now, sub_id),
        )
        return sub_id, False
    else:
        sub_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO subscriptions
               (subscription_id, name, service_url, amount, currency, billing_cycle,
                next_renewal, category, status, first_seen, last_seen, source_provider,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, COALESCE(?, 'USD'), ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (sub_id, name, service_url, amount, currency, billing_cycle,
             next_renewal, category, status, now, now, source_provider, now, now),
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
                         short_evidence: str | None = None) -> str | None:
    """Insert an email record. Returns None if source_message_id already exists (dedup)."""
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
            billing_period_end, short_evidence, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (record_id, subscription_id, source_message_id, source_provider,
         source_account_id, source_account_email, sender_address, sender_name,
         subject, email_date, amount_extracted, currency_extracted,
         confidence_score, disposition, event_type, billing_period_start,
         billing_period_end, short_evidence, now),
    )
    return record_id


def get_email_records(
    conn: sqlite3.Connection,
    disposition: str | None = None,
    account_id: str | None = None,
    source_provider: str | None = None,
) -> list[sqlite3.Row]:
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

    return {
        "total_monthly_cost": round(top_total or 0.0, 2),
        "currency": top_currency,
        "active_count": active["cnt"],
        "detected_count": detected_count,
        "flagged_count": flagged_count,
        "has_mock_data": has_mock_data,
        "monthly_costs_by_currency": monthly_costs_by_currency,
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
) -> None:
    """Insert a payment event. INSERT OR IGNORE on event_id — safe for re-scans.

    Privacy: stores NO raw email content. merchant_name is the canonical name from
    sender_list.py (e.g. 'Spotify'), never the raw sender address or email subject.
    """
    conn.execute(
        """INSERT OR IGNORE INTO payment_events
           (event_id, source_message_id, source_provider, source_account_id,
            event_type, amount, currency, merchant_name, event_date,
            is_recurring_candidate, is_one_time_candidate,
            subscription_id, confidence_score)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (event_id, source_message_id, source_provider, source_account_id,
         event_type, amount, currency, merchant_name, event_date,
         is_recurring_candidate, is_one_time_candidate,
         subscription_id, confidence_score),
    )


def get_payment_events(
    conn: sqlite3.Connection,
    source_message_id: str | None = None,
    merchant_name: str | None = None,
    subscription_id: str | None = None,
    event_type: str | None = None,
) -> list[sqlite3.Row]:
    """Return payment events, optionally filtered by one or more fields."""
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
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return conn.execute(
        f"SELECT * FROM payment_events {where} ORDER BY event_date DESC",
        params,
    ).fetchall()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
