# Subscription Tracker — Current State

**Last updated:** 2026-06-01  
**Phase:** Phase 3.8 complete — real-scan cleanup & usability. Builds on Phase 3.7 (safe PDF/attachment parsing).

---

## What Works

- **Phase 3.8 features** (complete, 2026-06-01):
  - **Weak cycle gate.** `detect_cycle()` returns `CycleResult(cycle, cycle_source, cycle_confidence)`.
    Tier 1 provider + WEAK cycle inference (context-word match) → `billing_cycle` overridden to
    UNKNOWN. Fixes Spotify ₪12.90 showing as ANNUAL when subject has `/mo` (strong wins).
    `cycle_confidence` values: `STRONG` (positional patterns) | `WEAK` (context words) | `NONE`.
  - **Payment processor separation.** `PROCESSOR_DOMAINS` in `sender_list.py` lists known Israeli
    and global payment processors (Cardcom, Z-Credit, Morning/iCount, RavPass, Grow, Tranzila,
    Paylink, Meshulam, Priority, Bill.com, QuickBooks, Payoneer). Processor emails:
    → stored as `one_time_charge` / `unknown_payment` (never IGNORED, never subscriptions)
    → `is_processor_email=1`, `payment_processor` set, `merchant_name_candidate` from PDF or None
    → hidden from subscription Review Queue by default (`exclude_processor_rows=True`)
    → visible in Payment Events; all correction actions available
    → processor name never used as merchant name
  - **Migration 012 (schema_version 13):** 7 new columns on `email_records`:
    `sender_domain`, `payment_processor`, `merchant_name_candidate`,
    `is_processor_email`, `gmail_account_id`, `cycle_source`, `cycle_confidence`.
    Pre-3.8 rows have NULL for new columns; re-scan populates them.
  - **Multi-account visibility.** `account_aliases: list[str]` on subscription API responses
    (all contributing accounts, not just one). ReviewQueue now has an account dropdown filter
    (only shown when > 1 alias present). SubscriptionTable shows account badge per row,
    "multiple accounts" when > 1 alias. PaymentEventsTable already had account_alias.
  - **Timezone display.** All UI dates use `formatDateLocal()` (browser `Intl.DateTimeFormat`,
    local timezone). Replaces raw `.slice(0,10)` and `toLocaleDateString()`. Stored UTC unchanged.
  - **Stale PDF banner fixed.** `PaymentEventsTable` attachment count now only counts events
    with `needs_attachment_review=1 AND amount IS NULL`. Previously counted all flagged events
    including those where PDF extraction already filled the amount.
  - **Validation report Phase 3.8 sections:** processor stats, one-time leakage, PDF extraction
    rate, weak cycle count, pre-3.8 untracked rows, dual UTC/local timestamp format.
    `APP_TIMEZONE` env var (default `Asia/Jerusalem`).

- **Phase 3.7 features** (complete, 2026-06-01):
  - **Safe PDF/attachment parsing.** In forensic mode, PDF invoices/receipts on scanned
    emails are parsed **transiently**: `messages.attachments.get` → bytes (in memory) →
    `pdfminer.six` text (in memory) → structured fields → bytes & text discarded. No raw
    PDF text/bytes are ever stored, logged, or returned. Uses the existing `gmail.readonly`
    scope — **no scope change**.
  - **New dependency:** `pdfminer.six==20260107` (pure-Python; deps already pinned).
  - **Migration 011** (schema_version 12): `email_attachments` (metadata: filename,
    mime_type, size, detected_attachment_type, processing_status) + `attachment_extracted_fields`
    (structured: provider, amount, currency, invoice/payment dates, billing period,
    inferred_cycle, tax, invoice_number, + coded `evidence_reasons`/`missing_evidence`/
    `penalty_reasons`/`subscription_indicators`, extraction_status). No raw-text column.
  - **`backend/parser/pdf_extractor.py`** — `classify_attachment()` + `extract_pdf_fields()`
    (reuses `amount_extractor`/`cycle_detector`; refund/cancellation/trial/auto-renew
    detection; never raises; never returns raw text).
  - **Detector integration:** a parsed PDF fills a missing amount/cycle and feeds the
    Phase 3.6 explanation fields. **Guardrail:** a PDF *receipt alone* never reaches
    CONFIRMED (no cycle ⇒ no confirmation); a refund PDF never fills a charge amount.
  - **`gmail.py`:** `_extract_attachment_parts()` (no new call — from the existing
    `format=full` payload) + `_fetch_attachment_bytes()` (sole `attachments.get` caller,
    transient, size-guarded) + `process_attachments()` (one bad PDF never aborts a scan).
  - **Correction-aware:** PDF-derived rows flow through the same user_corrections as
    everything else. Added `is_event_marked_one_time()` so a one-time mark survives
    reprocess (no resubscription); reprocess replays stored PDF evidence (no Gmail refetch).
  - **API:** `GET /api/email-records/{id}/attachments` (structured fields only);
    `has_attachment` flag on email-record responses.
  - **Frontend:** ReviewQueue shows a 📎 toggle with inline PDF evidence
    (amount/provider/cycle/status/reasons); the existing evidence/missing/suggested fields
    already carry PDF notes. PaymentEventsTable's amount + decision_reason reflect PDF data.
  - **validation_report.py:** new "ATTACHMENT / PDF COVERAGE" section (counts + coded
    reasons; parse failures; unexplained PDF candidates; corrections on PDF-derived rows).

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
- **Phase 3.5 features** (complete, 2026-05-29):
  - **user_corrections table** (migration 009): Audit trail for DISMISSED_EMAIL, CONFIRMED_SUB, REJECTED_SUB, RELABELED corrections. Persists dismiss actions across page refreshes.
  - **email_records.user_dismissed** (migration 009): Fast-filter flag for dismissed Review Queue items. No JOIN needed on hot paths.
  - **scan_jobs.last_checkpoint_idx** (migration 009): After each batch, stores the last processed index into collected_ids[]. Interrupted forensic scans can resume from the checkpoint rather than restarting from 0.
  - **POST /api/email-records/{id}/dismiss**: Persists Review Queue dismissal to DB. Sets `user_dismissed=1` and inserts DISMISSED_EMAIL correction.
  - **GET /api/email-records/dismissed-ids**: Returns list of dismissed record IDs for ReviewQueue.tsx to pre-populate on page load.
  - **GET /api/email-records?include_dismissed**: Default excludes dismissed records. Pass `include_dismissed=true` to include them (for validation report, etc.).
  - **ReviewQueue.tsx**: Loads dismissed IDs from DB on mount (useEffect). handleDismiss() persists via API before local state update. Graceful degradation if API fails — still dismisses locally.
  - **scripts/reprocess_email_records.py**: New script that reads email_records, deletes their payment_events, and re-runs the detector with current rules. Supports --dry-run, --provider, --since flags. Does not fetch from Gmail; body_text/snippet remain None. Privacy-safe: uses only stored metadata.
  - **Multi-account scanning**: scan_async.py now loops over all active Gmail accounts (get_all_active_gmail_accounts()) instead of just the first one. De-duplicates message IDs across accounts.
  - **setup.py**: get_all_active_gmail_accounts(), dismiss_email_record(), get_dismissed_email_ids(), insert_user_correction(), get_user_corrections() functions added.
  - **get_email_records() include_dismissed param**: Default excludes user_dismissed=1 rows from all queries.
  - **EmailRecordResponse model**: Added user_dismissed field (0 or 1).
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

- **Pre-3.8 email_records** have `gmail_account_id = NULL`. These show as "Unknown account" in the UI. Re-scan to populate.
- **Multi-account body fetch:** scanning fetches all accounts' message IDs but uses the first account's credentials for body fetch. If a message ID belongs to a second account, body fetch may fail silently. Full per-account routing is future work.
- Review Queue "Show all" (local view) button only resets local dismissed state — persisted dismissals in DB remain (need separate UI to un-dismiss if desired)
- Google canonical name is "Google" (not specific product e.g. "Google One")
- Spotify plan variants ("Premium Student", "Family") not distinguished
- Zoom "Payment Processed" billing cycle not detected (no cycle keyword in subject)
- Wolt food delivery receipts (non-subscription one-time orders) may appear as Wolt+ candidates since they come from the same domain. User can delete false positives.
- Image/scanned PDFs are not OCR'd — text-based PDFs only.

---

## Test Status

- **617 passed, 1 skipped** (token file test — no `token.json` on disk)
- Privacy gate: **29 passed, 1 skipped** — all green (7 new Phase 3.8 privacy tests)
- TypeScript: `npx tsc --noEmit` clean
- Phase 3.7 tests added (+43): `test_pdf_extractor.py` (22 — extraction, classification,
  failure modes, no-raw-text), `test_detector_pdf.py` (8 — amount fill, attachment
  persistence, receipt-only guardrail, refund, idempotent re-scan), `test_pdf_corrections.py`
  (5 — blocked/relabel/confirmed-not-downgraded/one-time-survives-reprocess/dismissed-skip),
  `test_api_attachments.py` (4 — attachments endpoint, has_attachment flag, no raw-text keys),
  plus privacy tests (`test_attachment_no_raw_content.py`, `test_attachments_get_only_in_fetch_attachment_bytes`)
- Phase 3.5 tests added (21 new tests):
  - `test_api_email_records.py` — NEW file, 11 tests: dismiss endpoint (200/404), dismissed-ids list, include_dismissed filter, user_dismissed field in response
  - `test_reprocess_script.py` — NEW file, 5 tests: no email_records duplication, payment_events recreated, dry-run makes no changes, provider filter, no body_text used
  - `test_database.py` — 5 new tests: dismiss_email_record() sets flag, returns False for nonexistent, inserts correction, get_dismissed_email_ids(), get_email_records() excludes dismissed
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
- **Attachment access (Phase 3.7):** `messages.attachments.get` only in `_fetch_attachment_bytes()`; bytes + extracted PDF text are processed in memory and discarded immediately. Only structured fields (amount, currency, dates, cycle, coded reason tokens) are stored in `attachment_extracted_fields` — never raw PDF text. Same `gmail.readonly` scope.
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

## Phase 3.7 Known Limitations

- **Image/scanned PDFs are not OCR'd** — text-based PDFs only. An image-only PDF is
  recorded as `processing_status=PARSE_FAILED` / `extraction_status=NO_TEXT` (no crash).
- **No provider-specific PDF parsers yet** — extraction is generic (labeled totals, dates,
  billing periods, recurring keywords). Unusual invoice layouts may yield `NO_FIELDS`.
- **Attachment parsing is forensic-mode only** (piggybacks on the `_fetch_body` payload).
- **Reprocess replays stored PDF fields only** — raw PDF text is never stored, so
  parser improvements still require a fresh forensic scan to re-read attachments.
- Marking a single event one-time blocks subscription creation for that message on
  reprocess; the existing subscription row (if any) should be deleted by the user.

## Next Planned Phase

**Future** — Provider-specific PDF parsers, OCR for image receipts (optional, local-only),
full multi-account selector UI, AI/LLM reviewer (only after deterministic rules proven
insufficient, never sending raw content externally).

**Manual verification (requires a connected Gmail account with PDF invoices):**
Run a forensic scan, then check:
- An email whose amount is only in a PDF invoice now shows the amount (ReviewQueue 📎 → details)
- `email_attachments` / `attachment_extracted_fields` populate; no raw text stored
- `python scripts/validation_report.py` shows the "ATTACHMENT / PDF COVERAGE" section
- A PDF receipt with no recurring evidence is NOT auto-confirmed; a refund PDF is not a charge
- Mark a PDF-derived event one-time → reprocess → it is not recreated as a subscription
