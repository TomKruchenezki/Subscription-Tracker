"""Schema and CRUD constraint tests using the in-memory db_path fixture."""
import sqlite3
import pytest
from backend.db.setup import (
    get_connection, upsert_subscription, insert_email_record,
    get_subscriptions, get_subscription_by_id, get_email_records,
    update_subscription_lifecycle, get_summary, init_db, create_scan_job,
    insert_payment_event, get_payment_events,
    # Phase 3.5
    dismiss_email_record, get_dismissed_email_ids, insert_user_correction,
    get_user_corrections, get_all_active_gmail_accounts,
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


# ---------------------------------------------------------------------------
# Phase 2.6: source_provider filtering in DB layer
# ---------------------------------------------------------------------------

def _insert_sub_and_record(
    conn,
    source_provider: str,
    name: str,
    amount: float,
    disposition: str = "DETECTED",
    subject_suffix: str = "",
) -> str:
    """Helper: insert one subscription + one email_record with the given source_provider."""
    sub_id, _ = upsert_subscription(
        conn, name=name, amount=amount, currency="USD",
        billing_cycle="MONTHLY", category="SAAS", status="ACTIVE",
        source_provider=source_provider,
    )
    conn.commit()
    insert_email_record(
        conn,
        source_message_id=f"msg-{name}-{source_provider}{subject_suffix}",
        source_provider=source_provider,
        source_account_id=f"acct_{source_provider.lower()}",
        source_account_email=f"test@{source_provider.lower()}.local",
        subscription_id=sub_id,
        sender_address=f"billing@{name.lower()}.com",
        sender_name=name,
        subject=f"{name} receipt",
        email_date="2026-01-01T00:00:00Z",
        amount_extracted=amount,
        currency_extracted="USD",
        confidence_score=0.9,
        disposition=disposition,
    )
    conn.commit()
    return sub_id


def test_get_subscriptions_source_provider_gmail(conn):
    """get_subscriptions(source_provider='GMAIL') returns only GMAIL rows."""
    _insert_sub_and_record(conn, "MOCK", "MockSvc", 5.00)
    _insert_sub_and_record(conn, "GMAIL", "GmailSvc", 10.00)

    gmail_subs = get_subscriptions(conn, source_provider="GMAIL")
    assert len(gmail_subs) == 1, f"Expected 1 GMAIL subscription, got {len(gmail_subs)}"
    assert gmail_subs[0]["source_provider"] == "GMAIL"
    assert gmail_subs[0]["name"] == "GmailSvc"


def test_get_subscriptions_source_provider_mock(conn):
    """get_subscriptions(source_provider='MOCK') returns only MOCK rows."""
    _insert_sub_and_record(conn, "MOCK", "MockSvc2", 5.00)
    _insert_sub_and_record(conn, "GMAIL", "GmailSvc2", 10.00)

    mock_subs = get_subscriptions(conn, source_provider="MOCK")
    assert len(mock_subs) == 1, f"Expected 1 MOCK subscription, got {len(mock_subs)}"
    assert mock_subs[0]["source_provider"] == "MOCK"


def test_get_subscriptions_no_filter_returns_all(conn):
    """get_subscriptions() with no source_provider returns both MOCK and GMAIL rows."""
    _insert_sub_and_record(conn, "MOCK", "MockSvc3", 5.00)
    _insert_sub_and_record(conn, "GMAIL", "GmailSvc3", 10.00)

    all_subs = get_subscriptions(conn)
    names = {s["name"] for s in all_subs}
    assert "MockSvc3" in names
    assert "GmailSvc3" in names


def test_get_email_records_source_provider_filter(conn):
    """get_email_records(source_provider='GMAIL') returns only GMAIL email_records."""
    _insert_sub_and_record(conn, "MOCK", "MockSvc4", 5.00)
    _insert_sub_and_record(conn, "GMAIL", "GmailSvc4", 10.00)

    gmail_records = get_email_records(conn, source_provider="GMAIL")
    assert len(gmail_records) == 1, f"Expected 1 GMAIL record, got {len(gmail_records)}"
    assert gmail_records[0]["source_provider"] == "GMAIL"

    all_records = get_email_records(conn)
    assert len(all_records) == 2, "No filter must return both MOCK and GMAIL records"


def test_get_summary_source_provider_gmail_excludes_mock(conn):
    """get_summary(source_provider='GMAIL') counts only GMAIL subscriptions/records.

    Create 1 MOCK ACTIVE sub ($10) and 1 GMAIL ACTIVE sub ($20).
    Gmail-filtered summary must show: active_count=1, total_monthly=$20.
    Unfiltered summary must show: active_count=2, total_monthly=$30.
    """
    _insert_sub_and_record(conn, "MOCK", "MockSvc5", 10.00)
    _insert_sub_and_record(conn, "GMAIL", "GmailSvc5", 20.00)

    gmail_summary = get_summary(conn, source_provider="GMAIL")
    assert gmail_summary["active_count"] == 1, (
        f"Gmail summary should have 1 active sub, got {gmail_summary['active_count']}"
    )
    assert gmail_summary["total_monthly_cost"] == pytest.approx(20.00), (
        f"Gmail summary should cost $20, got {gmail_summary['total_monthly_cost']}"
    )

    unfiltered = get_summary(conn)
    assert unfiltered["active_count"] == 2, (
        f"Unfiltered summary should have 2 active subs, got {unfiltered['active_count']}"
    )
    assert unfiltered["total_monthly_cost"] == pytest.approx(30.00), (
        f"Unfiltered summary should cost $30, got {unfiltered['total_monthly_cost']}"
    )


def test_get_summary_has_mock_data_flag(conn):
    """get_summary(source_provider='GMAIL') sets has_mock_data=True when MOCK rows exist."""
    # Insert both MOCK and GMAIL rows
    _insert_sub_and_record(conn, "MOCK", "MockSvc6", 5.00, subject_suffix="-a")
    _insert_sub_and_record(conn, "GMAIL", "GmailSvc6", 15.00, subject_suffix="-b")

    summary_with_mock = get_summary(conn, source_provider="GMAIL")
    assert summary_with_mock["has_mock_data"] is True, (
        "has_mock_data must be True when MOCK rows exist in DB during Gmail mode"
    )

    # Remove MOCK rows and verify flag clears
    conn.execute("DELETE FROM email_records WHERE source_provider = 'MOCK'")
    conn.execute("DELETE FROM subscriptions WHERE source_provider = 'MOCK'")
    conn.commit()

    summary_clean = get_summary(conn, source_provider="GMAIL")
    assert summary_clean["has_mock_data"] is False, (
        "has_mock_data must be False after all MOCK rows are removed"
    )

    # Unfiltered summary (mock mode) should never report has_mock_data=True
    _insert_sub_and_record(conn, "MOCK", "MockSvc7", 5.00, subject_suffix="-c")
    summary_mock_mode = get_summary(conn, source_provider=None)
    assert summary_mock_mode["has_mock_data"] is False, (
        "has_mock_data must always be False when source_provider is None (mock mode)"
    )


# ---------------------------------------------------------------------------
# Phase 3.0: Migration 005 — QUARTERLY billing_cycle accepted
# ---------------------------------------------------------------------------

def test_quarterly_billing_cycle_accepted(tmp_path):
    """After migration 005, QUARTERLY is a valid billing_cycle value.

    Uses tmp_path + init_db() directly (not the conftest fixture) to ensure
    the fresh DB has had ALL migrations applied including 005_quarterly_cycle.sql.
    The conftest fixture also applies all migrations so conn-based tests would
    work too, but this makes the dependency explicit.
    """
    db = str(tmp_path / "quarterly.db")
    init_db(db)
    c = get_connection(db)
    try:
        sub_id, was_created = upsert_subscription(
            c, name="QuarterlyService", amount=29.99, currency="USD",
            billing_cycle="QUARTERLY",
            category="SAAS", status="ACTIVE", source_provider="MOCK",
        )
        c.commit()
        assert was_created is True, "QuarterlyService should be a new subscription"
        row = c.execute(
            "SELECT billing_cycle FROM subscriptions WHERE subscription_id = ?",
            (sub_id,),
        ).fetchone()
        assert row is not None, "Subscription with QUARTERLY billing_cycle must be persisted"
        assert row["billing_cycle"] == "QUARTERLY", (
            f"Expected billing_cycle='QUARTERLY', got {row['billing_cycle']!r}. "
            "Migration 005 must add QUARTERLY to the valid_billing_cycle CHECK constraint."
        )
    finally:
        c.close()


# ---------------------------------------------------------------------------
# Phase 3.3: payment_events table tests
# ---------------------------------------------------------------------------

def _make_payment_event_kwargs(**overrides):
    """Return a base set of kwargs for insert_payment_event with optional overrides."""
    defaults = dict(
        event_id="pe-test-001",
        source_message_id="msg-test-001",
        source_provider="MOCK",
        source_account_id="mock_default",
        event_type="subscription_charge",
        amount=9.99,
        currency="USD",
        merchant_name="Spotify",
        event_date="2026-01-15T00:00:00Z",
        is_recurring_candidate=1,
        is_one_time_candidate=0,
        subscription_id=None,
        confidence_score=0.85,
    )
    defaults.update(overrides)
    return defaults


def test_insert_payment_event_basic(conn):
    """insert_payment_event stores a row; get_payment_events retrieves it with correct fields."""
    insert_payment_event(conn, **_make_payment_event_kwargs())
    conn.commit()

    events = get_payment_events(conn, source_message_id="msg-test-001")
    assert len(events) == 1, f"Expected 1 payment event, got {len(events)}"
    ev = events[0]
    assert ev["event_id"] == "pe-test-001"
    assert ev["event_type"] == "subscription_charge"
    assert ev["amount"] == pytest.approx(9.99)
    assert ev["currency"] == "USD"
    assert ev["merchant_name"] == "Spotify"
    assert ev["source_message_id"] == "msg-test-001"
    assert ev["is_recurring_candidate"] == 1
    assert ev["is_one_time_candidate"] == 0
    assert ev["confidence_score"] == pytest.approx(0.85)


def test_insert_payment_event_idempotent(conn):
    """INSERT OR IGNORE: inserting the same event_id twice leaves only 1 row."""
    kwargs = _make_payment_event_kwargs()
    insert_payment_event(conn, **kwargs)
    conn.commit()
    insert_payment_event(conn, **kwargs)   # duplicate — must be silently ignored
    conn.commit()

    events = get_payment_events(conn, source_message_id="msg-test-001")
    assert len(events) == 1, (
        f"INSERT OR IGNORE must keep exactly 1 row for duplicate event_id, got {len(events)}"
    )


def test_payment_event_currency_none_stored(conn):
    """currency=None is stored as SQL NULL; merchant_name is still correct."""
    insert_payment_event(conn, **_make_payment_event_kwargs(
        event_id="pe-null-currency",
        source_message_id="msg-null-currency",
        currency=None,
        amount=None,
    ))
    conn.commit()

    events = get_payment_events(conn, source_message_id="msg-null-currency")
    assert len(events) == 1
    ev = events[0]
    assert ev["currency"] is None, (
        f"currency=None must be stored as SQL NULL, got {ev['currency']!r}"
    )
    assert ev["amount"] is None, "amount=None must be stored as SQL NULL"
    assert ev["merchant_name"] == "Spotify"


def test_get_summary_per_currency(conn):
    """get_summary returns monthly_costs_by_currency with per-currency totals.

    1 ACTIVE ILS sub (₪12.90 MONTHLY) + 1 ACTIVE USD sub ($9.99 MONTHLY)
    → monthly_costs_by_currency = {"ILS": 12.90, "USD": 9.99}
    """
    upsert_subscription(
        conn, name="SpotifyILS", amount=12.90, currency="ILS",
        billing_cycle="MONTHLY", category="STREAMING", status="ACTIVE",
        source_provider="MOCK",
    )
    upsert_subscription(
        conn, name="Netflix", amount=9.99, currency="USD",
        billing_cycle="MONTHLY", category="STREAMING", status="ACTIVE",
        source_provider="MOCK",
    )
    conn.commit()

    summary = get_summary(conn)
    costs = summary.get("monthly_costs_by_currency", {})

    assert "ILS" in costs, f"ILS must appear in monthly_costs_by_currency: {costs}"
    assert "USD" in costs, f"USD must appear in monthly_costs_by_currency: {costs}"
    assert costs["ILS"] == pytest.approx(12.90), f"ILS total should be 12.90, got {costs['ILS']}"
    assert costs["USD"] == pytest.approx(9.99), f"USD total should be 9.99, got {costs['USD']}"


def test_upsert_subscription_currency_coalesce(conn):
    """When upsert is called with currency=None on an existing row, the stored currency is preserved.

    Reproduces Bug 2 (ILS→USD overwrite on re-scan): after the COALESCE fix, calling
    upsert_subscription with currency=None must NOT overwrite an existing ILS value.
    """
    # Create subscription with explicit ILS currency
    sub_id, was_created = upsert_subscription(
        conn, name="SpotifyILSCoalesce", amount=12.90, currency="ILS",
        billing_cycle="MONTHLY", category="STREAMING", status="ACTIVE",
        source_provider="MOCK",
    )
    conn.commit()
    assert was_created is True

    # Re-scan: currency not extracted (None) — must NOT overwrite ILS with NULL
    sub_id2, was_created2 = upsert_subscription(
        conn, name="SpotifyILSCoalesce", amount=None, currency=None,
        billing_cycle="MONTHLY", category="STREAMING", status="ACTIVE",
        source_provider="MOCK",
    )
    conn.commit()
    assert was_created2 is False, "Second upsert should return was_created=False"
    assert sub_id == sub_id2, "Same subscription_id must be returned"

    row = conn.execute(
        "SELECT currency FROM subscriptions WHERE subscription_id = ?", (sub_id,)
    ).fetchone()
    assert row["currency"] == "ILS", (
        f"currency must remain 'ILS' after upsert with currency=None, "
        f"got {row['currency']!r}. COALESCE(?, currency) fix must be applied."
    )


# ---------------------------------------------------------------------------
# Phase 3.3B: get_payment_events filter tests + new event type tests
# ---------------------------------------------------------------------------

def test_get_payment_events_filters_by_event_type(conn):
    """get_payment_events(event_type=...) returns only matching events."""
    insert_payment_event(conn, **_make_payment_event_kwargs(
        event_id="pe-filter-001", source_message_id="msg-filter-001",
        event_type="subscription_charge",
    ))
    insert_payment_event(conn, **_make_payment_event_kwargs(
        event_id="pe-filter-002", source_message_id="msg-filter-002",
        event_type="renewal_charge",
    ))
    insert_payment_event(conn, **_make_payment_event_kwargs(
        event_id="pe-filter-003", source_message_id="msg-filter-003",
        event_type="refund",
    ))
    conn.commit()

    renewals = get_payment_events(conn, event_type="renewal_charge")
    assert len(renewals) == 1, f"Filter by event_type='renewal_charge' must return 1 row, got {len(renewals)}"
    assert renewals[0]["event_type"] == "renewal_charge"

    refunds = get_payment_events(conn, event_type="refund")
    assert len(refunds) == 1, f"Filter by event_type='refund' must return 1 row, got {len(refunds)}"


def test_get_payment_events_renewal_charge_stored(conn):
    """'renewal_charge' event_type stores and retrieves correctly (added in migration 007)."""
    insert_payment_event(conn, **_make_payment_event_kwargs(
        event_id="pe-renewal-001",
        source_message_id="msg-renewal-001",
        event_type="renewal_charge",
        amount=15.49,
        currency="USD",
        merchant_name="Netflix",
    ))
    conn.commit()

    events = get_payment_events(conn, source_message_id="msg-renewal-001")
    assert len(events) == 1
    assert events[0]["event_type"] == "renewal_charge", (
        f"'renewal_charge' must be a valid event_type. Got {events[0]['event_type']!r}. "
        f"Migration 007 must add 'renewal_charge' to the CHECK constraint."
    )
    assert events[0]["merchant_name"] == "Netflix"
    assert events[0]["amount"] == pytest.approx(15.49)


def test_get_payment_events_no_raw_content(conn):
    """payment_events rows must not contain any raw email content fields.

    Privacy: the table must have no subject, sender_address, snippet, body_text,
    or body_html columns. This test verifies the returned dict keys.
    """
    insert_payment_event(conn, **_make_payment_event_kwargs())
    conn.commit()

    events = get_payment_events(conn)
    assert len(events) == 1
    ev = dict(events[0])

    forbidden_fields = {"subject", "sender_address", "snippet", "body_text",
                        "body_html", "short_evidence", "raw_body", "payload"}
    present_forbidden = forbidden_fields & set(ev.keys())
    assert not present_forbidden, (
        f"payment_events must not contain raw email content fields. "
        f"Found forbidden fields: {present_forbidden}"
    )


def test_get_payment_events_filter_by_source_provider(conn):
    """get_payment_events(source_provider=...) filters correctly."""
    insert_payment_event(conn, **_make_payment_event_kwargs(
        event_id="pe-gmail-001", source_message_id="msg-gmail-001",
        source_provider="GMAIL",
    ))
    insert_payment_event(conn, **_make_payment_event_kwargs(
        event_id="pe-mock-001", source_message_id="msg-mock-001",
        source_provider="MOCK",
    ))
    conn.commit()

    gmail_events = get_payment_events(conn, source_provider="GMAIL")
    assert len(gmail_events) == 1
    assert gmail_events[0]["source_provider"] == "GMAIL"

    mock_events = get_payment_events(conn, source_provider="MOCK")
    assert len(mock_events) == 1
    assert mock_events[0]["source_provider"] == "MOCK"


def test_get_payment_events_filter_by_recurring(conn):
    """get_payment_events(is_recurring_candidate=1) returns only recurring candidates."""
    insert_payment_event(conn, **_make_payment_event_kwargs(
        event_id="pe-recurring-001", source_message_id="msg-recurring-001",
        is_recurring_candidate=1,
    ))
    insert_payment_event(conn, **_make_payment_event_kwargs(
        event_id="pe-nonrecurring-001", source_message_id="msg-nonrecurring-001",
        is_recurring_candidate=0,
    ))
    conn.commit()

    recurring = get_payment_events(conn, is_recurring_candidate=1)
    assert len(recurring) == 1
    assert recurring[0]["is_recurring_candidate"] == 1


# ── Phase 3.5: User corrections and dismiss ───────────────────────────────────

def _insert_minimal_record(conn, suffix="001", msg_id=None):
    """Insert a minimal email_record for testing. Returns the generated record_id."""
    import uuid as _uuid
    mid = msg_id or f"msg-test-{suffix}"
    # insert_email_record generates its own UUID record_id — capture and return it
    record_id = insert_email_record(
        conn,
        source_message_id=mid,
        source_provider="MOCK",
        source_account_id="mock_default",
        source_account_email="demo@mock.local",
        sender_address="billing@test.com",
        sender_name=None,
        subject="Test receipt",
        email_date="2026-01-01T00:00:00Z",
        amount_extracted=None,
        currency_extracted=None,
        confidence_score=0.75,
        disposition="FLAGGED",
        event_type=None,
        subscription_id=None,
        billing_period_start=None,
        billing_period_end=None,
        short_evidence=None,
    )
    conn.commit()
    assert record_id is not None, f"insert_email_record failed for msg {mid}"
    return record_id


def test_dismiss_email_record_sets_flag(conn):
    """dismiss_email_record() sets user_dismissed=1 on the record."""
    record_id = _insert_minimal_record(conn)
    found = dismiss_email_record(conn, record_id)
    conn.commit()
    assert found is True, "dismiss_email_record must return True for existing record"

    row = conn.execute(
        "SELECT user_dismissed FROM email_records WHERE record_id = ?", (record_id,)
    ).fetchone()
    assert row is not None
    assert row[0] == 1, f"user_dismissed must be 1, got {row[0]}"


def test_dismiss_nonexistent_record_returns_false(conn):
    """dismiss_email_record() returns False for nonexistent record."""
    found = dismiss_email_record(conn, "rec-does-not-exist")
    assert found is False


def test_dismiss_inserts_user_correction(conn):
    """dismiss_email_record() inserts a DISMISSED_EMAIL entry in user_corrections."""
    import sqlite3
    has_table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='user_corrections'"
    ).fetchone()
    if not has_table:
        pytest.skip("user_corrections table not present (migration 009 not applied)")

    record_id = _insert_minimal_record(conn, "corr-rec-001")
    dismiss_email_record(conn, record_id)
    conn.commit()

    row = conn.execute(
        "SELECT correction_type FROM user_corrections WHERE email_record_id = ?",
        (record_id,),
    ).fetchone()
    assert row is not None, "DISMISSED_EMAIL correction must be inserted"
    assert row[0] == "DISMISSED_EMAIL"


def test_get_dismissed_email_ids_returns_set(conn):
    """get_dismissed_email_ids() returns a set of dismissed record_ids."""
    record_id = _insert_minimal_record(conn, "dismiss-set-001")
    dismiss_email_record(conn, record_id)
    conn.commit()

    dismissed = get_dismissed_email_ids(conn)
    assert record_id in dismissed, (
        f"Dismissed record {record_id!r} must be in get_dismissed_email_ids() result"
    )


def test_get_email_records_excludes_dismissed_by_default(conn):
    """get_email_records() excludes user_dismissed=1 records by default."""
    record_id = _insert_minimal_record(conn, "exclude-rec-001")
    dismiss_email_record(conn, record_id)
    conn.commit()

    # Default: excluded
    records = get_email_records(conn)
    assert not any(r["record_id"] == record_id for r in records), (
        "Dismissed record must be excluded from get_email_records() by default"
    )

    # With include_dismissed=True: included
    records_all = get_email_records(conn, include_dismissed=True)
    assert any(r["record_id"] == record_id for r in records_all), (
        "Dismissed record must be included when include_dismissed=True"
    )


def test_get_all_active_gmail_accounts_returns_list(conn):
    """get_all_active_gmail_accounts() returns a list (empty if none connected)."""
    accounts = get_all_active_gmail_accounts(conn)
    assert isinstance(accounts, list), "Must return a list"
    # In mock mode, no accounts connected — list is empty
    assert len(accounts) == 0 or all("account_id" in dict(a) for a in accounts)
