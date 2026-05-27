"""
Subscription Tracker — Privacy-Safe Validation Report
======================================================

Reads aggregate-only metrics from the local SQLite database and prints a
report that is safe to paste into chat. No raw email content is exposed:
no subjects, no sender addresses, no source_message_id values, no account
emails, no short_evidence text.

Usage:
    python scripts/validation_report.py
    python scripts/validation_report.py --db data/subscriptions.db
    python scripts/validation_report.py > report.txt

The database is opened in READ-ONLY mode. This script cannot corrupt it.
"""

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


# ── .env loader (no third-party deps) ────────────────────────────────────────

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


# ── Formatting helpers ────────────────────────────────────────────────────────

W = 52  # report width

def _header(title: str) -> str:
    return f"\n-- {title} {'-' * max(0, W - 4 - len(title))}"

def _flag(ok: bool | None, warn: bool = False) -> str:
    if ok is True:
        return "PASS"
    if ok is None or warn:
        return "WARN"
    return "FAIL"

def _fmt_amount(amount) -> str:
    if amount is None:
        return "    —  "
    return f"${float(amount):>6.2f}"


# ── Report sections ───────────────────────────────────────────────────────────

def _run(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    return conn.execute(sql, params).fetchall()


def report(db_path: str, use_mock: bool) -> None:
    # Open read-only
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
    except Exception as exc:
        print(f"ERROR: Cannot open database at {db_path!r}: {exc}", file=sys.stderr)
        sys.exit(1)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # ── Header ────────────────────────────────────────────────────────────────
    print("+" + "=" * W + "+")
    print(f"|  Subscription Tracker -- Validation Report{' ' * (W - 43)}|")
    print(f"|  {now}{' ' * max(0, W - 2 - len(now))}|")
    db_display = db_path if len(db_path) <= W - 5 else "..." + db_path[-(W - 7):]
    print(f"|  DB: {db_display}{' ' * max(0, W - 6 - len(db_display))}|")
    print("+" + "=" * W + "+")

    # ── Subscriptions ─────────────────────────────────────────────────────────
    print(_header("Subscriptions"))

    total_subs = _run(conn, "SELECT COUNT(*) FROM subscriptions")[0][0]
    print(f"  Total: {total_subs}")

    by_source_subs = _run(conn,
        "SELECT source_provider, COUNT(*) FROM subscriptions GROUP BY source_provider ORDER BY source_provider")
    parts = "  ".join(f"{r[0]}={r[1]}" for r in by_source_subs)
    print(f"  By source:  {parts}")

    by_status = _run(conn,
        "SELECT status, COUNT(*) FROM subscriptions GROUP BY status ORDER BY status")
    parts = "  ".join(f"{r[0]}={r[1]}" for r in by_status)
    print(f"  By status:  {parts}")

    gmail_subs = _run(conn,
        """SELECT name, status, amount, billing_cycle
           FROM subscriptions WHERE source_provider = 'GMAIL'
           ORDER BY name""")
    if gmail_subs:
        print(f"\n  Detected services (GMAIL):")
        for row in gmail_subs:
            name = row["name"] or "(unknown)"
            status = row["status"] or "—"
            amt = _fmt_amount(row["amount"])
            cycle = row["billing_cycle"] or "—"
            print(f"    {name:<22} {status:<12} {amt}  {cycle}")
    else:
        print("\n  Detected services (GMAIL): (none)")

    # Data quality
    missing_amount = _run(conn,
        "SELECT COUNT(*) FROM subscriptions WHERE source_provider='GMAIL' AND amount IS NULL")[0][0]
    missing_first = _run(conn,
        "SELECT COUNT(*) FROM subscriptions WHERE source_provider='GMAIL' AND first_charge_date IS NULL")[0][0]
    missing_last = _run(conn,
        "SELECT COUNT(*) FROM subscriptions WHERE source_provider='GMAIL' AND last_charge_date IS NULL")[0][0]

    print(f"\n  Data quality (GMAIL subscriptions):")
    print(f"    Missing amount:             {missing_amount}")
    print(f"    Missing first_charge_date:  {missing_first}")
    print(f"    Missing last_charge_date:   {missing_last}")

    # ── Email Records ─────────────────────────────────────────────────────────
    print(_header("Email Records"))

    total_records = _run(conn, "SELECT COUNT(*) FROM email_records")[0][0]
    print(f"  Total stored: {total_records}")

    by_src_disp = _run(conn,
        """SELECT source_provider, disposition, COUNT(*) as cnt
           FROM email_records
           GROUP BY source_provider, disposition
           ORDER BY source_provider, disposition""")
    if by_src_disp:
        print(f"\n  By source + disposition:")
        for row in by_src_disp:
            print(f"    {row[0]:<8} / {row[1]:<10} {row[2]}")
    else:
        print("\n  By source + disposition: (no records)")

    # ── MOCK Contamination ────────────────────────────────────────────────────
    print(_header("MOCK Contamination"))

    mock_records = _run(conn,
        "SELECT COUNT(*) FROM email_records WHERE source_provider = 'MOCK'")[0][0]
    mock_subs = _run(conn,
        "SELECT COUNT(*) FROM subscriptions WHERE source_provider = 'MOCK'")[0][0]

    if not use_mock:
        if mock_records > 0 or mock_subs > 0:
            print(f"  USE_MOCK=false, but {mock_records} MOCK email records and")
            print(f"  {mock_subs} MOCK subscriptions found.             [WARN]")
            print(f"  Expected: 0 MOCK rows in Gmail mode.")
        else:
            print(f"  USE_MOCK=false, no MOCK contamination detected.   [PASS]")
    else:
        print(f"  USE_MOCK=true — mock mode is active (expected MOCK rows).")
        print(f"  MOCK email records: {mock_records}   MOCK subscriptions: {mock_subs}")

    # ── Review Queue ──────────────────────────────────────────────────────────
    gmail_flagged = _run(conn,
        "SELECT COUNT(*) FROM email_records WHERE disposition='FLAGGED' AND source_provider='GMAIL'")[0][0]

    print(_header(f"Review Queue (GMAIL FLAGGED: {gmail_flagged})"))

    with_amount = _run(conn,
        """SELECT COUNT(*) FROM email_records
           WHERE disposition='FLAGGED' AND source_provider='GMAIL'
           AND amount_extracted IS NOT NULL""")[0][0]
    without_amount = gmail_flagged - with_amount
    print(f"  With amount extracted:    {with_amount}")
    print(f"  Without amount:           {without_amount}")

    # Confidence bands (FLAGGED GMAIL only)
    bands = _run(conn,
        """SELECT
             CASE
               WHEN confidence_score >= 0.80 THEN '80%+'
               WHEN confidence_score >= 0.70 THEN '70-79%'
               WHEN confidence_score >= 0.60 THEN '60-69%'
               WHEN confidence_score >= 0.50 THEN '50-59%'
               ELSE '40-49%'
             END AS band,
             COUNT(*) as cnt
           FROM email_records
           WHERE disposition = 'FLAGGED' AND source_provider = 'GMAIL'
           GROUP BY band
           ORDER BY band DESC""")

    if bands:
        print(f"\n  Confidence score bands:")
        band_dict = {r["band"]: r["cnt"] for r in bands}
        high_confidence_flagged = band_dict.get("80%+", 0) + band_dict.get("70-79%", 0)
        for label in ["80%+", "70-79%", "60-69%", "50-59%", "40-49%"]:
            cnt = band_dict.get(label, 0)
            note = ""
            if label in ("80%+", "70-79%") and cnt > 0:
                note = "  <- check these (should be DETECTED)"  # noqa: E501
            print(f"    {label:<8} {cnt}{note}")

    # ── Event Types ───────────────────────────────────────────────────────────
    print(_header("Event Types (GMAIL records)"))

    event_types = _run(conn,
        """SELECT COALESCE(event_type, '(none)') as et, COUNT(*) as cnt
           FROM email_records WHERE source_provider = 'GMAIL'
           GROUP BY et ORDER BY cnt DESC""")
    if event_types:
        for row in event_types:
            print(f"  {row['et']:<30} {row['cnt']}")
    else:
        print("  (no GMAIL records)")

    # ── Duplicates ────────────────────────────────────────────────────────────
    print(_header("Duplicates"))

    msg_id_dups = _run(conn,
        """SELECT COUNT(*) FROM (
             SELECT source_message_id FROM email_records
             WHERE source_message_id IS NOT NULL
             GROUP BY source_message_id HAVING COUNT(*) > 1
           )""")[0][0]
    flag = _flag(msg_id_dups == 0)
    print(f"  source_message_id duplicates:  {flag} ({msg_id_dups})")

    name_dups = _run(conn,
        """SELECT name, COUNT(*) as cnt FROM subscriptions
           GROUP BY name HAVING cnt > 1 ORDER BY name""")
    if name_dups:
        print(f"  Duplicate subscription names:  WARN ({len(name_dups)} names)")
        for row in name_dups:
            print(f"    {row['name']}  ({row['cnt']} rows)")
    else:
        print(f"  Duplicate subscription names:  PASS (0)")

    # ── Connected Accounts ────────────────────────────────────────────────────
    print(_header("Connected Accounts"))

    accounts = _run(conn,
        """SELECT source_provider, is_active, COUNT(*) as cnt
           FROM connected_accounts
           GROUP BY source_provider, is_active
           ORDER BY source_provider""")
    if accounts:
        for row in accounts:
            state = "active" if row["is_active"] else "inactive"
            print(f"  {row['source_provider']:<8} ({state}): {row['cnt']}")
    else:
        print("  (no connected accounts)")

    # ── Safety Checklist ──────────────────────────────────────────────────────
    print(_header("Safety Checklist"))

    checks = []

    # Records exist
    checks.append((
        "Records exist",
        total_records > 0,
        f"{total_records} stored"
    ))

    # MOCK contamination (only warn in gmail mode)
    if not use_mock:
        no_mock = (mock_records == 0 and mock_subs == 0)
        checks.append((
            "No MOCK contamination",
            None if (not no_mock) else True,
            f"{mock_records} MOCK records" if not no_mock else "clean"
        ))
    else:
        checks.append(("No MOCK contamination", None, "mock mode active (expected)"))

    # No message ID duplicates
    checks.append((
        "No source_message_id duplicates",
        msg_id_dups == 0,
        f"{msg_id_dups}"
    ))

    # No duplicate subscription names
    checks.append((
        "No duplicate subscription names",
        len(name_dups) == 0,
        f"{len(name_dups)}"
    ))

    # Review Queue has items (expected for any real mailbox)
    if not use_mock:
        checks.append((
            "Review Queue populated",
            None if gmail_flagged == 0 else True,
            f"{gmail_flagged} flagged"
        ))

    # High-confidence items stuck in queue
    if not use_mock and bands:
        high_conf = band_dict.get("80%+", 0) + band_dict.get("70-79%", 0)
        checks.append((
            "High-confidence items in queue",
            None if high_conf > 0 else True,
            f"{high_conf} item(s) >=70% — review these" if high_conf > 0 else "none"
        ))

    # Data quality
    checks.append((
        "Subscriptions with amount",
        None if missing_amount > 0 else True,
        f"{missing_amount} missing" if missing_amount else "all present"
    ))
    checks.append((
        "first_charge_date coverage",
        None if missing_first > 0 else True,
        f"{missing_first} missing" if missing_first else "all present"
    ))

    for label, ok, detail in checks:
        flag_str = _flag(ok is True, warn=(ok is None))
        print(f"  {label:<38} {flag_str:<5}  ({detail})")

    print()
    conn.close()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print a privacy-safe validation report from the local SQLite database."
    )
    parser.add_argument("--db", metavar="PATH", help="Path to the SQLite database file.")
    args = parser.parse_args()

    # Load .env from project root (two levels up from this file)
    project_root = Path(__file__).resolve().parent.parent
    dotenv = _load_dotenv(project_root / ".env")

    # Resolve DB path: arg > env > .env > default
    db_path = (
        args.db
        or os.getenv("DB_PATH")
        or dotenv.get("DB_PATH")
        or str(project_root / "data" / "subscriptions.db")
    )

    # Resolve USE_MOCK
    raw_use_mock = (
        os.getenv("USE_MOCK")
        or dotenv.get("USE_MOCK")
        or "true"
    )
    use_mock = raw_use_mock.lower() not in {"false", "0", "no"}

    if not Path(db_path).exists():
        print(f"ERROR: Database not found at {db_path!r}", file=sys.stderr)
        print("Run a scan first: open the dashboard and click 'Run scan'.", file=sys.stderr)
        sys.exit(1)

    report(db_path, use_mock)


if __name__ == "__main__":
    main()
