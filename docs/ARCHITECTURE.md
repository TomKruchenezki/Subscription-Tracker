# Architecture

High-level map of the system. For *current* status/test counts read `docs/CURRENT_STATE.md`;
for *what to do next* read `docs/NEXT_STEPS.md`. The authoritative DB schema is the set of
migration files in `backend/db/migrations/` (this doc summarizes; it does not replace them).

---

## Data flow

```
Gmail (gmail.readonly)
  └─ metadata: From / Subject / Date  (always)
  └─ forensic mode only, transient in memory (never stored):
       body text (format=full, _fetch_body)
       PDF attachment bytes → text (messages.attachments.get, _fetch_attachment_bytes → pdfminer.six)
        ↓
  detector.process_email()  — 5 stages: tier → pattern → parse → score → disposition
        ↓
  email_records ──→ payment_events ──→ subscriptions
        │                                  ▲
        └─ email_attachments / attachment_extracted_fields (structured PDF evidence)
        ↓
  FastAPI (backend/api) ──→ Next.js dashboard (frontend)
```

`user_corrections` feeds back into `process_email()` (relabel / reject / one-time) so user
decisions persist across scans and reprocessing.

---

## Database tables

Authoritative definitions live in `backend/db/migrations/*.sql` (current schema_version: 12).
Tables (privacy rule: **no raw body / snippet / HTML / PDF text in any column**):

| Table | Purpose |
|---|---|
| `subscriptions` | Latest per-service state (amount, cycle, status, `detection_state`, `source_account_id`) |
| `email_records` | One row per processed email: disposition, `event_type`, explanation fields, `user_dismissed` |
| `payment_events` | Individual financial events (subscription_charge / renewal / refund / …), `needs_attachment_review`, `user_marked_one_time` |
| `user_corrections` | Audit + correction-awareness (DISMISSED_EMAIL / CONFIRMED_SUB / REJECTED_SUB / RELABELED / MARKED_ONE_TIME / MERGED) with `sender_address` scope |
| `scan_jobs` | Background scan progress + `last_checkpoint_idx` for resume |
| `email_attachments` | Attachment metadata (filename, mime, size, type, processing_status) — Phase 3.7 |
| `attachment_extracted_fields` | Structured PDF-derived evidence + coded reason tokens — Phase 3.7 |
| `user_settings`, `schema_version` | Local config + migration tracking |

---

## File layout

```
subscription-tracker/
  CLAUDE.md                      ← always-loaded constitution (operational)
  README.md  .env.example  .gitignore  main.py  requirements.txt  conftest.py  pytest.ini

  docs/
    CURRENT_STATE.md             ← phase, test count, known problems, verification commands (read first)
    NEXT_STEPS.md                ← short, actionable: next task + likely files/tests
    CONTEXT_MANAGEMENT.md        ← session hygiene: start / NORMAL vs DEEP / /clear / handoff
    ARCHITECTURE.md              ← this file
    PRODUCT_ACCEPTANCE.md        ← acceptance gate + explainable/correctable rules
    PRIVACY_SECURITY.md          ← data-handling policy, threat model
    GMAIL_API_PLAN.md            ← OAuth flow, fetching strategy, transient-content rules
    DATA_MODEL.md                ← schema detail (migrations are authoritative)
    DETECTION_RULES.md  TEST_PLAN.md  ROADMAP.md  PRODUCT_SPEC.md  REAL_GMAIL_SCAN_VALIDATION.md
    FUTURE_BANK_INTEGRATION.md

  .claude/agents/                ← product-architect, privacy-security-reviewer,
                                   payment-data-quality-reviewer, gmail-integration-specialist,
                                   email-parser-specialist, subscription-detection-specialist,
                                   qa-test-reviewer, product-acceptance-reviewer, subscription-recall-reviewer
  .claude/skills/                ← start-session, handoff-summary, test-and-report, git-safe-commit,
                                   real-scan-triage, phase-plan, scan-diagnosis, privacy-review

  backend/                       ← EXISTS (Python / FastAPI)
    sources/      mock.py, gmail.py, factory.py
    parser/       amount_extractor.py, sender_resolver.py, cycle_detector.py, pdf_extractor.py
    detector/     detector.py, confidence_scorer.py, sender_list.py, pattern_library.py
    auth/         oauth.py, token_store.py
    db/           setup.py, migrations/ (001…011)
    api/          app.py, routers/ (subscriptions, payment_events, email_records, scan, scan_async, accounts, health)
    models/       email_metadata.py, subscription.py
    utils/        retry.py

  frontend/                      ← EXISTS (Next.js)
    src/app/        page.tsx, review/page.tsx, accounts/…
    src/components/ SpendingSummary, SubscriptionTable, ReviewQueue, PaymentEventsTable
    src/lib/        api.ts, format.ts
    src/types/      api.ts

  data/mock/                     ← mock_emails.json, expected_detections.json
  scripts/                       ← validation_report.py, reprocess_email_records.py
  tests/                         ← privacy/ (build gate) · unit/ · integration/ (--integration) · fixtures/
  .github/workflows/ci.yml       ← privacy tests + pip-audit on every push
```

---

## Agent / specialist routing (detail)

The compact table is in `CLAUDE.md`. Additional rules:

- **`privacy-security-reviewer` is mandatory** after any change to `backend/auth/`,
  `backend/sources/`, `backend/db/` (schema), `backend/api/` (new endpoints), or
  `requirements.txt` (new dependency). When in doubt, invoke it first.
- **Adding a new subscription service** requires BOTH `subscription-detection-specialist`
  (Tier 1/2 in `sender_list.py`) and `email-parser-specialist` (canonical name in `sender_resolver.py`).
- **New `email_records`/`subscriptions` column** requires BOTH `product-architect` (worth
  collecting?) and `privacy-security-reviewer` (safe to store?).

> Cost note: subagents start cold and re-derive context. Prefer doing focused work inline;
> invoke a specialist when the task explicitly calls for that gate or the user asks.

---

## Key entry points

| Task area | Start here |
|---|---|
| Detection pipeline | `backend/detector/detector.py` (`process_email`) |
| Amount / cycle / sender parsing | `backend/parser/*.py` |
| PDF/attachment parsing | `backend/parser/pdf_extractor.py`, `backend/sources/gmail.py` |
| Gmail fetch / OAuth | `backend/sources/gmail.py`, `backend/auth/` |
| DB / schema | `backend/db/setup.py`, `backend/db/migrations/` |
| API | `backend/api/routers/` |
| Dashboard | `frontend/src/components/`, `frontend/src/lib/api.ts` |
| Validation / reprocess | `scripts/validation_report.py`, `scripts/reprocess_email_records.py` |
