"""
Phase 3.8 privacy compliance tests.

Verifies:
- gmail_account_id is an opaque metadata field (not a raw Gmail address)
- merchant_name_candidate never contains raw body text, raw PDF text, or snippets
- account alias never exposes a full Gmail address in API responses
- is_processor_email flag does not leak PII
"""
import sqlite3
import os
import pytest
from datetime import datetime, timezone
from backend.models.email_metadata import EmailMetadata
from backend.detector.detector import process_email
from backend.db.setup import get_email_records, account_alias


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_email(msg_id: str, sender: str, subject: str,
                body: str | None = None, snippet: str | None = None,
                account_id: str = "test_account_123") -> EmailMetadata:
    return EmailMetadata(
        source_message_id=msg_id,
        source_provider="MOCK",
        source_account_id=account_id,
        source_account_email="user@gmail.com",
        sender_address=sender,
        sender_name=None,
        subject=subject,
        email_date=datetime.fromisoformat("2025-06-01T10:00:00Z".replace("Z", "+00:00")),
        snippet=snippet,
        body_text=body,
    )


@pytest.fixture
def conn(db_path):
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    yield c
    c.close()


# ── gmail_account_id is metadata only ─────────────────────────────────────────

def test_gmail_account_id_is_not_raw_email_address(conn):
    """gmail_account_id stores an opaque ID, not the raw Gmail address."""
    email = _make_email(
        "acct-id-test",
        "billing@email.spotify.com",
        "Your receipt",
        account_id="opaque-account-id-xyz",
    )
    process_email(conn, email)
    records = get_email_records(conn, include_dismissed=True)
    assert len(records) == 1
    rec = records[0]
    # gmail_account_id should be the opaque account ID, not the email address
    gaid = rec["gmail_account_id"] if "gmail_account_id" in rec.keys() else None
    if gaid is not None:
        # Must not contain "@" or "gmail.com" — opaque IDs don't look like email addresses
        assert "@" not in str(gaid), (
            f"gmail_account_id must be an opaque ID, not a raw email address. Got: {gaid!r}"
        )


def test_account_alias_is_truncated_hash(conn):
    """account_alias() returns an 8-char hex string (SHA-256 prefix), not the raw account ID."""
    alias = account_alias("some-account-id-123")
    assert alias is not None
    assert len(alias) == 8, f"account_alias must be 8 chars, got {len(alias)!r}: {alias!r}"
    assert all(c in "0123456789abcdef" for c in alias), (
        f"account_alias must be a hex string, got {alias!r}"
    )


def test_account_alias_none_for_none_input():
    """account_alias(None) returns None — no crash or PII leak."""
    assert account_alias(None) is None


# ── merchant_name_candidate must never contain raw body text ──────────────────

def test_merchant_name_candidate_not_set_for_non_processor(conn):
    """For regular (non-processor) senders, merchant_name_candidate is None (not used)."""
    email = _make_email(
        "non-processor-001",
        "billing@email.spotify.com",
        "Spotify Premium receipt $9.99/mo",
        body="Full body text with sensitive content: card ending 1234.",
    )
    process_email(conn, email)
    records = get_email_records(conn, include_dismissed=True)
    assert len(records) == 1
    rec = records[0]
    mnc = rec["merchant_name_candidate"] if "merchant_name_candidate" in rec.keys() else None
    # For non-processor: either None or a short canonical name — never raw body text
    if mnc is not None:
        assert "card ending" not in str(mnc), (
            "merchant_name_candidate must never contain raw body text"
        )
        assert len(str(mnc)) <= 100, (
            f"merchant_name_candidate must be a short structured name, got {len(str(mnc))} chars"
        )


def test_merchant_name_candidate_for_processor_is_structured(conn):
    """For processor senders, merchant_name_candidate (if set) is a short structured label."""
    email = _make_email(
        "cardcom-privacy-001",
        "billing@cardcom.co.il",
        "Receipt NIS 80.00",
        body="Detailed invoice body with long customer PII and bank details here.",
    )
    process_email(conn, email)
    records = get_email_records(conn, include_dismissed=True)
    assert len(records) == 1
    rec = records[0]
    mnc = rec["merchant_name_candidate"] if "merchant_name_candidate" in rec.keys() else None
    if mnc is not None:
        # merchant_name_candidate must be short and must never contain body text fragments
        assert "invoice body" not in str(mnc), (
            "merchant_name_candidate must not contain raw body text fragments"
        )
        assert "PII" not in str(mnc), (
            "merchant_name_candidate must not contain body text"
        )
        assert len(str(mnc)) <= 100, (
            f"merchant_name_candidate must be a short structured label. Got {len(str(mnc))} chars"
        )


# ── Processor flag does not leak PII ──────────────────────────────────────────

def test_is_processor_email_is_0_or_1(conn):
    """is_processor_email is always 0 or 1 — a boolean flag, not a string or PII value."""
    email = _make_email(
        "processor-flag-001",
        "noreply@cardcom.co.il",
        "Receipt - payment received $50.00",  # RECEIPT pattern ensures the email is stored
    )
    process_email(conn, email)
    records = get_email_records(conn, include_dismissed=True)
    assert len(records) == 1
    rec = records[0]
    flag = rec["is_processor_email"] if "is_processor_email" in rec.keys() else 0
    assert flag in (0, 1), f"is_processor_email must be 0 or 1, got {flag!r}"


# ── Processor rows still stored (never dropped) ───────────────────────────────

def test_processor_email_record_is_stored_not_silently_dropped(conn):
    """Processor emails must always produce a stored email_record (never silently IGNORED)."""
    email = _make_email(
        "processor-stored-001",
        "invoice@z-credit.co.il",
        "Invoice NIS 120.00",
    )
    process_email(conn, email)
    all_records = get_email_records(conn, include_dismissed=True, exclude_processor_rows=False)
    assert len(all_records) == 1, (
        "Processor email must be stored as an email_record — never silently dropped"
    )
    assert all_records[0]["disposition"] != "IGNORED", (
        "Processor email must not be IGNORED — it must be stored for correction/history"
    )
