"""Schema and CRUD constraint tests using the in-memory db_path fixture."""
import sqlite3
import pytest
from backend.db.setup import (
    get_connection, upsert_subscription, insert_email_record,
    get_subscriptions, get_subscription_by_id, get_email_records,
    update_subscription_lifecycle, init_db, create_scan_job,
)


@pytest.fixture
def conn(db_path):
    c = get_connection(db_path)
    yield c
    c.close()


def test_init_db_is_idempotent(tmp_path):
    """Calling init_db twice on the same path must not raise.

    This guards against ALTER TABLE migrations that fail with
    'duplicate column name' when the DB already has those columns.
    """
    from backend.db.setup import init_db
    db = str(tmp_path / "idempotent.db")
    init_db(db)
    init_db(db)   # must not raise OperationalError


def test_schema_version_exists(conn):
    row = conn.execute("SELECT COUNT(*) as cnt FROM schema_version").fetchone()
    assert row["cnt"] >= 1


def test_valid_disposition_constraint(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO email_records (record_id, source_message_id, source_provider, "
            "source_account_id, source_account_email, sender_address, "
            "subject, email_date, confidence_score, disposition) "
            "VALUES ('r1', 's1', 'MOCK', 'mock_default', 'demo@mock.local', "
            "'a@b.com', 'Test', '2025-01-01T00:00:00Z', 0.5, 'INVALID')"
        )
        conn.commit()


def test_subject_length_constraint(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO email_records (record_id, source_message_id, source_provider, "
            "source_account_id, source_account_email, sender_address, "
            "subject, email_date, confidence_score, disposition) "
            "VALUES ('r2', 's2', 'MOCK', 'mock_default', 'demo@mock.local', "
            "'a@b.com', ?, '2025-01-01T00:00:00Z', 0.5, 'DETECTED')",
            ("x" * 501,),
        )
        conn.commit()


def test_valid_confidence_constraint(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO email_records (record_id, source_message_id, source_provider, "
            "source_account_id, source_account_email, sender_address, "
            "subject, email_date, confidence_score, disposition) "
            "VALUES ('r3', 's3', 'MOCK', 'mock_default', 'demo@mock.local', "
            "'a@b.com', 'Test', '2025-01-01T00:00:00Z', 1.5, 'DETECTED')"
        )
        conn.commit()


def test_cascade_delete(conn):
    sub_id, _ = upsert_subscription(
        conn, name="TestService", amount=9.99, currency="USD",
        billing_cycle="MONTHLY", category="SAAS", status="ACTIVE", source_provider="MOCK",
    )
    conn.commit()
    insert_email_record(
        conn, source_message_id="sm1", source_provider="MOCK",
        source_account_id="mock_default", source_account_email="demo@mock.local",
        subscription_id=sub_id, sender_address="a@b.com", sender_name=None,
        subject="Test receipt", email_date="2025-01-01T00:00:00Z",
        amount_extracted=9.99, currency_extracted="USD",
        confidence_score=0.9, disposition="DETECTED",
    )
    conn.commit()

    records_before = get_email_records(conn)
    assert len(records_before) == 1

    conn.execute("DELETE FROM subscriptions WHERE subscription_id = ?", (sub_id,))
    conn.commit()

    records_after = get_email_records(conn)
    assert len(records_after) == 0, "email_records must CASCADE DELETE with subscription"


def test_upsert_subscription_idempotent(conn):
    upsert_subscription(
        conn, name="Netflix", amount=15.49, currency="USD",
        billing_cycle="MONTHLY", category="STREAMING", status="ACTIVE", source_provider="MOCK",
    )
    conn.commit()
    upsert_subscription(
        conn, name="Netflix", amount=17.99, currency="USD",
        billing_cycle="MONTHLY", category="STREAMING", status="ACTIVE", source_provider="MOCK",
    )
    conn.commit()

    subs = get_subscriptions(conn)
    netflix = [s for s in subs if s["name"] == "Netflix"]
    assert len(netflix) == 1, "Upserting same name must not create duplicate subscription"


def test_dedup_email_record(conn):
    sub_id, _ = upsert_subscription(
        conn, name="Spotify", amount=9.99, currency="USD",
        billing_cycle="MONTHLY", category="STREAMING", status="ACTIVE", source_provider="MOCK",
    )
    conn.commit()
    first = insert_email_record(
        conn, source_message_id="spotify_001", source_provider="MOCK",
        source_account_id="mock_default", source_account_email="demo@mock.local",
        subscription_id=sub_id, sender_address="a@b.com", sender_name=None,
        subject="Spotify receipt", email_date="2025-01-01T00:00:00Z",
        amount_extracted=9.99, currency_extracted="USD",
        confidence_score=0.9, disposition="DETECTED",
    )
    conn.commit()
    second = insert_email_record(
        conn, source_message_id="spotify_001", source_provider="MOCK",
        source_account_id="mock_default", source_account_email="demo@mock.local",
        subscription_id=sub_id, sender_address="a@b.com", sender_name=None,
        subject="Spotify receipt", email_date="2025-01-01T00:00:00Z",
        amount_extracted=9.99, currency_extracted="USD",
        confidence_score=0.9, disposition="DETECTED",
    )
    conn.commit()
    assert first is not None
    assert second is None, "Duplicate source_message_id must return None (dedup)"
    assert len(get_email_records(conn)) == 1


# ---------------------------------------------------------------------------
# Phase 1.2: lifecycle column tests
# ---------------------------------------------------------------------------

def test_upsert_subscription_returns_was_created(conn):
    """First call returns (id, True); second call same name returns (same_id, False)."""
    sub_id_1, was_created_1 = upsert_subscription(
        conn, name="Linear", amount=96.00, currency="USD",
        billing_cycle="ANNUAL", category="SAAS", status="ACTIVE", source_provider="MOCK",
    )
    conn.commit()
    sub_id_2, was_created_2 = upsert_subscription(
        conn, name="Linear", amount=96.00, currency="USD",
        billing_cycle="ANNUAL", category="SAAS", status="ACTIVE", source_provider="MOCK",
    )
    conn.commit()
    assert was_created_1 is True
    assert was_created_2 is False
    assert sub_id_1 == sub_id_2, "Upsert must return the same subscription_id on second call"


def test_lifecycle_columns_are_null_by_default(conn):
    """All 4 lifecycle timestamps must be NULL immediately after upsert."""
    sub_id, _ = upsert_subscription(
        conn, name="Vercel", amount=20.00, currency="USD",
        billing_cycle="MONTHLY", category="CLOUD", status="ACTIVE", source_provider="MOCK",
    )
    conn.commit()
    row = conn.execute(
        "SELECT first_charge_date, last_charge_date, cancelled_at, trial_ends_at "
        "FROM subscriptions WHERE subscription_id = ?",
        (sub_id,),
    ).fetchone()
    assert row["first_charge_date"] is None
    assert row["last_charge_date"] is None
    assert row["cancelled_at"] is None
    assert row["trial_ends_at"] is None


def test_update_subscription_lifecycle_first_charge(conn):
    """first_charge_date uses MIN semantics (earliest wins); last_charge_date uses MAX semantics (latest wins)."""
    sub_id, _ = upsert_subscription(
        conn, name="Dropbox", amount=11.99, currency="USD",
        billing_cycle="MONTHLY", category="CLOUD", status="ACTIVE", source_provider="MOCK",
    )
    conn.commit()

    update_subscription_lifecycle(
        conn, sub_id,
        first_charge_date="2025-01-01T00:00:00Z",
        last_charge_date="2025-01-01T00:00:00Z",
    )
    conn.commit()
    # Second call: first_charge_date should NOT change (COALESCE), last_charge_date should
    update_subscription_lifecycle(
        conn, sub_id,
        first_charge_date="2025-02-01T00:00:00Z",
        last_charge_date="2025-02-01T00:00:00Z",
    )
    conn.commit()

    row = conn.execute(
        "SELECT first_charge_date, last_charge_date FROM subscriptions WHERE subscription_id = ?",
        (sub_id,),
    ).fetchone()
    assert row["first_charge_date"] == "2025-01-01T00:00:00Z", "first_charge_date must not be overwritten"
    assert row["last_charge_date"] == "2025-02-01T00:00:00Z", "last_charge_date must be updated to latest"


def test_first_charge_date_min_semantics(conn):
    """When newer date is processed first (Gmail newest-first order), MIN semantics
    must still record the oldest date as first_charge_date and newest as last_charge_date."""
    sub_id, _ = upsert_subscription(
        conn, name="MinMaxService", amount=9.99, currency="USD",
        billing_cycle="MONTHLY", category="SAAS", status="ACTIVE", source_provider="MOCK",
    )
    conn.commit()

    # Simulate Gmail newest-first: May 22 processed before March 20
    update_subscription_lifecycle(
        conn, sub_id,
        first_charge_date="2026-05-22T10:00:00Z",
        last_charge_date="2026-05-22T10:00:00Z",
    )
    conn.commit()
    update_subscription_lifecycle(
        conn, sub_id,
        first_charge_date="2026-03-20T10:00:00Z",
        last_charge_date="2026-03-20T10:00:00Z",
    )
    conn.commit()

    row = conn.execute(
        "SELECT first_charge_date, last_charge_date FROM subscriptions WHERE subscription_id = ?",
        (sub_id,),
    ).fetchone()
    # MIN: March 20 is earlier → first_charge_date must be March 20
    assert row["first_charge_date"].startswith("2026-03-20"), (
        f"first_charge_date should be 2026-03-20 (MIN), got {row['first_charge_date']}"
    )
    # MAX: May 22 is later → last_charge_date must be May 22
    assert row["last_charge_date"].startswith("2026-05-22"), (
        f"last_charge_date should be 2026-05-22 (MAX), got {row['last_charge_date']}"
    )


def test_last_charge_date_not_overwritten_by_older(conn):
    """last_charge_date uses MAX semantics: an older date must NOT overwrite a newer one."""
    sub_id, _ = upsert_subscription(
        conn, name="MaxService", amount=15.00, currency="USD",
        billing_cycle="MONTHLY", category="SAAS", status="ACTIVE", source_provider="MOCK",
    )
    conn.commit()

    # Set last_charge_date to May 22 (recent)
    update_subscription_lifecycle(conn, sub_id, last_charge_date="2026-05-22T10:00:00Z")
    conn.commit()
    # Then process an older email (March 20) — must NOT overwrite
    update_subscription_lifecycle(conn, sub_id, last_charge_date="2026-03-20T10:00:00Z")
    conn.commit()

    row = conn.execute(
        "SELECT last_charge_date FROM subscriptions WHERE subscription_id = ?",
        (sub_id,),
    ).fetchone()
    assert row["last_charge_date"].startswith("2026-05-22"), (
        f"last_charge_date should remain 2026-05-22 (MAX), got {row['last_charge_date']}"
    )


def test_lifecycle_dates_idempotent_same_value(conn):
    """Calling update_subscription_lifecycle with the same date twice must be stable."""
    sub_id, _ = upsert_subscription(
        conn, name="IdempotentService", amount=5.00, currency="USD",
        billing_cycle="MONTHLY", category="SAAS", status="ACTIVE", source_provider="MOCK",
    )
    conn.commit()

    date = "2026-04-15T08:00:00Z"
    update_subscription_lifecycle(conn, sub_id, first_charge_date=date, last_charge_date=date)
    conn.commit()
    update_subscription_lifecycle(conn, sub_id, first_charge_date=date, last_charge_date=date)
    conn.commit()

    row = conn.execute(
        "SELECT first_charge_date, last_charge_date FROM subscriptions WHERE subscription_id = ?",
        (sub_id,),
    ).fetchone()
    assert row["first_charge_date"] == date, "first_charge_date must be stable after same-value update"
    assert row["last_charge_date"] == date, "last_charge_date must be stable after same-value update"


def test_email_record_stores_event_type(conn):
    """event_type and short_evidence round-trip through insert_email_record → get_email_records."""
    sub_id, _ = upsert_subscription(
        conn, name="Spotify", amount=9.99, currency="USD",
        billing_cycle="MONTHLY", category="STREAMING", status="ACTIVE", source_provider="MOCK",
    )
    conn.commit()
    insert_email_record(
        conn,
        source_message_id="ev_001",
        source_provider="MOCK",
        source_account_id="mock_default",
        source_account_email="demo@mock.local",
        subscription_id=sub_id,
        sender_address="no-reply@spotify.com",
        sender_name="Spotify",
        subject="Spotify renewal receipt",
        email_date="2025-03-01T00:00:00Z",
        amount_extracted=9.99,
        currency_extracted="USD",
        confidence_score=0.9,
        disposition="DETECTED",
        event_type="renewal_charge",
        short_evidence="Renewal: USD 9.99/monthly from Spotify",
    )
    conn.commit()

    records = get_email_records(conn)
    assert len(records) == 1
    assert records[0]["event_type"] == "renewal_charge"
    assert records[0]["short_evidence"] == "Renewal: USD 9.99/monthly from Spotify"


# ---------------------------------------------------------------------------
# Phase 2.5A-hotfix: init_db() migration version regression tests
#
# These tests call init_db() directly (NOT the conftest db_path fixture) so they
# catch the exact bug class where a migration is silently skipped due to a
# duplicate schema_version number.  The conftest fixture bypasses version checks.
# ---------------------------------------------------------------------------

def test_init_db_creates_scan_jobs_fresh_db(tmp_path):
    """On a brand-new DB file, init_db() must create the scan_jobs table."""
    db = str(tmp_path / "fresh.db")
    init_db(db)
    conn = get_connection(db)
    try:
        tables = {
            r[0] for r in
            conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "scan_jobs" in tables, (
            "init_db() must create scan_jobs on a fresh DB — "
            "check that 003_scan_jobs.sql declares a unique schema_version number"
        )
    finally:
        conn.close()


def test_init_db_creates_scan_jobs_idempotent(tmp_path):
    """Calling init_db() twice on the same DB must not raise and scan_jobs must still exist."""
    db = str(tmp_path / "idem.db")
    init_db(db)
    init_db(db)   # must not raise OperationalError
    conn = get_connection(db)
    try:
        tables = {
            r[0] for r in
            conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "scan_jobs" in tables, "scan_jobs must still exist after calling init_db() twice"
    finally:
        conn.close()


def test_scan_jobs_schema_version_is_4(tmp_path):
    """After init_db(), schema_version must contain version=4 (003_scan_jobs.sql)."""
    db = str(tmp_path / "ver.db")
    init_db(db)
    conn = get_connection(db)
    try:
        row = conn.execute(
            "SELECT 1 FROM schema_version WHERE version = 4"
        ).fetchone()
        assert row is not None, (
            "schema_version must contain version=4 after applying 003_scan_jobs.sql. "
            "If version=3 is used instead, 003 collides with 002_lifecycle.sql "
            "and init_db() skips it."
        )
    finally:
        conn.close()


def test_create_scan_job_after_init_db(tmp_path):
    """create_scan_job() must succeed on a fresh DB initialised with init_db()."""
    db = str(tmp_path / "create.db")
    init_db(db)
    conn = get_connection(db)
    try:
        # Must not raise OperationalError: no such table: scan_jobs
        create_scan_job(
            conn,
            scan_id="hotfix-test-001",
            account_id="user@gmail.com",
            mode="forensic",
            scan_range="1y",
            content_access_level="body_text_ephemeral",
        )
        conn.commit()
        row = conn.execute(
            "SELECT scan_id FROM scan_jobs WHERE scan_id = 'hotfix-test-001'"
        ).fetchone()
        assert row is not None, "create_scan_job must persist the new row to scan_jobs"
    finally:
        conn.close()
