"""
Reprocessing Mode — re-derive payment_events and subscription links from stored email_records.

Usage:
    python scripts/reprocess_email_records.py [options]

Options:
    --db PATH           Path to SQLite DB (default: data/subscriptions.db or DB_PATH env var)
    --provider NAME     Only reprocess records for a specific canonical merchant name
                        (e.g. "Spotify", "Wolt+", "ChatGPT")
    --since DATE        Only reprocess records with email_date >= DATE (YYYY-MM-DD)
    --dry-run           Print what would be reprocessed without making any changes

What this script does:
    1. Reads existing email_records from the local DB (no Gmail fetch)
    2. For each matching record:
       a. Deletes its existing payment_events (by source_message_id)
       b. Reconstructs EmailMetadata from stored fields (sender, subject, date)
       c. Calls process_email() — INSERT OR IGNORE ensures email_record isn't re-inserted
       d. New payment_events are created with current detector rules
       e. Subscription upsert re-runs with current rules (updated amounts, cycles, etc.)
    3. Commits the updated payment_events and subscription links

When to use:
    - After adding a new Tier 1 provider (e.g. Wolt+): reprocess to pick up old emails
    - After fixing a detector bug (e.g. cycle detection): reprocess to correct old data
    - After a billing cycle fix: reprocess to update payment_events event_types
    - To regenerate payment_events without re-fetching months of Gmail history

Limitations:
    - body_text and snippet are NOT stored (privacy design). Body-dependent parsing
      improvements CANNOT be replayed without refetching from Gmail.
    - Only stored metadata fields (sender, subject, date, account_id) are reprocessed.
    - email_records themselves are NOT modified (they are the authoritative source).

Privacy guarantee:
    - Reads only structured metadata fields — no raw body, HTML, or snippet from DB
      (those were never stored).
    - Does not fetch from Gmail or any external service.
    - Does not log raw email content (subjects are logged only in debug mode with --verbose).
    - Output safe to share: shows counts and provider names only.
"""
import argparse
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


def _load_dotenv(path: Path) -> dict[str, str]:
    """Parse a .env file and return a dict of key=value pairs."""
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        env[key] = value
    return env


def _reconstruct_pdf_attachments(conn: sqlite3.Connection, record_id: str) -> list[dict]:
    """Rebuild ephemeral PDF evidence from STORED structured fields (Phase 3.7).

    The raw PDF text was never stored, but the structured attachment_extracted_fields
    rows were. Reconstructing them lets reprocessing replay PDF-derived amounts/cycles
    into payment_events and subscription upserts WITHOUT re-fetching from Gmail.
    """
    from backend.parser.pdf_extractor import PdfEvidence

    try:
        rows = conn.execute(
            "SELECT * FROM attachment_extracted_fields WHERE email_record_id = ?",
            (record_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []  # pre-3.7 DB without the table

    def _split(val: str | None) -> list[str]:
        return [t for t in (val or "").split(";") if t]

    attachments: list[dict] = []
    for fr in rows:
        ev = PdfEvidence(
            extraction_status=fr["extraction_status"] or "OK",
            provider=fr["provider"],
            product_name=fr["product_name"],
            amount=fr["amount"],
            currency=fr["currency"],
            invoice_date=fr["invoice_date"],
            payment_date=fr["payment_date"],
            billing_period_start=fr["billing_period_start"],
            billing_period_end=fr["billing_period_end"],
            inferred_cycle=fr["inferred_cycle"],
            tax_amount=fr["tax_amount"],
            invoice_number=fr["invoice_number"],
            subscription_indicators=_split(fr["subscription_indicators"]),
            evidence_reasons=_split(fr["evidence_reasons"]),
            missing_evidence=_split(fr["missing_evidence"]),
            penalty_reasons=_split(fr["penalty_reasons"]),
            confidence_score=fr["confidence_score"] or 0.0,
            parser_version=fr["parser_version"],
        )
        attachments.append({
            "detected_attachment_type": "PDF_OTHER",
            "processing_status": "PARSED",
            "evidence": ev,
        })
    return attachments


def _row_to_metadata(conn: sqlite3.Connection, row: sqlite3.Row):
    """Reconstruct EmailMetadata from a stored email_records row.

    Privacy: uses only stored structured fields. snippet and body_text are NOT
    stored (privacy design) — they are left as None. This means body_text-dependent
    parsing improvements cannot be replayed without refetching from Gmail.

    Phase 3.7: PDF-derived evidence IS replayed from stored attachment_extracted_fields
    (structured fields only — never raw PDF text), so corrections and PDF amounts persist.
    """
    from backend.models.email_metadata import EmailMetadata

    email_date_str = row["email_date"] or ""
    try:
        email_date = datetime.fromisoformat(email_date_str.replace("Z", "+00:00"))
    except ValueError:
        email_date = datetime.now(timezone.utc)

    return EmailMetadata(
        source_message_id=row["source_message_id"],
        source_provider=row["source_provider"],
        source_account_id=row["source_account_id"],
        source_account_email=row["source_account_email"],
        sender_address=row["sender_address"],
        sender_name=row["sender_name"],
        subject=row["subject"],
        email_date=email_date,
        snippet=None,     # ephemeral — never stored (privacy design)
        body_text=None,   # ephemeral — never stored (privacy design)
        attachments=_reconstruct_pdf_attachments(conn, row["record_id"]),
    )


def reprocess(
    db_path: str,
    provider_filter: str | None = None,
    since_date: str | None = None,
    dry_run: bool = False,
    verbose: bool = False,
) -> None:
    """Main reprocessing function."""
    # Import here so project root doesn't need to be in sys.path when loading
    from backend.db.setup import get_connection
    from backend.detector.detector import process_email

    conn = get_connection(db_path)
    conn.row_factory = sqlite3.Row

    # ── Build filter query ────────────────────────────────────────────────────
    # We filter by canonical_name (merchant name) if provider_filter is given.
    # email_records doesn't store canonical_name directly — it stores sender_address.
    # We look up which sender_addresses map to the given canonical name via
    # the subscriptions and payment_events tables.
    conditions: list[str] = []
    params: list = []

    if provider_filter:
        # Filter: only records linked to this provider's subscriptions,
        # or that already have payment_events with this merchant_name.
        conditions.append(
            "(er.subscription_id IN "
            "(SELECT s.subscription_id FROM subscriptions s WHERE s.name = ?) "
            "OR er.source_message_id IN "
            "(SELECT pe.source_message_id FROM payment_events pe WHERE pe.merchant_name = ?))"
        )
        params.extend([provider_filter, provider_filter])

    if since_date:
        conditions.append("er.email_date >= ?")
        params.append(since_date)

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    query = (
        "SELECT er.* FROM email_records er "
        + (where_clause + " " if where_clause else "")
        + "ORDER BY er.email_date ASC"
    )

    rows = conn.execute(query, params).fetchall()
    total = len(rows)

    print(f"Reprocess mode: {'DRY RUN — no changes will be written' if dry_run else 'LIVE'}")
    if provider_filter:
        print(f"  Provider filter: {provider_filter!r}")
    if since_date:
        print(f"  Since: {since_date}")
    print(f"  Matching email_records: {total}")
    print()

    if total == 0:
        print("Nothing to reprocess.")
        conn.close()
        return

    reprocessed = 0
    payment_events_deleted = 0
    errors = 0

    for row in rows:
        msg_id = row["source_message_id"]
        try:
            # Phase 3.5/3.6: Skip dismissed records — user explicitly said "not relevant"
            if row["user_dismissed"] == 1:
                if verbose:
                    print(f"  SKIPPED (dismissed): {msg_id[:12]}...")
                continue

            # Count existing payment_events for this message
            existing_pe = conn.execute(
                "SELECT COUNT(*) FROM payment_events WHERE source_message_id = ?",
                (msg_id,),
            ).fetchone()[0]

            if verbose:
                print(f"  [{row['source_provider']}] {msg_id[:12]}... "
                      f"(existing payment_events: {existing_pe})")

            if not dry_run:
                # Delete existing payment_events so they are recreated with current rules.
                # INSERT OR IGNORE on event_id (UUID5) would otherwise skip updates.
                conn.execute(
                    "DELETE FROM payment_events WHERE source_message_id = ?",
                    (msg_id,),
                )
                payment_events_deleted += existing_pe

                # Reconstruct EmailMetadata and re-run detector.
                # email_record INSERT is skipped (existing source_message_id → no-op).
                # Subscription upsert and payment_event creation use current rules.
                metadata = _row_to_metadata(conn, row)
                # persist_attachments=False: the email_record + attachment rows already
                # exist; reprocess replays stored PDF evidence into payment_events and
                # the subscription upsert only — it must not duplicate attachment rows.
                process_email(conn, metadata, persist_attachments=False)

            reprocessed += 1

        except Exception as exc:
            errors += 1
            print(f"  ERROR processing {msg_id[:12]}...: {type(exc).__name__}: {exc}")
            if errors > 10:
                print("  Too many errors — aborting.")
                break

    if not dry_run:
        conn.commit()

    conn.close()

    print(f"Done.")
    print(f"  Records processed: {reprocessed} / {total}")
    if not dry_run:
        print(f"  Payment events deleted (before recreate): {payment_events_deleted}")
    if errors:
        print(f"  Errors: {errors}")
    if dry_run:
        print()
        print("DRY RUN complete — no changes written. Remove --dry-run to apply.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Reprocess existing email_records to regenerate payment_events and "
            "subscription links using current detector rules. "
            "Does not fetch from Gmail — uses only stored metadata."
        )
    )
    parser.add_argument("--db", metavar="PATH",
                        help="Path to SQLite DB (default: DB_PATH env var or data/subscriptions.db)")
    parser.add_argument("--provider", metavar="NAME",
                        help="Only reprocess records for this canonical merchant name")
    parser.add_argument("--since", metavar="DATE",
                        help="Only reprocess records with email_date >= DATE (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be reprocessed without making changes")
    parser.add_argument("--verbose", action="store_true",
                        help="Print each record being processed (debug)")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    dotenv = _load_dotenv(project_root / ".env")

    # Add project root to sys.path so backend imports work
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    db_path = (
        args.db
        or os.getenv("DB_PATH")
        or dotenv.get("DB_PATH")
        or str(project_root / "data" / "subscriptions.db")
    )

    if not Path(db_path).exists():
        print(f"ERROR: Database not found at {db_path!r}", file=sys.stderr)
        print("Run a scan first.", file=sys.stderr)
        sys.exit(1)

    reprocess(
        db_path=db_path,
        provider_filter=args.provider,
        since_date=args.since,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
