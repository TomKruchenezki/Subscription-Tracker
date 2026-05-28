# Subscription Tracker — Current State

**Last updated:** 2026-05-28  
**Phase:** Phase 3.4 complete — provider expansion (Wolt+, Apple Music), manual CRUD, review queue UX, custom scan range, needs_attachment_review flag

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
- **Phase 3.4 features** (complete, 2026-05-28):
  - **Wolt/Wolt+ Tier 1**: wolt.com, mail.wolt.com, wolt.fi, wolt.de, wolt.at, wolt.il added to TIER_1 in sender_list.py. wolt.com added to Gmail Pass 1 domain filter — Wolt+ now detected in quick/deep mode (not only forensic).
  - **Apple product disambiguation**: `resolve_sender()` in sender_resolver.py now accepts `subject` parameter. Apple sender + "Apple Music" in subject → "Apple Music"; "iCloud" → "iCloud+"; "App Store" → "App Store"; "iTunes" → "Apple Music"; "Apple TV+" → "Apple TV+"; "Apple One" → "Apple One". detector.py always calls `resolve_sender(sender, subject)` for accurate product names.
  - **needs_attachment_review flag**: migration 008 adds this column to payment_events. Set to 1 when tier=1 + RECEIPT/RENEWAL pattern + amount=None. Marks events where charge is real but amount is in an attached PDF (Phase 3.5 queue). Visible in PaymentEventsTable as 📎 indicator.
  - **Manual subscription CRUD**: `POST /api/subscriptions` (create, 201), `POST /api/subscriptions/{id}/update` (update via POST not PUT — CORS allows GET/POST/DELETE only), `DELETE /api/subscriptions/{id}` (204). DB functions: `create_subscription_manual()`, `update_subscription_fields()`, `delete_subscription()`.
  - **Payment event link/unlink**: `POST /api/payment-events/{id}/link` (body: `{"subscription_id": "..."}`) and `POST /api/payment-events/{id}/unlink`. DB functions: `link_payment_event()`, `unlink_payment_event()`.
  - **unconfirmed_count in summary**: `get_summary()` now returns `unconfirmed_count` (count of UNKNOWN-status subscriptions). SpendingSummary shows "—" instead of "$0.00" when all subs are UNKNOWN, with "N unconfirmed subscriptions" subtext.
  - **SubscriptionTable redesign**: Two sections — "Active subscriptions" (ACTIVE/TRIAL) and "Unconfirmed candidates" (UNKNOWN/PAUSED). Each row has ✏️ Edit and 🗑️ Delete buttons. "+ Add subscription" creates a new subscription manually. Inline edit form (EditRow) with all editable fields. Cancelled shown in a collapsed `<details>` section.
  - **ReviewQueue redesign**: FLAGGED email_records now grouped by event_type into 5 categories: Subscription candidates / Unknown payments / Refunds / Cancellations / Trials. Each row has "✓ Confirm" (opens modal pre-filled from record data → creates subscription) and "✕ Dismiss" (hides from view, local state only). Amount display bug fixed: `${currency}${amount}` → `formatCurrency()`.
  - **PaymentEventsTable redesign**: Link/Unlink actions per row. 📎 indicator for needs_attachment_review=1 events. Attachment count summary banner.
  - **Custom scan date range**: SpendingSummary now includes "Custom range…" option in the scan range dropdown. When selected, shows From/To date inputs. page.tsx passes `date_from`/`date_to` to the scan API (backend already supports these parameters).
  - **validation_report.py**: New "Known Provider Coverage" section (checks Spotify, Netflix, Wolt+, etc. in DB), "Unconfirmed Subscriptions Detail" section (lists UNKNOWN-status subs), "Attachment Review Queue" section (events with needs_attachment_review=1). Enhanced UI Visibility Checklist with Phase 3.4 checks (manual CRUD, SubscriptionTable sections, Wolt in Tier 1).
  - **subscription-recall-reviewer agent**: New `.claude/agents/subscription-recall-reviewer.md` focused on false-negative risk assessment.
  - **README.md**: Full rewrite covering current architecture, all features, API reference, scan modes, manual corrections guide, provider coverage table, and known limitations.
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

- Google/Spotify/Zoom may show UNKNOWN until a forensic scan is run with Phase 3.3B+3.4 fixes applied
- Google canonical name is "Google" (not specific product e.g. "Google One")
- Spotify plan variants ("Premium Student", "Family") not distinguished
- Zoom "Payment Processed" billing cycle not detected (no cycle keyword in subject)
- Subject-line-only amount extraction misses amounts buried in HTML body for some providers → marked as needs_attachment_review=1 in payment_events (Phase 3.5 will extract these)
- Wolt food delivery receipts (non-subscription one-time orders) may appear as Wolt+ candidates since they come from the same domain. User can delete false positives.
- Review Queue "Dismiss" action is local-state only — dismissed records reappear on page refresh (no DB persistence for dismissals in Phase 3.4)

---

## Test Status

- **515 passed, 1 skipped** (token file test — no `token.json` on disk)
- Privacy gate: **18 passed, 1 skipped** — all green
- Phase 3.4 tests added (40 new tests):
  - `test_sender_list.py` — 5 new tests: Wolt Tier 1 coverage (wolt.com, mail.wolt.com, wolt.fi, wolt.de, wolt.il)
  - `test_sender_resolver.py` — 13 new tests: Apple product disambiguation (Apple Music, iCloud+, App Store, iTunes, Apple TV+, Apple One, generic fallback), Wolt sender resolution
  - `test_api_subscriptions.py` — NEW file, 13 tests: POST /api/subscriptions (create, 201, validation), POST /{id}/update (amount, status, cycle), DELETE /{id} (204, DB removal, 404)
  - `test_detector.py` — 7 new tests: needs_attachment_review flag (Tier 1 no amount → 1, with amount → 0, Tier 0 → 0), Wolt+ detected, Apple Music subscription named correctly
  - `test_api_payment_events.py` — 6 new tests: link/unlink endpoints (200, 404), needs_attachment_review field in response
- Phase 3.3B tests (25 tests, still passing):
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
| Sender resolver (w/ Apple) | `backend/parser/sender_resolver.py` |
| Amount extraction | `backend/parser/amount_extractor.py` |
| Cycle detection | `backend/parser/cycle_detector.py` |
| Body fetch + strip | `backend/sources/gmail.py` |
| DB schema/CRUD | `backend/db/setup.py` |
| Migrations | `backend/db/migrations/00*.sql` |
| Payment events (v2 schema) | `backend/db/migrations/007_payment_events_v2.sql` |
| Attachment review flag | `backend/db/migrations/008_needs_attachment_review.sql` |
| Subscriptions API | `backend/api/routers/subscriptions.py` |
| Payment events API | `backend/api/routers/payment_events.py` |
| Currency formatting | `frontend/src/lib/format.ts` |
| API client | `frontend/src/lib/api.ts` |
| TypeScript types | `frontend/src/types/api.ts` |
| Dashboard page | `frontend/src/app/page.tsx` |
| Review Queue page | `frontend/src/app/review/page.tsx` |
| Spending summary + scan controls | `frontend/src/components/SpendingSummary.tsx` |
| Subscription table (w/ CRUD) | `frontend/src/components/SubscriptionTable.tsx` |
| Review queue (w/ categories) | `frontend/src/components/ReviewQueue.tsx` |
| Payment events UI | `frontend/src/components/PaymentEventsTable.tsx` |
| Scan router | `backend/api/routers/scan.py`, `scan_async.py` |
| Validation script | `scripts/validation_report.py` |

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
```

## Next Planned Phase

**Phase 3.5** — PDF/attachment amount extraction, reprocessing mode, user corrections table

Target: extract amounts from payment_events where `needs_attachment_review=1`. These are Tier 1 events where the charge is confirmed but amount is in an attached PDF or HTML body.

Before starting Phase 3.5: run a forensic scan (2y range) with Phase 3.4 fixes applied. Verify:
- Wolt+ appears in results (recall test)
- Apple Music shows separately from generic "Apple" (disambiguation test)
- SubscriptionTable shows Active vs Unconfirmed sections
- Review Queue is categorized (not a flat list)
- Custom date range picker appears in scan controls
- Known Provider Coverage section in validation_report shows expected providers
