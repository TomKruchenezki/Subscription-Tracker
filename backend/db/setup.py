import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _migrations_sql() -> str:
    sql_file = _MIGRATIONS_DIR / "001_initial_schema.sql"
    return sql_file.read_text(encoding="utf-8")


def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(db_path: str) -> None:
    conn = get_connection(db_path)
    try:
        conn.executescript(_migrations_sql())
        conn.commit()
    finally:
        conn.close()


# ── Subscriptions ────────────────────────────────────────────────────────────

def upsert_subscription(conn: sqlite3.Connection, *, name: str, amount: float | None,
                         currency: str, billing_cycle: str, category: str,
                         status: str, source_provider: str, service_url: str | None = None,
                         next_renewal: str | None = None) -> str:
    """Insert or update a subscription by canonical name. Returns subscription_id."""
    now = _now()
    row = conn.execute(
        "SELECT subscription_id FROM subscriptions WHERE name = ?", (name,)
    ).fetchone()

    if row:
        sub_id = row["subscription_id"]
        conn.execute(
            """UPDATE subscriptions
               SET amount = COALESCE(?, amount),
                   currency = ?,
                   billing_cycle = CASE WHEN ? != 'UNKNOWN' THEN ? ELSE billing_cycle END,
                   category = ?,
                   status = ?,
                   last_seen = ?,
                   updated_at = ?
               WHERE subscription_id = ?""",
            (amount, currency, billing_cycle, billing_cycle, category, status, now, now, sub_id),
        )
    else:
        sub_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO subscriptions
               (subscription_id, name, service_url, amount, currency, billing_cycle,
                next_renewal, category, status, first_seen, last_seen, source_provider,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (sub_id, name, service_url, amount, currency, billing_cycle,
             next_renewal, category, status, now, now, source_provider, now, now),
        )
    return sub_id


def update_subscription_status(conn: sqlite3.Connection, name: str, status: str) -> None:
    now = _now()
    conn.execute(
        "UPDATE subscriptions SET status = ?, updated_at = ? WHERE name = ?",
        (status, now, name),
    )


def get_subscriptions(conn: sqlite3.Connection, status: str | None = None) -> list[sqlite3.Row]:
    if status:
        return conn.execute(
            "SELECT * FROM subscriptions WHERE status = ? ORDER BY name", (status,)
        ).fetchall()
    return conn.execute("SELECT * FROM subscriptions ORDER BY name").fetchall()


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
                         disposition: str) -> str | None:
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
            confidence_score, disposition, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (record_id, subscription_id, source_message_id, source_provider,
         source_account_id, source_account_email, sender_address, sender_name,
         subject, email_date, amount_extracted, currency_extracted,
         confidence_score, disposition, now),
    )
    return record_id


def get_email_records(conn: sqlite3.Connection, disposition: str | None = None,
                       account_id: str | None = None) -> list[sqlite3.Row]:
    conditions = []
    params: list = []
    if disposition:
        conditions.append("disposition = ?")
        params.append(disposition)
    if account_id:
        conditions.append("source_account_id = ?")
        params.append(account_id)
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

def get_summary(conn: sqlite3.Connection) -> dict:
    active = conn.execute(
        "SELECT COUNT(*) as cnt, SUM(CASE WHEN billing_cycle='ANNUAL' THEN amount/12.0 ELSE amount END) as monthly "
        "FROM subscriptions WHERE status = 'ACTIVE' AND amount IS NOT NULL"
    ).fetchone()

    flagged_count = conn.execute(
        "SELECT COUNT(*) as cnt FROM email_records WHERE disposition = 'FLAGGED'"
    ).fetchone()["cnt"]

    detected_count = conn.execute(
        "SELECT COUNT(*) as cnt FROM email_records WHERE disposition = 'DETECTED'"
    ).fetchone()["cnt"]

    return {
        "total_monthly_cost": round(active["monthly"] or 0.0, 2),
        "currency": "USD",
        "active_count": active["cnt"],
        "detected_count": detected_count,
        "flagged_count": flagged_count,
    }


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
