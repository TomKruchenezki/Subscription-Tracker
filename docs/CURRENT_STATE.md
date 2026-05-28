# Subscription Tracker — Current State

**Last updated:** 2026-05-28  
**Phase:** Phase 3.3B complete — payment event semantics, native currency display, GET /api/payment-events, frontend PaymentEventsTable, billing cycle body_text restriction

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
- **Phase 3.1 features** (complete, 2026-05-28):
  - `payment_events` table (migration 006) — intermediate financial event store, INSERT OR IGNORE idempotency, UUID5 event_id
  - Currency bug fixes — three-part fix eliminating ILS→USD corruption:
    - Python: `currency = parsed["currency"]` (no `or "USD"` — None propagates)
    - INSERT: `COALESCE(?, 'USD')` — new rows default to USD when no currency extracted
    - UPDATE: `COALESCE(?, currency)` — existing rows (e.g., ILS) preserved across rescans
  - Multi-currency summary — `monthly_costs_by_currency` dict in `get_summary()` response
  - Subscription linking — `payment_events.subscription_id` foreign key to `subscriptions`
  - One-time payment detection — `is_one_time_candidate` / `is_recurring_candidate` flags
  - Refund and cancellation event types (`refund`, `cancellation`, `unknown_payment`)
- **Phase 3.3B fixes** (complete, 2026-05-28):
  - **payment_events semantics**: `_map_payment_event_type()` now derives from email_record event_type (which carries full context: was_created, tier, disposition), not from PatternType alone. Eliminates the old bug where PatternType.NONE → "unknown_payment" caused payment_events to mirror every email_record.
  - **`renewal_charge` event type**: RENEWAL receipts now correctly produce `event_type="renewal_charge"` (first receipt = "subscription_charge", subsequent = "renewal_charge"). Migration 007 adds `renewal_charge` to the CHECK constraint and drops the incorrect Phase 3.3 data.
  - **Payment event creation gate**: FLAGGED emails only produce payment_events when both amount AND event_type are confirmed. PatternType.NONE FLAGGED emails produce no event.
  - **is_recurring_candidate fix**: Only set to 1 when `pe_event_type in ("subscription_charge", "renewal_charge") AND amount is not None`. No amount = no recurring signal.
  - **Billing cycle body_text restriction**: Weak cycle patterns (standalone "annual", "weekly", "monthly" + billing context) are suppressed for body_text. Only strong positional patterns (/year, per month, /week, etc.) fire from body_text. Fixes Spotify $1.07/mo root cause (body_text "annual" + "subscription" was firing ANNUAL on a monthly charge).
  - **GET /api/payment-events endpoint**: New router at `backend/api/routers/payment_events.py`. Filters by `event_type`, `is_recurring_candidate`, `is_one_time_candidate`, `limit`. Returns safe structured fields only — no raw email content.
  - **Native currency symbols**: `frontend/src/lib/format.ts` provides `formatCurrency(amount, currency)` and `formatMonthly(amount, currency)`. ILS displays as ₪, USD as $, EUR as €. SpendingSummary and SubscriptionTable both updated.
  - **Per-currency breakdown**: SpendingSummary shows `₪12.90/mo · $9.99/mo` when multiple currencies are tracked.
  - **PaymentEventsTable component**: New `frontend/src/components/PaymentEventsTable.tsx` renders payment events in dashboard. Safe fields only (no subject, sender, snippet, body).
  - **Product acceptance guardrails**: Three new rules in CLAUDE.md requiring user-visible acceptance criteria before phase completion. New `.claude/agents/product-acceptance-reviewer.md` agent.
  - **Validation report**: Two new sections — "Payment Event Semantics Check" and "UI Visibility Checklist".

---

## Latest Validation Result (pre-Phase-3.3B; next scan will reflect fixes)

- 3 subscriptions found: Google, Spotify, Zoom — all `UNKNOWN` status, N/A amount
- 18 DETECTED emails had 0 amounts extracted (HTML body bugs A/B/C caused this)
- 8 FLAGGED emails had amounts (plain-text subjects from unknown senders)
- Phase 3.0 fixes should resolve all 3 UNKNOWN → ACTIVE on next forensic scan

---

## Known Problems

- Google/Spotify/Zoom may show UNKNOWN until a forensic scan is run with Phase 3.3B fixes
- Google canonical name is "Google" (not specific product e.g. "Google One")
- Spotify plan variants ("Premium Student", "Family") not distinguished
- Zoom "Payment Processed" billing cycle not detected (no cycle keyword in subject)
- Subject-line-only amount extraction misses amounts buried in HTML body for some providers
  (Phase 3.2 provider-specific parsers will address this)
- A fresh forensic scan is required to repopulate `payment_events` with correct semantics
  (migration 007 dropped the incorrect Phase 3.3 data)

---

## Test Status

- **475 passed, 1 skipped** (token file test — no `token.json` on disk)
- Privacy gate: **18 passed, 1 skipped** — all green
- Phase 3.3B tests added (25 new tests):
  - `test_cycle_detector.py` — 9 tests: body_text weak pattern suppression, Spotify regression
  - `test_detector.py` — 6 tests: payment event semantics, renewal_charge, NONE → no event, is_recurring_candidate
  - `test_database.py` — 5 tests: get_payment_events filtering, renewal_charge stored, no raw content
  - `test_api_payment_events.py` — 6 tests: GET /api/payment-events endpoint, safe fields, filtering

---

## Verification Commands

```bash
# Privacy gate — run before any commit; must always be 100%
python -m pytest tests/privacy/ -v

# Full suite — run once after all code changes are complete
python -m pytest tests/ -q

# Targeted tests — run while iterating on a single module
python -m pytest tests/unit/test_<module>.py -q

# TypeScript check (run after any .ts/.tsx file changes)
cd frontend && npx tsc --noEmit

# Validation report against live DB
python scripts/validation_report.py

# Re-run forensic scan to verify Phase 3.3B fixes:
#   - payment_events count << email_records (not mirrored)
#   - Spotify shows ₪ symbol, not $
#   - $1.07/mo bug is gone
#   - PaymentEventsTable visible in dashboard
# Via dashboard: forensic mode + 2y range
# Via API: POST /api/scan/start?mode=forensic&scan_range=2y
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
- **`payment_events` privacy rule** — table must never contain: subject, sender_address, snippet, body_text, body_html, short_evidence. `merchant_name` must be canonical (e.g., "Spotify"), not a raw sender address.

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
| Payment events (v1) | `backend/db/migrations/006_payment_events.sql` |
| Payment events (v2) | `backend/db/migrations/007_payment_events_v2.sql` |
| Payment events API | `backend/api/routers/payment_events.py` |
| Currency formatting | `frontend/src/lib/format.ts` |
| Payment events UI | `frontend/src/components/PaymentEventsTable.tsx` |
| Scan router | `backend/api/routers/scan.py`, `scan_async.py` |
| Validation script | `scripts/validation_report.py` |

---

## Next Planned Phase

**Phase 3.2** — Provider-specific parsers  
Target: improve amount extraction for providers whose billing amounts appear only in HTML body (Google One, Zoom, etc.), not in subject lines.  
See `docs/NEXT_STEPS.md` for the full roadmap.

**Before Phase 3.2**: run a forensic scan (2y range) to verify Phase 3.3B fixes produce correct payment_events semantics and the dashboard shows ₪ symbols correctly.
