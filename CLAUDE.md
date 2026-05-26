# Subscription Tracker — CLAUDE.md

A privacy-first, local-first Gmail subscription tracker. Detects recurring subscriptions
by reading Gmail metadata only (sender, subject, date — never body). All data stays in
a local SQLite file. No cloud sync, no bank access, no telemetry.

**Tech stack:** Python 3.11+ / FastAPI / SQLite (backend) · Next.js (frontend dashboard)  
**Current phase:** Phase 1 — mock data + local detection engine (see `docs/ROADMAP.md`)

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
| 0 | Repo scaffold: docs, CLAUDE.md, agents | **Current** |
| 1 | Mock data + local detection engine | Not started |
| 2 | Gmail OAuth integration (read-only) | Not started |
| 3 | Polish, CSV export, renewal predictions | Not started |
| Future | AI parsing, bank integration | Not planned |

**Phase gate:** Do not begin Phase 2 until Phase 1 achieves 90%+ test coverage and
all privacy compliance tests pass.

**When a phase completes:** Update the Status column above and update the **Current phase**
line at the top of this file. This keeps agents reading CLAUDE.md oriented to the project's
actual state without needing to parse git history.

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
    gmail-integration-specialist.md
    email-parser-specialist.md
    subscription-detection-specialist.md
    qa-test-reviewer.md

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

---

## What Claude Must Not Do Without Explicit User Approval

- Add any Gmail scope beyond `gmail.readonly`
- Add any database column in `email_records` storing email content
- Add any new outbound HTTP call to a non-Google service
- Change the token storage mechanism
- Import Plaid, Teller, or any bank API client
- Add AI/LLM-based parsing code
- Increase the scope of data collected beyond what is in `docs/PRIVACY_SECURITY.md`
