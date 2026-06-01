"""
Tests for scripts/reprocess_email_records.py (Phase 3.5).

Verifies:
- Reprocessing does not duplicate email_records
- Reprocessing deletes and recreates payment_events with current rules
- Dry-run mode makes no DB changes
- Provider filter restricts which records are reprocessed
- Privacy: script uses only stored metadata (no body_text, no external fetch)
"""
import sqlite3
from datetime import datetime, timezone

import pytest

from backend.models.email_metadata import EmailMetadata
from backend.detector.detector import process_email
from backend.db.setup import get_payment_events, get_subscriptions, get_email_records


@pytest.fixture
def conn(db_path):
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    yield c
    c.close()


def _make_email(message_id, sender, subject, date_str="2025-05-01T08:00:00Z"):
    return EmailMetadata(
        source_message_id=message_id,
        source_provider="MOCK",
        source_account_id="mock_default",
        source_account_email="demo@mock.local",
        sender_address=sender,
        sender_name=None,
        subject=subject,
        email_date=datetime.fromisoformat(date_str.replace("Z", "+00:00")),
    )


def test_reprocess_does_not_duplicate_email_records(conn, db_path):
    """After reprocessing, email_records count must remain unchanged."""
    from scripts.reprocess_email_records import reprocess

    # First scan: create one email_record
    email = _make_email("rp-001", "billing@account.netflix.com",
                        "Your Netflix membership receipt - $15.49")
    process_email(conn, email)
    conn.commit()

    count_before = len(get_email_records(conn, include_dismissed=True))
    assert count_before == 1

    # Reprocess
    reprocess(db_path=db_path, dry_run=False)

    count_after = len(get_email_records(conn, include_dismissed=True))
    assert count_after == count_before, (
        f"email_records count must not change during reprocessing: "
        f"before={count_before}, after={count_after}"
    )


def test_reprocess_recreates_payment_events(conn, db_path):
    """After reprocessing, payment_events are deleted and recreated.

    The test verifies that:
    1. A corrupted payment_event is deleted during reprocess
    2. A new payment_event is created by the detector
    3. The new event type is a valid financial event type (not the corrupted value)
    """
    from scripts.reprocess_email_records import reprocess

    # Create a payment_event via first scan
    email = _make_email("rp-002", "billing@account.netflix.com",
                        "Your Netflix membership receipt - $15.49")
    process_email(conn, email)
    conn.commit()

    pe_before = get_payment_events(conn, source_message_id="rp-002")
    assert len(pe_before) == 1
    original_type = pe_before[0]["event_type"]
    assert original_type in ("subscription_charge", "renewal_charge"), (
        f"First scan must produce a financial event type, got {original_type!r}"
    )

    # Manually corrupt to a nonsense value (simulating an old buggy rule)
    conn.execute(
        "UPDATE payment_events SET event_type = 'unknown_payment' WHERE source_message_id = ?",
        ("rp-002",),
    )
    conn.commit()

    # Verify corruption
    pe_corrupted = get_payment_events(conn, source_message_id="rp-002")
    assert pe_corrupted[0]["event_type"] == "unknown_payment"

    # Reprocess: delete corrupted payment_event, recreate with current detector rules
    reprocess(db_path=db_path, dry_run=False)

    pe_after = get_payment_events(conn, source_message_id="rp-002")
    assert len(pe_after) == 1, f"Expected 1 payment_event after reprocess, got {len(pe_after)}"
    # After reprocessing, the event type should be restored (subscription_charge or
    # renewal_charge depending on whether subscription already existed)
    assert pe_after[0]["event_type"] in ("subscription_charge", "renewal_charge"), (
        f"Reprocess must recreate payment_event with a valid financial type, "
        f"got {pe_after[0]['event_type']!r}. "
        f"'unknown_payment' corruption must be removed."
    )


def test_reprocess_dry_run_makes_no_changes(conn, db_path):
    """--dry-run flag: no DB changes should occur."""
    from scripts.reprocess_email_records import reprocess

    email = _make_email("rp-003", "billing@account.netflix.com",
                        "Your Netflix membership receipt - $15.49")
    process_email(conn, email)
    conn.commit()

    # Corrupt payment_event
    conn.execute(
        "UPDATE payment_events SET event_type = 'unknown_payment' WHERE source_message_id = ?",
        ("rp-003",),
    )
    conn.commit()

    # Run dry-run
    reprocess(db_path=db_path, dry_run=True)

    # Corruption must still be present (dry-run made no changes)
    pe_after = get_payment_events(conn, source_message_id="rp-003")
    assert pe_after[0]["event_type"] == "unknown_payment", (
        f"dry-run must not modify payment_events, "
        f"got event_type={pe_after[0]['event_type']!r}"
    )


def test_reprocess_provider_filter(conn, db_path):
    """--provider filter: only matching records are reprocessed."""
    from scripts.reprocess_email_records import reprocess

    # Two different subscriptions
    netflix = _make_email("rp-004-netflix", "billing@account.netflix.com",
                          "Your Netflix membership receipt - $15.49", "2025-01-01T00:00:00Z")
    spotify = _make_email("rp-004-spotify", "billing@spotify.com",
                          "Your Spotify Premium receipt - $9.99", "2025-01-02T00:00:00Z")
    process_email(conn, netflix)
    process_email(conn, spotify)
    conn.commit()

    # Corrupt both payment_events
    conn.execute(
        "UPDATE payment_events SET event_type = 'unknown_payment'"
    )
    conn.commit()

    # Reprocess only Netflix
    reprocess(db_path=db_path, provider_filter="Netflix", dry_run=False)

    # Netflix payment_event should be restored; Spotify should still be corrupted
    pe_netflix = get_payment_events(conn, source_message_id="rp-004-netflix")
    pe_spotify = get_payment_events(conn, source_message_id="rp-004-spotify")

    # Netflix must be restored to a valid financial event type (not unknown_payment)
    assert pe_netflix[0]["event_type"] in ("subscription_charge", "renewal_charge"), (
        f"Netflix payment_event must be restored after reprocess, "
        f"got {pe_netflix[0]['event_type']!r}"
    )
    # Spotify should remain corrupted (provider filter excluded it)
    assert pe_spotify[0]["event_type"] == "unknown_payment", (
        f"Spotify payment_event must NOT be changed by Netflix-only reprocess, "
        f"got {pe_spotify[0]['event_type']!r}"
    )


def test_reprocess_no_body_text_used(conn, db_path):
    """Reprocessing must not access body_text (which is never stored).

    This is verified by ensuring the script works correctly on records that
    would have body_text=None — which all stored records do.
    """
    from scripts.reprocess_email_records import reprocess, _row_to_metadata

    # Create a record
    email = _make_email("rp-005", "billing@account.netflix.com",
                        "Your Netflix membership receipt - $15.49")
    process_email(conn, email)
    conn.commit()

    # Read the stored record and reconstruct metadata
    row = conn.execute(
        "SELECT * FROM email_records WHERE source_message_id = ?", ("rp-005",)
    ).fetchone()
    assert row is not None

    metadata = _row_to_metadata(conn, row)

    # body_text and snippet must be None (privacy constraint)
    assert metadata.body_text is None, (
        "body_text must be None in reprocessed EmailMetadata — it is never stored"
    )
    assert metadata.snippet is None, (
        "snippet must be None in reprocessed EmailMetadata — it is ephemeral, never stored"
    )

    # Full reprocess should still succeed without body_text
    reprocess(db_path=db_path, dry_run=False)
    pe = get_payment_events(conn, source_message_id="rp-005")
    assert len(pe) == 1, "Reprocessing without body_text must still produce a payment_event"
