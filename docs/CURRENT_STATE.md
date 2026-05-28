# Subscription Tracker — Current State

**Last updated:** 2026-05-28  
**Phase:** Phase 3.0 complete — HTML body extraction fixed

---

## What Works

- Gmail OAuth (read-only, `gmail.readonly` scope only)
- Multi-pass forensic scan (6 passes, background job with progress polling)
- Detection pipeline: Tier 1/2 sender list, pattern matching, confidence scoring
- Lifecycle events: subscription_started, renewal_charge, cancellation, trial_started, etc.
- Source filtering: MOCK vs GMAIL separated in all DB queries and API endpoints
- Validation report: `python scripts/validation_report.py`
- Background scan jobs with SQLite persistence (scan_jobs table)
- **Phase 3.0 fixes** (complete, 2026-05-28):
  - `_strip_html()` now skips `<style>`, `<script>`, `<head>` content — Bug A
  - `_AMOUNT_RE` allows optional whitespace between currency symbol and digits — Bug B
  - `_extract_body_text()` max_chars raised 2000 → 5000 — Bug C
  - Migration 005: QUARTERLY added to billing_cycle CHECK constraint

---

## Latest Validation Result (pre-Phase-3.0 forensic + 1y scan)

- 3 subscriptions found: Google, Spotify, Zoom — all `UNKNOWN` status, N/A amount
- 18 DETECTED emails had 0 amounts extracted (HTML body bugs A/B/C caused this)
- 8 FLAGGED emails had amounts (plain-text subjects from unknown senders)
- Phase 3.0 fixes should resolve all 3 UNKNOWN → ACTIVE on next forensic scan

---

## Known Problems

- Google/Spotify/Zoom show UNKNOWN until a forensic scan is run post-Phase-3.0
- Google canonical name is "Google" (not specific product e.g. "Google One")
- Spotify plan variants ("Premium Student", "Family") not distinguished
- Zoom "Payment Processed" billing cycle not detected (no cycle keyword in subject)

---

## Test Status

- **388 passed, 1 skipped** (token file test — no `token.json` on disk)
- Privacy gate: **17 passed, 1 skipped** — all green

---

## Verification Commands

```bash
# Privacy gate — run before any commit; must always be 100%
python -m pytest tests/privacy/ -v

# Full suite — run once after all code changes are complete
python -m pytest tests/ -q

# Targeted tests — run while iterating on a single module
python -m pytest tests/unit/test_<module>.py -q

# Validation report against live DB
python scripts/validation_report.py

# Re-run forensic scan to verify Phase 3.0 UNKNOWN → ACTIVE
# Via dashboard: forensic mode + 1y range
# Via API: POST /api/scan/start?mode=forensic&scan_range=1y
```

---

## Privacy / Security Constraints (Non-Negotiable)

- **Gmail scope:** `gmail.readonly` only — never add a second scope
- **Body access:** `format=metadata` in `_fetch_metadata()`; `format=full` only in `_fetch_body()` (ephemeral, discarded immediately — never stored or logged)
- **Tokens:** keyring or AES-256 encrypted file only — never plaintext
- **No bank integration** — no Plaid, Teller, scraping, bank credentials
- **No external telemetry** — no analytics SDKs, no error-reporting services
- **No AI/LLM classification** — deterministic rules only (MVP constraint)
- **`tests/privacy/` must never fail** — failing privacy tests block all other work

---

## Key Files

| Area | File |
|------|------|
| Detection pipeline | `backend/detector/detector.py` |
| Confidence scoring | `backend/detector/confidence_scorer.py` |
| Sender tier list | `backend/detector/sender_list.py` |
| Pattern matching | `backend/detector/pattern_library.py` |
| Amount extraction | `backend/parser/amount_extractor.py` |
| Cycle detection | `backend/parser/cycle_detector.py` |
| Body fetch + strip | `backend/sources/gmail.py` (`_fetch_body`, `_extract_body_text`, `_strip_html`) |
| DB schema/CRUD | `backend/db/setup.py` |
| Migrations | `backend/db/migrations/00*.sql` |
| Scan router | `backend/api/routers/scan.py`, `scan_async.py` |
| Validation script | `scripts/validation_report.py` |

---

## Next Planned Phase

**Phase 3.1** — `payment_events` table + event-to-subscription linking  
See `docs/NEXT_STEPS.md` for the full 3-phase roadmap.
