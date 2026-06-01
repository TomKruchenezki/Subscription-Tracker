"""
Phase 3.7 privacy gate: the attachment tables must never store raw email or PDF content.

email_attachments and attachment_extracted_fields hold structured metadata + short
coded reason tokens only. No column may store raw PDF text, raw bytes, body, HTML,
snippet, or payload content.
"""
import sqlite3
from pathlib import Path

import pytest

# Substrings that would indicate a column may hold raw content (matches the policy in
# tests/privacy/test_no_body_in_schema.py).
PROHIBITED = {"body", "html", "raw", "content", "full", "snippet", "payload"}

_ATTACHMENT_TABLES = ["email_attachments", "attachment_extracted_fields"]


@pytest.mark.parametrize("table", _ATTACHMENT_TABLES)
def test_attachment_table_has_no_raw_content_columns(db_path, table):
    conn = sqlite3.connect(db_path)
    try:
        cols = [row[1].lower() for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    finally:
        conn.close()
    assert cols, f"{table} should exist after migrations"
    violations = [c for c in cols if any(term in c for term in PROHIBITED)]
    assert violations == [], f"{table} has columns that may store raw content: {violations}"


def test_migration_011_declares_no_raw_text_column():
    """Migration 011 SQL must not declare any raw text/content column."""
    migration = Path("backend/db/migrations/011_attachments.sql")
    if not migration.exists():
        pytest.skip("011_attachments.sql not found")
    sql = migration.read_text(encoding="utf-8").lower()
    # Column-definition-ish substrings that would store raw extracted text.
    forbidden = ["extracted_text", "pdf_text", "raw_text", "full_text", "body_text",
                 "body_html", "snippet", "ocr_text", "text_content"]
    for token in forbidden:
        for line in sql.split("\n"):
            stripped = line.strip()
            if stripped.startswith("--"):
                continue  # comments may mention these in prohibitions
            assert token not in stripped, (
                f"011_attachments.sql must not declare a raw-text column ({token!r}). "
                f"Found in: {line.strip()!r}"
            )
