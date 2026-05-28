# Subscription Tracker — CLAUDE.md

A privacy-first, local-first Gmail subscription tracker. Detects recurring subscriptions
by reading Gmail metadata only (sender, subject, date — never body). All data stays in
a local SQLite file. No cloud sync, no bank access, no telemetry.

**Tech stack:** Python 3.11+ / FastAPI / SQLite (backend) · Next.js (frontend dashboard)  
**Current phase:** Phase 3.3B complete — payment event semantics, native currency (₪/$), GET /api/payment-events, frontend PaymentEventsTable. See `docs/CURRENT_STATE.md`.

---

## Non-Negotiable Rules

These rules cannot be overridden by any agent, developer, or user request. Violations
must be surfaced immediately and block all other work.

| # | Rule |
|---|---|
| 1 | **Gmail scope is `gmail.readonly` only.** Never add a second scope. |
| 2 | **Never fetch or store email bodies.** `format=metadata` only in all Gmail API calls. |
| 3 | **Never store OAuth tokens in plaintext.** Keyring or AES-256 encrypted file only. |
| 4 | **No bank integration code of any kind.** No Plaid, Teller, scraping, or bank credentials. |
| 5 | **No external data transmission.** No analytics SDKs, no error-reporting services. |
| 6 | **`tests/privacy/` must never fail.** Failing privacy tests block all other work. |
| 7 | **Mock data first.** No live Gmail API calls until Phase 1 tests pass at 90%+ coverage. (Phase 1 constraint — lifted at Phase 2 gate. See ROADMAP.md.) |
| 8 | **Deterministic rules first.** No AI/LLM detection until deterministic rules are documented, tested, and shown to be insufficient. (MVP constraint — see ROADMAP.md Future section.) |

---

## Agent Routing Table

Invoke the appropriate subagent for each task type. When in doubt, invoke
`privacy-security-reviewer` as the first step.

| Task | Agent |
|---|---|
| Product scope, user stories, feature approval, new data fields | `product-architect` |
| ANY auth/schema/data-collection/API/dependency change (mandatory gate) | `privacy-security-reviewer` |
| payment_events quality, currency correctness, one-time vs recurring, refund handling | `payment-data-quality-reviewer` |
| Gmail API calls, OAuth flow, token storage, rate limiting | `gmail-integration-specialist` |
| Subject line parsing, amount extraction, sender resolution, cycle detection | `email-parser-specialist` |
| Detection rules, confidence scoring, sender domain list, categorization | `subscription-detection-specialist` |
| Test design, mock fixtures, coverage analysis, privacy test coverage | `qa-test-reviewer` |

**Adding a new subscription service** (e.g., a new streaming service) requires BOTH:
- `subscription-detection-specialist` — Tier 1/2 classification in `sender_list.py`
- `email-parser-specialist` — canonical name mapping in `sender_resolver.py`

**Schema change authority:** `product-architect` approves the *value* (is this field worth
collecting?). `privacy-security-reviewer` approves the *safety* (is this field safe to store?).
Both approvals are required for any new `email_records` or `subscriptions` column.

**`privacy-security-reviewer` is always invoked after any change to:**
- `backend/auth/`
- `backend/sources/`
- `backend/db/` (schema changes)
- `backend/api/` (new endpoints)
- `requirements.txt` (new dependencies)

---

## Development Phases

| Phase | Description | Status |
|---|---|---|
| 0 | Repo scaffold | Complete |
| 1 | Mock data + local detection engine | Complete |
| 2 | Gmail OAuth integration (read-only) | Complete |
| 3.0 | HTML body extraction fixes | **Complete** |
| 3.1 | payment_events + native currency + subscription linking | **Complete** |
| 3.3B | payment_events semantics + GET /api/payment-events + frontend PaymentEventsTable + billing cycle fix | **Complete** |
| 3.2 | Provider-specific parsers | Next |
| 3.3 | Attachment/PDF parsing | Planned |
| Future | AI parsing, bank integration | Not planned |

**When a phase completes:** Update the Status column above and the **Current phase**
line at the top of this file. Also update `docs/CURRENT_STATE.md` with the new test
count, scan results, and known problems.

---

## File Layout Reference

```
subscription-tracker/
  CLAUDE.md                      ← you are here
  README.md                      ← developer setup guide
  .env.example                   ← all env vars with comments
  .gitignore

  docs/
    PRODUCT_SPEC.md              ← user stories, MVP scope, non-goals
    ROADMAP.md                   ← phases and exit criteria
    PRIVACY_SECURITY.md          ← data handling policy, threat model
    GMAIL_API_PLAN.md            ← OAuth flow, fetching strategy
    DATA_MODEL.md                ← SQLite schema (4 tables)
    DETECTION_RULES.md           ← confidence scoring, pattern library
    TEST_PLAN.md                 ← test hierarchy, fixture design rules
    FUTURE_BANK_INTEGRATION.md   ← post-MVP design stub

  .claude/agents/
    product-architect.md
    privacy-security-reviewer.md
    payment-data-quality-reviewer.md
    gmail-integration-specialist.md
    email-parser-specialist.md
    subscription-detection-specialist.md
    qa-test-reviewer.md

  .claude/skills/
    phase-plan/SKILL.md          ← planning skill: diagnose → scope → tests → stop
    scan-diagnosis/SKILL.md      ← analyze validation_report output and scan results
    privacy-review/SKILL.md      ← privacy checklist for payment_events + new tables

  backend/                       ← Phase 1+ (does not exist yet)
    sources/                     ← mock.py, gmail.py, factory.py
    parser/                      ← amount_extractor.py, sender_resolver.py, cycle_detector.py
    detector/                    ← confidence_scorer.py, sender_list.py, pattern_library.py, detector.py
    auth/                        ← oauth.py, token_store.py
    db/                          ← setup.py, migrations/
    api/                         ← FastAPI routers
    utils/                       ← retry.py

  frontend/                      ← Phase 1+ Next.js dashboard
    src/
      app/                       ← Next.js App Router pages
      components/                ← dashboard, subscription list, review queue

  data/
    mock/                        ← mock_emails.json, expected_detections.json

  tests/
    privacy/                     ← build gate — must always pass
    unit/
    integration/                 ← requires --integration flag

  conftest.py                    ← --integration flag, db_path fixture
  pytest.ini                     ← markers: integration, slow
  main.py                        ← app entry point (python main.py --mock)
  requirements.txt               ← pinned Python dependencies
  .github/workflows/ci.yml       ← privacy tests + pip-audit on every push
```

---

## Workflow Rules

**Starting new features:**
1. Confirm the feature is in scope — invoke `product-architect` if uncertain
2. Start in mock mode — prototype against `data/mock/` before live data
3. Write privacy tests and interface tests before implementation
4. Invoke `privacy-security-reviewer` after implementing any auth or storage code

**Detection rule changes:**
1. Update `docs/DETECTION_RULES.md` first
2. Add mock fixture + expected outcome
3. Add parametrized test case
4. Then implement the code

**Before every commit:**
- Run `pytest tests/privacy/` — must pass at 100%
- Every PR description must answer: "What data does this change collect, store, or transmit?"

**After every phase completes:** Update `docs/CURRENT_STATE.md` with:
- What changed (new tables, bug fixes, new features)
- Current known problems
- Latest test count and pass/fail status
- Next recommended phase
- Exact verification commands (privacy gate, full suite, validation report command)

**User-visible acceptance criteria (required for every product feature):**
Every feature must specify where the user sees it in the app. If a backend change is
intentionally backend-only (e.g., a schema migration or internal refactor), state that
explicitly and confirm with the user. "The validation report shows it" is not sufficient
unless the feature is explicitly scoped as backend-only.

**Product acceptance gate (required before marking a phase complete):**
Before closing any phase, answer all four:
1. What changed for the user? (be specific — which screen/section)
2. Which API endpoint or UI component exposes it?
3. How can the user verify it without running a script or reading code?
4. Is `validation_report.py` the only visible evidence? If yes, is that accepted scope?

**No invisible feature completion:**
A phase is not complete if its new capability exists only in backend code, the DB schema,
or `validation_report.py` output — unless the phase was explicitly scoped as backend-only
and the user confirmed that scope before implementation began. Invoke `product-acceptance-reviewer`
before marking any feature-phase done.

---

## Context Budget Modes

Choose the mode that matches the task. Do not default to minimal-read mode for
architectural work — shallow context produces bad plans.

### NORMAL mode
Use for: targeted bug fixes, adding patterns, updating tests, small UI tweaks.
- Read `docs/CURRENT_STATE.md` first — it has phase, test count, known problems, and
  verification commands. Do not infer project state from other files.
- Then read only files directly relevant to the task. Use Grep/Glob to locate; Read only what is needed.
- Targeted tests first (`python -m pytest tests/unit/test_<module>.py -q`). Full suite once at the end.
- TypeScript check only when `.tsx`/`.ts` files were changed.
- Use Plan Mode for any change touching > 2 files or requiring architectural decisions.
- No implementation before explicit ExitPlanMode approval. "Sounds good" is not approval.
- Keep summaries concise: 3–5 bullet points. No verbatim plan recap.

### DEEP ARCHITECTURE mode
Use for: payment_events, subscription linking, multi-account scanning, provider parsers,
PDF parsing, new migrations, or any change touching > 3 files or > 1 subsystem.
- Read all genuinely relevant backend + schema + test files for the area being changed.
- **Depth is preferred over token savings.** A correct plan is worth the extra reads.
- Still avoid files unrelated to the change (unrelated auth, unrelated routers, frontend when backend-only, etc.).
- Always use Plan Mode. Always run the full test suite at the end.

### NEVER mode (always active, overrides everything)
Never read or print, under any circumstances:
- `.env`, `.env.local`, any file containing secrets or tokens
- Raw email bodies, raw HTML, snippets, or OAuth token values
- Raw DB row contents that include user PII
- Binary files, images, or media unless explicitly asked by the user

---

## What Claude Must Not Do Without Explicit User Approval

- Add any Gmail scope beyond `gmail.readonly`
- Add any database column in `email_records` storing email content
- Add any new outbound HTTP call to a non-Google service
- Change the token storage mechanism
- Import Plaid, Teller, or any bank API client
- Add AI/LLM-based parsing code
- Increase the scope of data collected beyond what is in `docs/PRIVACY_SECURITY.md`
