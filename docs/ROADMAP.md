# Development Roadmap

---

## Phase 0: Repository Foundation (Current)

**Goal:** Create the planning, workflow, and configuration layer before any application
code. Another developer or Claude agent can read CLAUDE.md and the docs directory and
understand the full intended system.

**Deliverables:**
- `CLAUDE.md`, `README.md`, `.gitignore`, `.env.example`
- All `docs/` files (this file, PRODUCT_SPEC, PRIVACY_SECURITY, DATA_MODEL, etc.)
- All `.claude/agents/` agent definitions
- No runnable application code

**Exit criteria:**
- All 18 scaffold files exist (commit is optional — creation is the gate)
- CLAUDE.md accurately describes agent routing for all task types
- Privacy rules are documented in at least CLAUDE.md and PRIVACY_SECURITY.md

---

## Phase 1: Mock Data + Local Detection Engine

**Goal:** Build a fully working detection and display pipeline that runs entirely on
synthetic mock data. No Gmail API calls. This phase proves the detection logic works
before any credentials are involved.

**Deliverables:**
- `data/mock/mock_emails.json` — 50+ synthetic email metadata records
- `data/mock/expected_detections.json` — expected outcomes for each mock email
- `main.py` — entry point (`python main.py --mock` starts the server)
- `requirements.txt` — pinned Python dependencies
- `conftest.py` — pytest infrastructure: `--integration` flag, `db_path` fixture
- `pytest.ini` — registers custom markers (`integration`, `slow`)
- `.github/workflows/ci.yml` — runs `pytest tests/privacy/` + `pip-audit` on every push
- `backend/` — FastAPI app skeleton
  - `backend/sources/mock.py` — mock email source returning `List[EmailMetadata]`
  - `backend/parser/` — amount extractor, sender resolver, cycle detector
  - `backend/detector/` — confidence scorer, sender list, pattern library
  - `backend/db/` — SQLite setup, migrations, CRUD operations
  - `backend/api/` — REST endpoints for the dashboard
  - `backend/utils/retry.py` — exponential backoff decorator (stubbed, used in Phase 2)
- `frontend/` — Next.js dashboard
  - `frontend/src/app/` — App Router pages (dashboard, review queue, settings)
  - `frontend/src/components/` — subscription table, spending summary
- `tests/privacy/` — all 5 privacy compliance tests (written first, before implementation)
- `tests/unit/` — parser, detector, database unit tests

**Constraints:**
- `USE_MOCK=true` is the only supported mode in this phase
- All tests must be runnable with no credentials and no network access
- `pytest tests/privacy/` must pass at 100% before Phase 2 begins
- Overall test coverage target: 90%+

**Exit criteria:**
- `python main.py --mock` serves the FastAPI backend; Next.js frontend shows a working
  subscription dashboard populated from mock fixtures
- Detection precision > 80% on the canonical mock fixture set
- All 5 privacy compliance tests pass (2 will skip gracefully pending Phase 2)
- GitHub Actions CI passes on a clean push
- `qa-test-reviewer` agent signs off on test coverage at 90%+

---

## Phase 2: Gmail API Integration

**Goal:** Replace the mock source with real Gmail API calls using the OAuth 2.0 flow.
The detection and display layer should not change — only the data source changes.

**Deliverables:**
- `backend/auth/` — OAuth flow, local callback server, PKCE implementation
- `backend/auth/token_store.py` — keyring and encrypted-file token storage backends
- `backend/sources/gmail.py` — Gmail metadata source implementing `EmailMetadata` interface
- `backend/sources/factory.py` — `USE_MOCK` switch
- Settings screen: connect Gmail, revoke Gmail, view stored data
- `tests/integration/test_gmail_api.py` — mocked HTTP integration tests (no live calls)

**Constraints:**
- Gmail scope must remain exactly `["https://www.googleapis.com/auth/gmail.readonly"]`
- `format=metadata` is the only valid Gmail API message format used
- All Phase 1 tests must still pass — the mock source is not removed
- `privacy-security-reviewer` agent must review all auth and Gmail source code

**Exit criteria:**
- OAuth flow completes successfully and token is stored encrypted
- Real Gmail scan produces subscription list equivalent to Phase 1 mock results
- All privacy compliance tests pass against the real data path
- Integration tests pass with mocked Gmail HTTP responses

---

## Phase 3: Polish and Reliability

**Goal:** Make the app reliable and pleasant to use. Add quality-of-life features
within the existing privacy and scope constraints.

**Potential deliverables** (each requires product-architect approval):
- Renewal date prediction with confidence interval display
- Category-based spending breakdown chart
- Duplicate subscription detection (same service, multiple email domains)
- CSV export (local file only — no upload)
- User-facing "What we store" data audit view (US-04 acceptance criteria)
- Better error messages for OAuth failures and Gmail API errors
- Rate limit recovery with user-visible progress indicator
- Configurable scan frequency and ignored sender list UI

**Constraints:**
- No new data fields without `product-architect` and `privacy-security-reviewer` approval
- No new external dependencies without security review
- No AI features, no bank features, no write scopes

---

## Future (Post-MVP, Not Scheduled)

These items are acknowledged but not planned. They require explicit re-scoping before
any implementation begins.

**AI-assisted parsing:**
- Use a local model (Ollama) or cloud model for ambiguous subject line parsing
- Requires privacy review: cloud model option would transmit subject lines externally
- Must be opt-in; deterministic rules remain the default

**Bank integration:**
- See `docs/FUTURE_BANK_INTEGRATION.md` for the design stub
- Higher security surface — separate planning milestone required

**Multi-Gmail-account support:**
- Multiple OAuth tokens, separate per-account databases or namespaced tables

**Mobile wrapper:**
- Electron or PWA for a native-feeling local app experience

---

## What Will Never Be Added

These are permanent non-goals, not deferred ones:

- Gmail write/send/delete scopes
- Storing full email bodies in any form
- Transmitting user data to any third-party service without explicit opt-in
- Bank credential storage of any kind
- Auto-cancelling subscriptions on the user's behalf
