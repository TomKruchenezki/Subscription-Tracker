"""
Unit tests for Phase 2.5A: scan_jobs CRUD, body-fetch triage, and batch dedup.

These tests use the same db_path fixture as other unit tests (in-memory SQLite
with all migrations applied). They do NOT make live Gmail API calls.
"""
import sqlite3
import pytest

from backend.db.setup import (
    create_scan_job,
    get_scan_job,
    get_running_scan_jobs,
    update_scan_job,
    get_connection,
)
from backend.models.email_metadata import EmailMetadata
from datetime import datetime, timezone


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_email(message_id: str, sender: str, subject: str) -> EmailMetadata:
    return EmailMetadata(
        source_message_id=message_id,
        source_provider="GMAIL",
        source_account_id="test_account",
        source_account_email="test@example.com",
        sender_address=sender,
        sender_name=None,
        subject=subject,
        email_date=datetime.now(timezone.utc),
    )


@pytest.fixture
def conn(db_path):
    c = get_connection(db_path)
    yield c
    c.close()


# ── CRUD tests ────────────────────────────────────────────────────────────────

def test_create_and_get_scan_job(conn):
    """Create a scan job, then read it back — all fields correct, status=pending."""
    create_scan_job(
        conn,
        scan_id="test-scan-001",
        account_id="user@gmail.com",
        mode="forensic",
        scan_range="1y",
        content_access_level="body_text_ephemeral",
    )
    conn.commit()

    row = get_scan_job(conn, "test-scan-001")
    assert row is not None
    assert row["scan_id"] == "test-scan-001"
    assert row["account_id"] == "user@gmail.com"
    assert row["mode"] == "forensic"
    assert row["scan_range"] == "1y"
    assert row["content_access_level"] == "body_text_ephemeral"
    assert row["status"] == "pending"
    assert row["processed_count"] == 0
    assert row["detected_count"] == 0
    assert row["total_ids"] == 0
    assert row["created_at"] is not None
    assert row["last_activity_at"] is not None


def test_get_scan_job_not_found(conn):
    """get_scan_job returns None for unknown scan_id."""
    result = get_scan_job(conn, "nonexistent-id")
    assert result is None


def test_update_scan_job_progress(conn):
    """update_scan_job persists progress fields; last_activity_at is always set."""
    create_scan_job(
        conn,
        scan_id="test-scan-002",
        account_id="user@gmail.com",
        mode="forensic",
        scan_range="3m",
        content_access_level="body_text_ephemeral",
    )
    conn.commit()

    update_scan_job(conn, "test-scan-002", status="processing", processed_count=50,
                    detected_count=3, flagged_count=10, ignored_count=37)
    conn.commit()

    row = get_scan_job(conn, "test-scan-002")
    assert row["status"] == "processing"
    assert row["processed_count"] == 50
    assert row["detected_count"] == 3
    assert row["flagged_count"] == 10
    assert row["ignored_count"] == 37
    assert row["last_activity_at"] is not None


def test_scan_job_status_transitions(conn):
    """Verify full status lifecycle: pending → collecting → processing → completed."""
    create_scan_job(
        conn, scan_id="test-scan-003", account_id="u@g.com",
        mode="forensic", scan_range="1y", content_access_level="body_text_ephemeral",
    )
    conn.commit()
    assert get_scan_job(conn, "test-scan-003")["status"] == "pending"

    update_scan_job(conn, "test-scan-003", status="collecting", started_at="2026-05-27T10:00:00Z")
    conn.commit()
    assert get_scan_job(conn, "test-scan-003")["status"] == "collecting"

    update_scan_job(conn, "test-scan-003", status="processing", total_ids=100)
    conn.commit()
    assert get_scan_job(conn, "test-scan-003")["status"] == "processing"

    update_scan_job(conn, "test-scan-003", status="completed",
                    completed_at="2026-05-27T10:05:00Z", processed_count=100)
    conn.commit()
    row = get_scan_job(conn, "test-scan-003")
    assert row["status"] == "completed"
    assert row["completed_at"] is not None
    assert row["processed_count"] == 100


def test_startup_marks_interrupted_jobs(conn, db_path):
    """Jobs with status collecting/processing at startup become interrupted."""
    from backend.api.routers.scan_async import mark_interrupted_jobs

    for i, status in enumerate(["collecting", "processing"]):
        create_scan_job(
            conn, scan_id=f"job-{i}", account_id="u@g.com",
            mode="forensic", scan_range="1y", content_access_level="body_text_ephemeral",
        )
        conn.commit()
        update_scan_job(conn, f"job-{i}", status=status)
        conn.commit()

    # Simulate server restart
    conn.close()
    mark_interrupted_jobs(db_path)

    conn2 = get_connection(db_path)
    try:
        running = get_running_scan_jobs(conn2)
        assert len(running) == 0, "No jobs should remain in running state after interrupt recovery"

        for i in range(2):
            row = get_scan_job(conn2, f"job-{i}")
            assert row["status"] == "interrupted"
            assert row["error_message"] is not None
    finally:
        conn2.close()


def test_get_running_scan_jobs(conn):
    """get_running_scan_jobs returns only pending/collecting/processing jobs."""
    for scan_id, status in [
        ("running-1", "pending"),
        ("running-2", "collecting"),
        ("running-3", "processing"),
        ("done-1", "completed"),
        ("done-2", "failed"),
        ("done-3", "interrupted"),
    ]:
        create_scan_job(
            conn, scan_id=scan_id, account_id="u@g.com",
            mode="forensic", scan_range="1y", content_access_level="body_text_ephemeral",
        )
        conn.commit()
        if status != "pending":
            update_scan_job(conn, scan_id, status=status)
            conn.commit()

    running = get_running_scan_jobs(conn)
    running_ids = {r["scan_id"] for r in running}
    assert running_ids == {"running-1", "running-2", "running-3"}


# ── Body-fetch triage tests ───────────────────────────────────────────────────

def test_body_triage_skips_notification(tmp_path):
    """NOTIFICATION subject on Tier 1 sender → _should_fetch_body returns False."""
    from backend.sources.gmail import _should_fetch_body

    email = _make_email("x1", "info@linkedin.com",
                        "You appeared in 3 searches this week")
    assert _should_fetch_body(email) is False, (
        "NOTIFICATION subject should skip body fetch"
    )


def test_body_triage_skips_excluded_domain(tmp_path):
    """Excluded domain (amazon.com, tier=-1) → _should_fetch_body returns False."""
    from backend.sources.gmail import _should_fetch_body

    email = _make_email("x2", "no-reply@amazon.com", "Your Amazon.com order receipt - $29.99")
    assert _should_fetch_body(email) is False, (
        "Excluded domain should skip body fetch (scores 0 regardless)"
    )


def test_body_triage_skips_promo_tier0(tmp_path):
    """PROMOTIONAL subject + Tier 0 (unknown) sender → returns False."""
    from backend.sources.gmail import _should_fetch_body

    email = _make_email("x3", "deals@unknownstore.xyz", "50% off your first month today only")
    assert _should_fetch_body(email) is False, (
        "PROMOTIONAL + Tier0 sender should skip body fetch"
    )


def test_body_triage_fetches_for_tier1_none_pattern(tmp_path):
    """Tier 1 sender + generic subject (PatternType.NONE) → returns True (uncertain)."""
    from backend.sources.gmail import _should_fetch_body

    email = _make_email("x4", "no-reply@netflix.com", "Your account information")
    assert _should_fetch_body(email) is True, (
        "Tier1 sender + NONE pattern must fetch body (uncertain — could be billing)"
    )


def test_body_triage_fetches_for_receipt_pattern(tmp_path):
    """Any Tier 0 sender + RECEIPT subject → returns True."""
    from backend.sources.gmail import _should_fetch_body

    email = _make_email("x5", "billing@unknownservice.io", "Your receipt for $29.00")
    assert _should_fetch_body(email) is True, (
        "RECEIPT pattern must always fetch body regardless of tier"
    )


def test_body_triage_fetches_for_tier2(tmp_path):
    """Tier 2 (payment processor like stripe.com) + NONE subject → returns True."""
    from backend.sources.gmail import _should_fetch_body

    email = _make_email("x6", "receipts@stripe.com", "Payment processed for your account")
    assert _should_fetch_body(email) is True, (
        "Tier2 sender must fetch body (payment processor — could be subscription billing)"
    )


def test_body_triage_notification_beats_tier1(tmp_path):
    """NOTIFICATION subject wins over Tier 1 domain — still skip."""
    from backend.sources.gmail import _should_fetch_body

    email = _make_email("x7", "no-reply@spotify.com", "New device sign-in detected")
    assert _should_fetch_body(email) is False, (
        "NOTIFICATION pattern should skip even on Tier1 sender"
    )


def test_body_triage_promotional_tier1_fetches(tmp_path):
    """PROMOTIONAL from Tier 1 sender → True (could be a renewal offer we want to track)."""
    from backend.sources.gmail import _should_fetch_body

    email = _make_email("x8", "no-reply@netflix.com", "50% off — upgrade your plan today")
    # Tier 1 + PROMOTIONAL → fetch (only skip PROMOTIONAL for Tier 0)
    assert _should_fetch_body(email) is True, (
        "PROMOTIONAL from Tier1 sender should still fetch body"
    )


# ── Batch dedup test ──────────────────────────────────────────────────────────

def test_batch_no_duplicates_on_rerun(conn):
    """Processing the same 3 emails twice must yield email_records count=3 (not 6)."""
    from backend.detector.detector import process_email

    emails = [
        _make_email("dedup-001", "billing@account.netflix.com",
                    "Your Netflix membership receipt - $15.49"),
        _make_email("dedup-002", "no-reply@spotify.com",
                    "Your Spotify Premium receipt - $9.99"),
        _make_email("dedup-003", "billing@account.netflix.com",
                    "Your Netflix subscription has been cancelled"),
    ]

    # First pass
    for email in emails:
        process_email(conn, email)
    conn.commit()

    # Second pass — same source_message_ids
    for email in emails:
        process_email(conn, email)
    conn.commit()

    records = conn.execute("SELECT COUNT(*) FROM email_records").fetchone()[0]
    assert records == 3, (
        f"Expected 3 email_records after reprocessing same emails, got {records}"
    )
