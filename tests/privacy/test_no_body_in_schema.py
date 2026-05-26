"""
Asserts that no column in email_records stores email body content.
Prohibited column name substrings: body, html, raw, content, full, snippet, payload.
"""
import sqlite3
import pytest

PROHIBITED = {"body", "html", "raw", "content", "full", "snippet", "payload"}


def test_no_body_columns_in_email_records(db_path):
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute("PRAGMA table_info(email_records)")
        columns = [row[1].lower() for row in cursor.fetchall()]
    finally:
        conn.close()

    violations = [col for col in columns if any(term in col for term in PROHIBITED)]
    assert violations == [], (
        f"email_records has columns that may store body content: {violations}"
    )


def test_no_body_columns_in_subscriptions(db_path):
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute("PRAGMA table_info(subscriptions)")
        columns = [row[1].lower() for row in cursor.fetchall()]
    finally:
        conn.close()

    violations = [col for col in columns if any(term in col for term in PROHIBITED)]
    assert violations == [], (
        f"subscriptions has columns that may store body content: {violations}"
    )
