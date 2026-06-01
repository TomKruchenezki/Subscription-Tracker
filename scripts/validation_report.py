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
import hashlib
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
        return "   N/A "   # 7 chars, ASCII-safe — avoids Windows CP1252 encoding issues
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

    # ── Provider Detection Stats ──────────────────────────────────────────────
    print(_header("Provider Detection Stats (GMAIL)"))

    provider_rows = _run(conn, """
        SELECT s.name, s.status, s.amount, s.billing_cycle,
               COALESCE(rc.receipt_count, 0) AS confirmed_receipts
        FROM subscriptions s
        LEFT JOIN (
            SELECT subscription_id, COUNT(*) AS receipt_count
            FROM email_records
            WHERE event_type IN ('subscription_started', 'renewal_charge')
            GROUP BY subscription_id
        ) rc ON rc.subscription_id = s.subscription_id
        WHERE s.source_provider = 'GMAIL'
        ORDER BY s.amount DESC
    """)

    if provider_rows:
        print(f"  {'Name':<22} {'Status':<10} {'Amount':>7}  {'Cycle':<8}  Receipts")
        print(f"  {'-'*22} {'-'*10} {'-'*7}  {'-'*8}  --------")
        for row in provider_rows:
            name = (row["name"] or "(unknown)")[:22]
            status = (row["status"] or "—")[:10]
            amt = _fmt_amount(row["amount"])
            cycle = (row["billing_cycle"] or "UNKNOWN")[:8]
            receipts = row["confirmed_receipts"] or 0
            print(f"  {name:<22} {status:<10} {amt}  {cycle:<8}  {receipts}")
    else:
        print("  (no GMAIL subscriptions)")

    # ── Billing Cycle Distribution ────────────────────────────────────────────
    print(_header("Billing Cycle Distribution (GMAIL)"))

    cycle_rows = _run(conn, """
        SELECT billing_cycle, COUNT(*) as cnt
        FROM subscriptions WHERE source_provider = 'GMAIL'
        GROUP BY billing_cycle ORDER BY cnt DESC
    """)
    if cycle_rows:
        for row in cycle_rows:
            print(f"  {row['billing_cycle']:<12}  {row['cnt']}")
    else:
        print("  (no GMAIL subscriptions)")

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

    # ── Gmail Account Breakdown ───────────────────────────────────────────────
    print(_header("Gmail Account Breakdown"))

    acct_rows = _run(conn,
        """SELECT source_account_id, disposition, COUNT(*) as cnt
           FROM email_records
           WHERE source_provider = 'GMAIL'
           GROUP BY source_account_id, disposition
           ORDER BY source_account_id, disposition""")

    if acct_rows:
        # Group by masked account ID
        acct_map: dict[str, dict[str, int]] = {}
        for row in acct_rows:
            raw_id = row["source_account_id"] or ""
            alias = hashlib.sha256(raw_id.encode()).hexdigest()[:8]
            if alias not in acct_map:
                acct_map[alias] = {}
            acct_map[alias][row["disposition"]] = row["cnt"]

        for alias, disp_counts in sorted(acct_map.items()):
            detected = disp_counts.get("DETECTED", 0)
            flagged  = disp_counts.get("FLAGGED",  0)
            ignored  = disp_counts.get("IGNORED",  0)
            print(f"  Account {alias}:")
            print(f"    DETECTED: {detected:<4}  FLAGGED: {flagged:<4}  IGNORED: {ignored}")

        if len(acct_map) > 1:
            print(f"\n  Note: {len(acct_map)} Gmail accounts found in email_records.")
            print(f"  Scan currently uses the first connected account only (LIMIT 1).")
        else:
            print(f"\n  Note: account alias is an 8-char SHA-256 hash (stable across runs).")
    else:
        print("  (no GMAIL email records)")

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
               WHEN confidence_score >= 0.40 THEN '40-49%'
               WHEN confidence_score >= 0.30 THEN '30-39%'
               ELSE '<30%'
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
        for label in ["80%+", "70-79%", "60-69%", "50-59%", "40-49%", "30-39%", "<30%"]:
            cnt = band_dict.get(label, 0)
            note = ""
            if label in ("80%+", "70-79%") and cnt > 0:
                note = "  <- check these (should be DETECTED)"  # noqa: E501
            if label == "30-39%" and cnt > 0:
                note = "  <- forensic-only; expect 0 after Phase 3.1 fix"
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

    # ── Detection Quality ─────────────────────────────────────────────────────
    print(_header("Detection Quality (GMAIL)"))

    gmail_total = _run(conn,
        "SELECT COUNT(*) FROM email_records WHERE source_provider='GMAIL'")[0][0]

    # Amount extraction rate by disposition
    amt_rows = _run(conn,
        """SELECT disposition,
                  COUNT(*) as total,
                  SUM(CASE WHEN amount_extracted IS NOT NULL THEN 1 ELSE 0 END) as with_amount
           FROM email_records WHERE source_provider = 'GMAIL'
           GROUP BY disposition
           ORDER BY disposition""")

    if amt_rows:
        print(f"  Amount extraction (of {gmail_total} total GMAIL emails):")
        for row in amt_rows:
            total_d = row["total"]
            with_a  = row["with_amount"]
            pct = f"{100 * with_a // total_d:3d}%" if total_d > 0 else "  N/A"
            print(f"    {row['disposition']:<10} {total_d:>4} total,  {with_a:>3} with amount ({pct})")
        # All GMAIL total
        all_with = sum(r["with_amount"] for r in amt_rows)
        all_pct = f"{100 * all_with // gmail_total:3d}%" if gmail_total > 0 else "  N/A"
        print(f"    {'All GMAIL':<10} {gmail_total:>4} total,  {all_with:>3} with amount ({all_pct})")
    else:
        print("  Amount extraction: (no GMAIL records)")

    # IGNORED breakdown
    ignored_zero = _run(conn,
        """SELECT COUNT(*) FROM email_records
           WHERE source_provider='GMAIL' AND disposition='IGNORED'
           AND confidence_score = 0.0""")[0][0]
    ignored_pos = _run(conn,
        """SELECT COUNT(*) FROM email_records
           WHERE source_provider='GMAIL' AND disposition='IGNORED'
           AND confidence_score > 0.0""")[0][0]
    ignored_total = ignored_zero + ignored_pos
    if ignored_total > 0:
        print(f"\n  IGNORED breakdown ({ignored_total} total):")
        print(f"    Score = 0.00 (excluded domain or no signal):  {ignored_zero}")
        print(f"    Score > 0.00 (below review threshold):         {ignored_pos}")

    # ── Suspicious Detections ────────────────────────────────────────────────
    print(_header("Suspicious Detections (GMAIL)"))

    suspicious = _run(conn, """
        SELECT s.name, s.amount, s.billing_cycle,
               s.first_charge_date IS NULL AS missing_first,
               s.last_charge_date  IS NULL AS missing_last,
               COALESCE(rc.receipt_count, 0) AS confirmed_receipts
        FROM subscriptions s
        LEFT JOIN (
            SELECT subscription_id, COUNT(*) AS receipt_count
            FROM email_records
            WHERE event_type IN ('subscription_started', 'renewal_charge')
            GROUP BY subscription_id
        ) rc ON rc.subscription_id = s.subscription_id
        WHERE s.source_provider = 'GMAIL' AND s.status = 'ACTIVE'
        ORDER BY s.amount DESC
    """)

    if suspicious:
        flags_found = False
        for row in suspicious:
            warnings = []
            if row["billing_cycle"] == "WEEKLY":
                warnings.append("WEEKLY billing (unusual for subscriptions)")
            if row["amount"] and row["amount"] > 100:
                warnings.append("high amount — verify this is real")
            if row["missing_first"]:
                warnings.append("no first_charge_date")
            if row["confirmed_receipts"] == 0:
                warnings.append("no confirmed receipt/renewal email")
            if warnings:
                flags_found = True
                amt = _fmt_amount(row["amount"])
                cycle = row["billing_cycle"] or "UNKNOWN"
                print(f"  WARN  {row['name']:<22} {amt}  {cycle}")
                for w in warnings:
                    print(f"          ^ {w}")
        if not flags_found:
            print("  All ACTIVE subscriptions have strong evidence.   [PASS]")
    else:
        print("  (no ACTIVE GMAIL subscriptions)")

    # ── Evidence Type Summary ─────────────────────────────────────────────────
    print(_header("Evidence Type Summary (GMAIL ACTIVE)"))

    evidence_rows = _run(conn, """
        SELECT COALESCE(er.event_type, '(no linked receipt email)') AS et,
               COUNT(DISTINCT s.subscription_id) AS sub_count
        FROM subscriptions s
        LEFT JOIN email_records er ON er.subscription_id = s.subscription_id
            AND er.event_type IN (
                'subscription_started', 'renewal_charge', 'subscription_candidate',
                'unknown_payment', 'trial_started'
            )
        WHERE s.source_provider = 'GMAIL' AND s.status = 'ACTIVE'
        GROUP BY et
        ORDER BY sub_count DESC
    """)
    if evidence_rows:
        for row in evidence_rows:
            print(f"  {row['et']:<35} {row['sub_count']} subscription(s)")
    else:
        print("  (no ACTIVE GMAIL subscriptions)")

    # ── Payment Events (Phase 3.3) ────────────────────────────────────────────
    # Gracefully skip if the payment_events table doesn't exist (pre-migration DBs)
    has_payment_events = bool(_run(conn,
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='payment_events'"))

    print(_header("Payment Events"))

    if not has_payment_events:
        print("  (payment_events table not found — run migration 006 first)")
    else:
        total_pe = _run(conn, "SELECT COUNT(*) FROM payment_events")[0][0]
        print(f"  Total payment events: {total_pe}")

        if total_pe > 0:
            # Count by event_type
            pe_by_type = _run(conn,
                """SELECT event_type, COUNT(*) as cnt
                   FROM payment_events
                   GROUP BY event_type ORDER BY cnt DESC""")
            print(f"\n  By event type:")
            for row in pe_by_type:
                print(f"    {row['event_type']:<22}  {row['cnt']}")

            # Currency distribution (amount totals per currency, excluding NULL amounts)
            pe_currency = _run(conn,
                """SELECT currency, COUNT(*) as cnt,
                          SUM(amount) as total_amount
                   FROM payment_events
                   WHERE amount IS NOT NULL AND currency IS NOT NULL
                   GROUP BY currency ORDER BY total_amount DESC""")
            if pe_currency:
                print(f"\n  Currency distribution (events with known amount):")
                for row in pe_currency:
                    cur = row["currency"] or "?"
                    total = row["total_amount"] or 0.0
                    print(f"    {cur:<5}  {row['cnt']:>4} events,  total: {total:>9.2f}")

            null_currency_count = _run(conn,
                "SELECT COUNT(*) FROM payment_events WHERE amount IS NULL OR currency IS NULL"
            )[0][0]
            if null_currency_count > 0:
                print(f"    (+ {null_currency_count} events with no amount/currency extracted)")

            # Recurring vs one-time breakdown
            recurring = _run(conn,
                "SELECT COUNT(*) FROM payment_events WHERE is_recurring_candidate = 1")[0][0]
            one_time  = _run(conn,
                "SELECT COUNT(*) FROM payment_events WHERE is_one_time_candidate = 1")[0][0]
            ambiguous = total_pe - recurring - one_time + _run(conn,
                "SELECT COUNT(*) FROM payment_events WHERE is_recurring_candidate=1 AND is_one_time_candidate=1")[0][0]
            print(f"\n  Recurring vs one-time flags:")
            print(f"    is_recurring_candidate = 1:  {recurring}")
            print(f"    is_one_time_candidate  = 1:  {one_time}")
            ambiguous_count = total_pe - recurring - one_time
            if ambiguous_count > 0:
                print(f"    Neither flag set (lifecycle/ambiguous): {ambiguous_count}")

            # Linked to subscription vs orphan
            linked = _run(conn,
                "SELECT COUNT(*) FROM payment_events WHERE subscription_id IS NOT NULL")[0][0]
            orphan = total_pe - linked
            print(f"\n  Linked to subscription:  {linked}")
            print(f"  Orphaned (no sub link):  {orphan}")
        else:
            print("  (no payment events recorded yet — run a scan first)")

    # ── Payment Event Semantics Check (Phase 3.3B) ────────────────────────────
    if has_payment_events and total_pe > 0:
        print(_header("Payment Event Semantics"))

        # Expected: payment_events << email_records (not a 1:1 mirror)
        pe_ratio = total_pe / max(total_records, 1)
        ratio_ok = pe_ratio < 0.6  # healthy: < 60% of email_records
        flag_ratio = _flag(ratio_ok, warn=(0.6 <= pe_ratio <= 0.9))
        print(f"  payment_events / email_records ratio:  {flag_ratio}  "
              f"{total_pe} / {total_records} = {pe_ratio:.0%}"
              f" {'(healthy)' if ratio_ok else '(WARNING: may be mirroring email_records)'}")

        # renewal_charge events present (Phase 3.3B fix verification)
        renewal_count = _run(conn,
            "SELECT COUNT(*) FROM payment_events WHERE event_type = 'renewal_charge'"
        )[0][0]
        has_renewal = renewal_count > 0
        if total_pe > 0:
            flag_renewal = _flag(has_renewal, warn=not has_renewal)
            print(f"  renewal_charge events:  {flag_renewal}  {renewal_count}")

        # No unknown_payment events if total is reasonable
        unknown_count = _run(conn,
            "SELECT COUNT(*) FROM payment_events WHERE event_type = 'unknown_payment'"
        )[0][0]
        unknown_ratio = unknown_count / max(total_pe, 1)
        flag_unknown = _flag(unknown_ratio < 0.1, warn=(0.1 <= unknown_ratio < 0.5))
        print(f"  unknown_payment ratio:  {flag_unknown}  "
              f"{unknown_count} / {total_pe} = {unknown_ratio:.0%}"
              f"{' (WARNING: high unknown ratio — check PatternType.NONE gate)' if unknown_ratio >= 0.5 else ''}")

        # Suspicious: ACTIVE subscriptions with ANNUAL cycle and no strong evidence
        sus_annual = _run(conn,
            """SELECT name, amount, currency, billing_cycle FROM subscriptions
               WHERE status = 'ACTIVE' AND billing_cycle = 'ANNUAL'
               AND source_provider != 'MOCK'
               ORDER BY name""")
        if sus_annual:
            print(f"\n  Suspicious ANNUAL subscriptions ({len(sus_annual)} — verify these have strong cycle evidence):")
            for row in sus_annual:
                amt = f"{row['currency']}{row['amount']:.2f}" if row['amount'] else "N/A"
                print(f"    {row['name']:<20}  {amt}  ANNUAL")

        # Currency preservation: ACTIVE subscriptions with their stored currencies
        print(f"\n  ACTIVE subscriptions by currency:")
        active_by_currency = _run(conn,
            """SELECT currency, COUNT(*) as cnt,
                      GROUP_CONCAT(name, ', ') as names
               FROM subscriptions
               WHERE status = 'ACTIVE' AND source_provider != 'MOCK'
               GROUP BY currency ORDER BY cnt DESC""")
        if active_by_currency:
            for row in active_by_currency:
                print(f"    {row['currency'] or 'NULL':<6}  {row['cnt']:>2} sub(s): {row['names']}")
        else:
            print("    (no ACTIVE subscriptions)")

    # ── Known Provider Coverage (Phase 3.4) ──────────────────────────────────
    print(_header("Known Provider Coverage"))

    # Canonical provider names to check for. These are the most common services
    # that should appear if the user has subscribed to them.
    _KNOWN_PROVIDERS = [
        "Spotify", "Netflix", "ChatGPT", "Claude", "Google One",
        "Apple", "Apple Music", "iCloud+", "GitHub", "Zoom",
        "OpenAI", "Notion", "Wolt+", "YouTube Premium",
        "LinkedIn Premium", "Grammarly", "Canva",
    ]

    found_any_providers = False
    for provider in _KNOWN_PROVIDERS:
        # Check subscriptions (any status)
        sub_count = _run(conn,
            "SELECT COUNT(*) FROM subscriptions WHERE name = ? AND source_provider != 'MOCK'",
            (provider,))[0][0]
        # Check email_records (canonical_name not stored — check by sender pattern if possible)
        # payment_events stores merchant_name which is the canonical name
        pe_count = 0
        if has_payment_events:
            pe_count = _run(conn,
                "SELECT COUNT(*) FROM payment_events WHERE merchant_name = ?",
                (provider,))[0][0]

        if sub_count > 0:
            active_sub = _run(conn,
                "SELECT status, amount, billing_cycle FROM subscriptions WHERE name = ? AND source_provider != 'MOCK' LIMIT 1",
                (provider,))[0]
            status = active_sub["status"] or "?"
            amt = _fmt_amount(active_sub["amount"])
            cycle = (active_sub["billing_cycle"] or "?")[:8]
            print(f"  FOUND   {provider:<20}  {status:<10} {amt}  {cycle}")
            found_any_providers = True
        elif pe_count > 0:
            print(f"  EVENTS  {provider:<20}  {pe_count} payment event(s), no subscription created")
            found_any_providers = True
        # else: not in DB — could be outside scan range or not subscribed

    if not found_any_providers:
        print("  (no known providers detected — run a scan first)")
    else:
        print(f"\n  Tip: Run a forensic scan (2y+ range) to maximize recall.")
        print(f"  Missing providers may be outside the current scan range.")

    # ── Unconfirmed Subscriptions Detail (Phase 3.4) ──────────────────────────
    unconfirmed_subs = _run(conn,
        """SELECT name, billing_cycle, amount, source_provider,
                  (SELECT COUNT(*) FROM email_records er WHERE er.subscription_id = s.subscription_id) AS email_count,
                  (SELECT COUNT(*) FROM payment_events pe WHERE pe.subscription_id = s.subscription_id) AS pe_count
           FROM subscriptions s
           WHERE status = 'UNKNOWN' AND source_provider != 'MOCK'
           ORDER BY name""")

    if unconfirmed_subs:
        print(_header(f"Unconfirmed Subscriptions ({len(unconfirmed_subs)})"))
        print(f"  These were detected but amount or cycle is uncertain.")
        print(f"  Edit in dashboard to confirm or delete as false positive.\n")
        for row in unconfirmed_subs:
            amt_str = "no amount" if row["amount"] is None else f"{_fmt_amount(row['amount'])}"
            cycle = row["billing_cycle"] or "?"
            emails = row["email_count"] or 0
            hint = "amount not in subject" if row["amount"] is None else "cycle unclear"
            print(f"  {row['name']:<22}  {amt_str}  {cycle:<8}  ({emails} email(s), {hint})")

    # ── Attachment Review Queue (Phase 3.4) ───────────────────────────────────
    if has_payment_events:
        attach_count = _run(conn,
            "SELECT COUNT(*) FROM payment_events WHERE needs_attachment_review = 1")[0][0]
        if attach_count > 0:
            print(_header(f"Attachment Review Queue ({attach_count})"))
            print(f"  These events have a known merchant but amount is in an attachment.")
            print(f"  Amount extraction from PDF/HTML not yet implemented (Phase 3.5).\n")
            attach_rows = _run(conn,
                """SELECT merchant_name, event_type, event_date
                   FROM payment_events WHERE needs_attachment_review = 1
                   ORDER BY event_date DESC""")
            for row in attach_rows:
                date_str = (row["event_date"] or "?")[:10]
                print(f"  {date_str}  {row['merchant_name']:<22}  {row['event_type']}")

    # ── UI Visibility Checklist (Phase 3.3B) ──────────────────────────────────
    print(_header("UI Visibility Checklist"))

    import os as _os
    _project_root = Path(__file__).resolve().parent.parent

    # Check 1: payment-events router exists
    pe_router_path = _project_root / "backend" / "api" / "routers" / "payment_events.py"
    _flag_pe_router = _flag(pe_router_path.exists())
    print(f"  GET /api/payment-events endpoint:      {_flag_pe_router}  "
          f"({'found' if pe_router_path.exists() else 'MISSING — create backend/api/routers/payment_events.py'})")

    # Check 2: PaymentEventsTable component exists
    pet_path = _project_root / "frontend" / "src" / "components" / "PaymentEventsTable.tsx"
    _flag_pet = _flag(pet_path.exists())
    print(f"  Frontend PaymentEventsTable component: {_flag_pet}  "
          f"({'found' if pet_path.exists() else 'MISSING — create frontend/src/components/PaymentEventsTable.tsx'})")

    # Check 3: format.ts helper exists (currency symbols)
    fmt_path = _project_root / "frontend" / "src" / "lib" / "format.ts"
    _flag_fmt = _flag(fmt_path.exists())
    print(f"  Currency format helper (format.ts):    {_flag_fmt}  "
          f"({'found' if fmt_path.exists() else 'MISSING — hardcoded $ symbols in use'})")

    # Check 4: hardcoded "$" in SpendingSummary
    summary_tsx = _project_root / "frontend" / "src" / "components" / "SpendingSummary.tsx"
    hardcoded_dollar = False
    if summary_tsx.exists():
        content = summary_tsx.read_text(encoding="utf-8")
        hardcoded_dollar = '`$${summary.total_monthly_cost' in content
    _flag_dollar = _flag(not hardcoded_dollar)
    print(f"  No hardcoded $ in SpendingSummary:     {_flag_dollar}  "
          f"({'clean' if not hardcoded_dollar else 'WARN: hardcoded $ found — ILS will show as $'})")

    # Check 5: payment_events/email_records ratio (computed above if table exists)
    if has_payment_events and total_pe > 0:
        ratio_ok_final = (total_pe / max(total_records, 1)) < 0.6
        _flag_ratio_final = _flag(ratio_ok_final, warn=not ratio_ok_final)
        print(f"  payment_events not mirroring emails:   {_flag_ratio_final}  "
              f"{total_pe} events vs {total_records} records")

    # Phase 3.4 checks
    sub_router_path = _project_root / "backend" / "api" / "routers" / "subscriptions.py"
    _has_crud = False
    if sub_router_path.exists():
        sub_router_content = sub_router_path.read_text(encoding="utf-8")
        _has_crud = "create_subscription_manual" in sub_router_content and "delete_subscription" in sub_router_content
    _flag_crud = _flag(_has_crud)
    print(f"  Manual CRUD endpoints (create/delete):  {_flag_crud}  "
          f"({'found' if _has_crud else 'MISSING — POST/DELETE /api/subscriptions not implemented'})")

    sub_table_path = _project_root / "frontend" / "src" / "components" / "SubscriptionTable.tsx"
    _has_edit = False
    if sub_table_path.exists():
        st_content = sub_table_path.read_text(encoding="utf-8")
        _has_edit = "EditRow" in st_content and "Unconfirmed" in st_content
    _flag_edit = _flag(_has_edit)
    print(f"  SubscriptionTable edit+sections:        {_flag_edit}  "
          f"({'found' if _has_edit else 'MISSING — edit/delete/create buttons not implemented'})")

    wolt_in_tier1 = False
    sender_list_path = _project_root / "backend" / "detector" / "sender_list.py"
    if sender_list_path.exists():
        wolt_in_tier1 = "wolt.com" in sender_list_path.read_text(encoding="utf-8")
    _flag_wolt = _flag(wolt_in_tier1)
    print(f"  Wolt in Tier 1 sender list:             {_flag_wolt}  "
          f"({'found' if wolt_in_tier1 else 'MISSING — Wolt+ not detectable in quick mode'})")

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

    # Data quality — only meaningful when GMAIL subscriptions exist
    gmail_sub_count = _run(conn,
        "SELECT COUNT(*) FROM subscriptions WHERE source_provider='GMAIL'")[0][0]
    if gmail_sub_count == 0:
        checks.append(("Subscriptions with amount", None, "N/A — no subscriptions detected yet"))
        checks.append(("first_charge_date coverage", None, "N/A — no subscriptions detected yet"))
    else:
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

    # Date ordering integrity (first_charge_date must be <= last_charge_date)
    date_inversion_count = _run(conn,
        """SELECT COUNT(*) FROM subscriptions
           WHERE source_provider='GMAIL'
           AND first_charge_date IS NOT NULL
           AND last_charge_date IS NOT NULL
           AND first_charge_date > last_charge_date""")[0][0]
    checks.append((
        "Date ordering (first <= last)",
        None if date_inversion_count > 0 else True,
        f"{date_inversion_count} inverted (first > last)" if date_inversion_count > 0 else "all correct"
    ))

    # ACTIVE subscriptions must have an amount (Phase 2.8 gate)
    active_no_amount = _run(conn,
        """SELECT COUNT(*) FROM subscriptions
           WHERE status='ACTIVE' AND amount IS NULL AND source_provider='GMAIL'""")[0][0]
    checks.append((
        "ACTIVE subs with no amount",
        active_no_amount == 0,
        f"{active_no_amount} ACTIVE row(s) with NULL amount" if active_no_amount
        else "all ACTIVE rows have amount"
    ))

    for label, ok, detail in checks:
        flag_str = _flag(ok is True, warn=(ok is None))
        print(f"  {label:<38} {flag_str:<5}  ({detail})")

    print()

    # ── Phase 3.7: Attachment / PDF coverage ────────────────────────────────────
    # Counts and coded reason tokens only — never raw PDF text (which is never stored).
    has_att_table = _run(
        conn, "SELECT name FROM sqlite_master WHERE type='table' AND name='email_attachments'"
    )
    if has_att_table:
        print(_header("ATTACHMENT / PDF COVERAGE"))

        total_att = _run(conn, "SELECT COUNT(*) FROM email_attachments")[0][0]
        emails_with_att = _run(
            conn,
            "SELECT COUNT(DISTINCT email_record_id) FROM email_attachments "
            "WHERE email_record_id IS NOT NULL",
        )[0][0]
        needs_review = _run(
            conn, "SELECT COUNT(*) FROM payment_events WHERE needs_attachment_review=1"
        )[0][0]
        print(f"  Attachments seen:                {total_att}")
        print(f"  Emails with attachments:         {emails_with_att}")
        print(f"  Payment events needing review:   {needs_review}")

        print("  By detected type:")
        for t, c in _run(
            conn,
            "SELECT detected_attachment_type, COUNT(*) FROM email_attachments "
            "GROUP BY detected_attachment_type ORDER BY COUNT(*) DESC",
        ):
            print(f"    {str(t):<18} {c}")

        print("  By processing status:")
        for s, c in _run(
            conn,
            "SELECT processing_status, COUNT(*) FROM email_attachments "
            "GROUP BY processing_status ORDER BY COUNT(*) DESC",
        ):
            print(f"    {str(s):<18} {c}")

        af_total = _run(conn, "SELECT COUNT(*) FROM attachment_extracted_fields")[0][0]
        af_with_amount = _run(
            conn, "SELECT COUNT(*) FROM attachment_extracted_fields WHERE amount IS NOT NULL"
        )[0][0]
        print(f"  PDF evidence rows:               {af_total} ({af_with_amount} with an amount)")

        print("  By extraction status:")
        for s, c in _run(
            conn,
            "SELECT extraction_status, COUNT(*) FROM attachment_extracted_fields "
            "GROUP BY extraction_status ORDER BY COUNT(*) DESC",
        ):
            print(f"    {str(s):<18} {c}")

        def _tally(column: str):
            counts: dict[str, int] = {}
            for row in _run(
                conn,
                f"SELECT {column} FROM attachment_extracted_fields "
                f"WHERE {column} IS NOT NULL AND {column} != ''",
            ):
                for tok in str(row[0]).split(";"):
                    if tok:
                        counts[tok] = counts.get(tok, 0) + 1
            return sorted(counts.items(), key=lambda kv: -kv[1])

        ev_tally = _tally("evidence_reasons")
        if ev_tally:
            print("  PDF-derived evidence by reason:")
            for tok, c in ev_tally:
                print(f"    {tok:<30} {c}")
        pen_tally = _tally("penalty_reasons")
        if pen_tally:
            print("  PDF parse / penalty reasons:")
            for tok, c in pen_tally:
                print(f"    {tok:<30} {c}")

        failed = _run(
            conn, "SELECT COUNT(*) FROM email_attachments WHERE processing_status='PARSE_FAILED'"
        )[0][0]
        unexplained = _run(
            conn,
            "SELECT COUNT(*) FROM attachment_extracted_fields "
            "WHERE amount IS NOT NULL AND (evidence_reasons IS NULL OR evidence_reasons='')",
        )[0][0]
        print(f"  PDF parse failures:              {failed}")
        print(f"  Unexplained PDF candidates:      {unexplained}")

        corr = _run(
            conn,
            "SELECT uc.correction_type, COUNT(*) FROM user_corrections uc "
            "WHERE uc.email_record_id IN ("
            "  SELECT DISTINCT email_record_id FROM attachment_extracted_fields "
            "  WHERE email_record_id IS NOT NULL) "
            "GROUP BY uc.correction_type ORDER BY COUNT(*) DESC",
        )
        if corr:
            print("  User corrections on PDF-derived rows:")
            for ct, c in corr:
                print(f"    {str(ct):<18} {c}")
        else:
            print("  User corrections on PDF-derived rows: none")

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
