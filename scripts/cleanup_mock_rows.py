#!/usr/bin/env python3
"""
scripts/cleanup_mock_rows.py

Deletes MOCK email_records and MOCK subscriptions from the local database.
NEVER touches GMAIL rows. Prints counts before and after.
Safe to run multiple times (idempotent).

Usage:
    python scripts/cleanup_mock_rows.py             # prompts for confirmation
    python scripts/cleanup_mock_rows.py --yes       # skip confirmation
    python scripts/cleanup_mock_rows.py --db path   # use specific DB file
"""
import argparse
import os
import sqlite3
import sys
from pathlib import Path


def _load_dotenv() -> None:
    env_file = Path(".env")
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def main() -> None:
    _load_dotenv()
    parser = argparse.ArgumentParser(description="Delete MOCK rows from the local DB.")
    parser.add_argument(
        "--db",
        default=os.getenv("DB_PATH", "data/subscriptions.db"),
        help="Path to SQLite database file (default: data/subscriptions.db)",
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Skip confirmation prompt",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Error: database not found at {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        mock_email_count: int = conn.execute(
            "SELECT COUNT(*) FROM email_records WHERE source_provider = 'MOCK'"
        ).fetchone()[0]
        mock_sub_count: int = conn.execute(
            "SELECT COUNT(*) FROM subscriptions WHERE source_provider = 'MOCK'"
        ).fetchone()[0]
        gmail_email_count: int = conn.execute(
            "SELECT COUNT(*) FROM email_records WHERE source_provider = 'GMAIL'"
        ).fetchone()[0]
        gmail_sub_count: int = conn.execute(
            "SELECT COUNT(*) FROM subscriptions WHERE source_provider = 'GMAIL'"
        ).fetchone()[0]

        print(f"\nDatabase: {db_path}")
        print(f"  MOCK email_records : {mock_email_count}")
        print(f"  MOCK subscriptions : {mock_sub_count}")
        print(f"  GMAIL email_records: {gmail_email_count}  (WILL NOT BE TOUCHED)")
        print(f"  GMAIL subscriptions: {gmail_sub_count}  (WILL NOT BE TOUCHED)")

        if mock_email_count == 0 and mock_sub_count == 0:
            print("\nNothing to clean up — no MOCK rows found.")
            return

        if not args.yes:
            answer = input(
                f"\nDelete {mock_email_count} MOCK email_records and "
                f"{mock_sub_count} MOCK subscriptions? [y/N] "
            )
            if answer.strip().lower() != "y":
                print("Aborted.")
                return

        # Delete email_records first (handles orphaned FLAGGED/IGNORED records with NULL sub_id)
        conn.execute("DELETE FROM email_records WHERE source_provider = 'MOCK'")
        # Delete subscriptions (cascade would handle email_records but they're already gone)
        conn.execute("DELETE FROM subscriptions WHERE source_provider = 'MOCK'")
        conn.commit()

        # Verify GMAIL rows are completely intact
        gmail_email_after: int = conn.execute(
            "SELECT COUNT(*) FROM email_records WHERE source_provider = 'GMAIL'"
        ).fetchone()[0]
        gmail_sub_after: int = conn.execute(
            "SELECT COUNT(*) FROM subscriptions WHERE source_provider = 'GMAIL'"
        ).fetchone()[0]

        assert gmail_email_after == gmail_email_count, (
            f"BUG: GMAIL email_records count changed from {gmail_email_count} to {gmail_email_after}!"
        )
        assert gmail_sub_after == gmail_sub_count, (
            f"BUG: GMAIL subscriptions count changed from {gmail_sub_count} to {gmail_sub_after}!"
        )

        print(
            f"\nDone. Deleted {mock_email_count} MOCK email_records "
            f"and {mock_sub_count} MOCK subscriptions."
        )
        print(
            f"GMAIL rows intact: {gmail_sub_after} subscriptions, "
            f"{gmail_email_after} email_records."
        )

    finally:
        conn.close()


if __name__ == "__main__":
    main()
