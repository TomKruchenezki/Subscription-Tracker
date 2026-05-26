# Product Specification

## Problem Statement

People accumulate subscriptions over time — streaming services, SaaS tools, newsletters,
cloud platforms — and lose track of them. The costs add up invisibly.

Existing subscription trackers solve this by either:
- Connecting to your bank account (high trust requirement, exposes full financial history)
- Syncing your email to a cloud service (privacy risk, vendor lock-in)

This app does neither. It reads Gmail metadata locally, runs detection on your machine,
and stores everything in a local file. No cloud sync. No bank access. No data leaves
your device.

**Tech stack:** Next.js frontend · FastAPI backend · Python parser/detection engine ·
SQLite (MVP) · PostgreSQL considered for later phases

**Target user:** A privacy-conscious developer or power user who:
- Is comfortable running a local Next.js + FastAPI stack
- Values knowing exactly what data is collected about them
- Does not want to hand over bank credentials or full email access to a third-party service

---

## MVP Scope

MVP covers Phase 1 (mock data + detection engine) and Phase 2 (Gmail read-only integration).

### In Scope

- Detect recurring subscriptions from Gmail metadata (sender, subject, date)
- Next.js dashboard: subscription list, spending summary, review queue for FLAGGED records
- FastAPI backend: detection pipeline, SQLite CRUD, mock/Gmail source switch
- Show a total estimated monthly cost
- Run entirely on mock data (`--mock` mode) with no Gmail account required
- Gmail OAuth flow using `gmail.readonly` scope only
- Encrypted local token storage
- One-command data deletion (`--delete-all`)
- "What we know about you" view: every field stored, in plain language
- Export to CSV (local file, no upload)

### Explicitly Out of Scope for MVP

- Bank connection of any kind (Plaid, Teller, scraping) — see `docs/FUTURE_BANK_INTEGRATION.md`
- Unsubscribe or cancel actions (requires Gmail write scope — never in scope)
- Email body parsing or AI-assisted detection
- Multi-Gmail-account support
- Mobile app or browser extension
- Cloud sync, SaaS version, or shared dashboards
- Notifications or reminders (stretch goal for Phase 3)
- Receipt PDF extraction
- Shared household subscription tracking

---

## User Stories

**US-01 — Mock mode evaluation**
As a new user, I can run the app with `--mock` and immediately see a populated subscription
dashboard without granting any permissions, so I can evaluate the app before connecting Gmail.

*Acceptance criteria:*
- `python main.py --mock` starts the app with no credentials required
- Dashboard shows at least 10 example subscriptions from `data/mock/mock_emails.json`
- Every detected subscription shows: name, amount, currency, billing cycle, category

---

**US-02 — Gmail connection**
As a user, I can connect my Gmail account using read-only OAuth and have the app scan
for subscriptions without me needing to understand the OAuth details.

*Acceptance criteria:*
- OAuth flow opens in browser; user sees Google's permission screen listing only "Read email"
- App does not request any write, send, delete, or compose permissions
- After authorization, app scans Gmail and presents detected subscriptions
- OAuth token is encrypted before being stored; user is informed of storage location

---

**US-03 — Subscription dashboard**
As a user, I can see all my active subscriptions with enough detail to understand
my spending.

*Acceptance criteria:*
- Table shows: service name, amount, currency, billing cycle, next renewal (estimated), category
- Summary row shows total estimated monthly cost (annual subscriptions converted to monthly)
- Cancelled and paused subscriptions are visually distinct from active ones

---

**US-04 — Data transparency**
As a user, I can see exactly what data the app has stored about me and delete it all.

*Acceptance criteria:*
- A "What we store" view enumerates every field in the database with a plain-language description
- `--delete-all` command wipes the database, the OAuth token, and all cached state
- After `--delete-all`, the app behaves as if freshly installed

---

**US-05 — Gmail disconnection**
As a user, I can revoke Gmail access from within the app and the app surfaces the link
to Google's permissions page.

*Acceptance criteria:*
- Settings screen includes a "Revoke Gmail Access" button
- Button deletes the local token and opens `https://myaccount.google.com/permissions`
- After revocation, the app returns to mock mode or prompts re-auth on next scan

---

## Success Metrics

| Metric | Target | How measured |
|---|---|---|
| Detection precision | > 80% | Manual review of detected subscriptions in test inbox |
| Detection recall | > 70% | Count of known subscriptions found vs. total known subscriptions |
| Zero body storage | 100% | `tests/privacy/test_no_body_in_schema.py` must pass |
| Gmail scope compliance | 100% | `tests/privacy/test_gmail_scope.py` must pass |
| Time to first list (mock) | < 60 seconds | From app start to visible mock subscription list |
| Time to first list (Gmail) | < 5 minutes | From OAuth start to visible real subscription list |

---

## Explicit Non-Goals

These will not be implemented and should not be proposed as MVP additions:

- **No bank access** — bank credentials, Plaid, Teller, or bank statement scraping
- **No AI parsing in MVP** — LLM-based detection is a post-MVP option
- **No write Gmail scopes** — unsubscribe, delete, archive, reply, send
- **No cloud data storage** — all data stays local; no remote database or API backend
- **No multi-user** — single local user only in MVP
- **No third-party analytics** — no Segment, Mixpanel, Sentry, or similar SDKs
