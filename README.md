# Subscription Tracker

A privacy-first, local-first subscription tracker that reads your Gmail metadata to
detect recurring charges — without ever touching email bodies, storing data in the cloud,
or connecting to your bank.

**Privacy guarantee:** Email bodies are never fetched or stored. All data lives in a
local SQLite file on your machine. See [docs/PRIVACY_SECURITY.md](docs/PRIVACY_SECURITY.md).

---

## How It Works

```
Gmail API (read-only)
       │
       │  metadata only: sender, subject, date
       ▼
  Email Fetcher
  (format=metadata — body never requested)
       │
       ▼
  Detection Engine
  (deterministic rules: sender list + subject patterns)
       │
       ▼
  Local SQLite Database
  (subscriptions.db — never leaves your machine)
       │
       ▼
  Dashboard
  (name, amount, billing cycle, next renewal, total cost)
```

**What is stored:** Service name, sender address, subject line, charge date, amount,
billing cycle, next renewal estimate.  
**What is never stored:** Email body, attachments, contacts, full email headers,
financial account numbers.

---

## Quick Start

### Step 1 — Start in mock mode (no Gmail account needed)

```bash
git clone <this-repo>
cd subscription-tracker
cp .env.example .env
pip install -r requirements.txt
python main.py --mock
```

Open [http://localhost:8000](http://localhost:8000) to see the dashboard populated with
example subscription data. No credentials required.

### Step 2 — Connect Gmail (Phase 2+)

1. Create a Google Cloud project and enable the Gmail API
2. Create OAuth 2.0 credentials (type: **Desktop app**)
3. Add your `client_id` and `client_secret` to `.env`
4. Set `USE_MOCK=false` in `.env`
5. Run `python main.py` — the browser will open for OAuth authorization

You will see Google's permission screen listing only **"Read email"** access.
No write, send, or delete permissions are requested.

---

## Project Structure

```
CLAUDE.md              Claude agent routing guide and project rules
README.md              This file
.env.example           All environment variables with comments
main.py                App entry point (python main.py --mock)
requirements.txt       Pinned Python dependencies

docs/
  PRODUCT_SPEC.md      User stories and MVP scope
  ROADMAP.md           Development phases
  PRIVACY_SECURITY.md  Data handling policy and threat model
  GMAIL_API_PLAN.md    OAuth flow and email fetching strategy
  DATA_MODEL.md        SQLite schema
  DETECTION_RULES.md   Subscription detection rules and confidence scoring
  TEST_PLAN.md         Test strategy and mock fixture design
  FUTURE_BANK_INTEGRATION.md  Post-MVP bank design stub

.claude/agents/        Claude subagent definitions for specialized tasks
backend/               Python/FastAPI API server (Phase 1+)
frontend/              Next.js dashboard and review UI (Phase 1+)
data/mock/             Synthetic email fixtures for development and testing
tests/                 Test suite (privacy/ is the build gate)
.github/workflows/     CI — runs privacy tests + pip-audit on every push
```

---

## Privacy Guarantee

| | Stored? |
|---|---|
| Sender email address | Yes |
| Email subject line | Yes |
| Email date | Yes |
| Extracted amount | Yes |
| Billing cycle | Yes |
| **Email body text** | **Never** |
| **Attachments** | **Never** |
| **Bank account details** | **Never** |
| **Data sent to any server** | **Never** |

OAuth refresh token is encrypted at rest using your OS keyring.
Access token is kept in memory only and never written to disk.

---

## Development Docs

- [Product Spec](docs/PRODUCT_SPEC.md) — what we're building and why
- [Roadmap](docs/ROADMAP.md) — phases and exit criteria
- [Privacy & Security](docs/PRIVACY_SECURITY.md) — data policy and threat model
- [Gmail API Plan](docs/GMAIL_API_PLAN.md) — OAuth and fetching design
- [Data Model](docs/DATA_MODEL.md) — database schema
- [Detection Rules](docs/DETECTION_RULES.md) — how subscriptions are identified
- [Test Plan](docs/TEST_PLAN.md) — testing strategy and fixture design
- [Future Bank Integration](docs/FUTURE_BANK_INTEGRATION.md) — post-MVP design stub

---

## Contributing

Before submitting any change:

```bash
pytest tests/privacy/    # must pass at 100% — this is the build gate
pytest                   # full suite
```

Every PR description must answer: *"What data does this change collect, store, or transmit?"*

Detection rule changes must be accompanied by a mock fixture entry in
`data/mock/mock_emails.json` and a test case in `tests/unit/test_detector.py`.

See [CLAUDE.md](CLAUDE.md) for the full agent routing guide and workflow rules.

---

## Deleting Your Data

```bash
python main.py --delete-all
```

Wipes the local database, removes the encrypted OAuth token, and resets all settings.
No data exists server-side — there is no server.
