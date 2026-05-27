"""
Unit tests for scripts/cleanup_mock_rows.py.

All tests use a real SQLite file in tmp_path (not the conftest db_path fixture)
so they can verify deletion without affecting the shared test DB.
"""
import sqlite3
import sys
import uuid
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_db(tmp_path: Path) -> Path:
    """Create a minimal subscriptions.db with the required tables."""
    db_path = tmp_path / "subscriptions.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE subscriptions (
            subscription_id TEXT PRIMARY KEY,
            name TEXT,
            amount REAL,
            currency TEXT,
            billing_cycle TEXT,
            category TEXT,
            status TEXT,
            source_provider TEXT,
            first_seen TEXT,
            last_seen TEXT,
            created_at TEXT,
            updated_at TEXT,
            service_url TEXT,
            next_renewal TEXT
        );
        CREATE TABLE email_records (
            record_id TEXT PRIMARY KEY,
            subscription_id TEXT REFERENCES subscriptions(subscription_id) ON DELETE CASCADE,
            source_message_id TEXT UNIQUE,
            source_provider TEXT,
            source_account_id TEXT,
            source_account_email TEXT,
            sender_address TEXT,
            sender_name TEXT,
            subject TEXT,
            email_date TEXT,
            amount_extracted REAL,
            currency_extracted TEXT,
            confidence_score REAL,
            disposition TEXT,
            created_at TEXT,
            event_type TEXT,
            billing_period_start TEXT,
            billing_period_end TEXT,
            short_evidence TEXT
        );
    """)
    conn.commit()
    conn.close()
    return db_path


def _insert_row(conn, provider: str, name: str, amount: float) -> None:
    now = "2026-01-01T00:00:00Z"
    sub_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO subscriptions
           (subscription_id, name, amount, currency, billing_cycle, category,
            status, source_provider, first_seen, last_seen, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (sub_id, name, amount, "USD", "MONTHLY", "SAAS",
         "ACTIVE", provider, now, now, now, now),
    )
    conn.execute(
        """INSERT INTO email_records
           (record_id, subscription_id, source_message_id, source_provider,
            source_account_id, source_account_email, sender_address,
            subject, email_date, confidence_score, disposition, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (str(uuid.uuid4()), sub_id, f"msg-{provider}-{name}", provider,
         f"acct_{provider}", f"test@{provider.lower()}.local",
         f"billing@{name.lower()}.com", f"{name} receipt",
         now, 0.9, "DETECTED", now),
    )


def _run_cleanup(db_path: Path, extra_args: list[str] | None = None) -> int:
    """Import and run the cleanup script's main() function. Returns sys.exit code (0 on success)."""
    # Insert the scripts directory into sys.path so the module can be imported
    scripts_dir = str(Path(__file__).parent.parent.parent / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "cleanup_mock_rows",
        Path(__file__).parent.parent.parent / "scripts" / "cleanup_mock_rows.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    args = ["--db", str(db_path), "--yes"] + (extra_args or [])
    import sys as _sys
    old_argv = _sys.argv
    try:
        _sys.argv = ["cleanup_mock_rows.py"] + args
        try:
            mod.main()
            return 0
        except SystemExit as exc:
            return int(exc.code) if exc.code is not None else 0
    finally:
        _sys.argv = old_argv


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_cleanup_deletes_only_mock_rows(tmp_path):
    """Cleanup must delete MOCK rows and leave GMAIL rows completely intact."""
    db_path = _build_db(tmp_path)
    conn = sqlite3.connect(str(db_path))
    _insert_row(conn, "MOCK", "MockSvc", 5.00)
    _insert_row(conn, "GMAIL", "GmailSvc", 20.00)
    conn.commit()
    conn.close()

    exit_code = _run_cleanup(db_path)
    assert exit_code == 0

    conn = sqlite3.connect(str(db_path))
    mock_subs = conn.execute(
        "SELECT COUNT(*) FROM subscriptions WHERE source_provider='MOCK'"
    ).fetchone()[0]
    mock_records = conn.execute(
        "SELECT COUNT(*) FROM email_records WHERE source_provider='MOCK'"
    ).fetchone()[0]
    gmail_subs = conn.execute(
        "SELECT COUNT(*) FROM subscriptions WHERE source_provider='GMAIL'"
    ).fetchone()[0]
    gmail_records = conn.execute(
        "SELECT COUNT(*) FROM email_records WHERE source_provider='GMAIL'"
    ).fetchone()[0]
    conn.close()

    assert mock_subs == 0, "All MOCK subscriptions must be deleted"
    assert mock_records == 0, "All MOCK email_records must be deleted"
    assert gmail_subs == 1, "GMAIL subscriptions must not be touched"
    assert gmail_records == 1, "GMAIL email_records must not be touched"


def test_cleanup_never_deletes_gmail(tmp_path):
    """When only GMAIL rows exist, cleanup must leave them intact and report nothing to delete."""
    db_path = _build_db(tmp_path)
    conn = sqlite3.connect(str(db_path))
    _insert_row(conn, "GMAIL", "GmailOnlySvc", 15.00)
    conn.commit()
    conn.close()

    exit_code = _run_cleanup(db_path)
    assert exit_code == 0

    conn = sqlite3.connect(str(db_path))
    gmail_subs = conn.execute(
        "SELECT COUNT(*) FROM subscriptions WHERE source_provider='GMAIL'"
    ).fetchone()[0]
    gmail_records = conn.execute(
        "SELECT COUNT(*) FROM email_records WHERE source_provider='GMAIL'"
    ).fetchone()[0]
    conn.close()

    assert gmail_subs == 1, "GMAIL subscriptions must be untouched when cleanup has nothing to delete"
    assert gmail_records == 1, "GMAIL email_records must be untouched when cleanup has nothing to delete"


def test_cleanup_idempotent(tmp_path):
    """Running cleanup twice on the same DB must not raise and final counts must match first run."""
    db_path = _build_db(tmp_path)
    conn = sqlite3.connect(str(db_path))
    _insert_row(conn, "MOCK", "MockSvc2", 5.00)
    _insert_row(conn, "GMAIL", "GmailSvc2", 20.00)
    conn.commit()
    conn.close()

    exit_code_1 = _run_cleanup(db_path)
    assert exit_code_1 == 0

    # Second run — nothing to delete
    exit_code_2 = _run_cleanup(db_path)
    assert exit_code_2 == 0

    conn = sqlite3.connect(str(db_path))
    mock_count = conn.execute(
        "SELECT COUNT(*) FROM subscriptions WHERE source_provider='MOCK'"
    ).fetchone()[0]
    gmail_count = conn.execute(
        "SELECT COUNT(*) FROM subscriptions WHERE source_provider='GMAIL'"
    ).fetchone()[0]
    conn.close()

    assert mock_count == 0, "No MOCK rows should remain after first run"
    assert gmail_count == 1, "GMAIL rows must still be intact after second run"
