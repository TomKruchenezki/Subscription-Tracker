# Subscription Tracker — CLAUDE.md

A privacy-first, local-first Gmail subscription tracker. Detects recurring subscriptions
by reading Gmail metadata (sender, subject, date) and — in forensic mode only — transiently
parsing email bodies and PDF attachments in memory. No raw body, snippet, or PDF text is
ever stored. All data stays in a local SQLite file. No cloud sync, no bank access, no telemetry.

**Tech stack:** Python 3.11+ / FastAPI / SQLite (backend) · Next.js (frontend dashboard)
**Current phase & status:** see `docs/CURRENT_STATE.md` (phase, test count, known problems, verification commands).
**What to do next:** see `docs/NEXT_STEPS.md`.

---

## Session Startup Protocol

On a new session, do NOT infer project state from chat history. Instead:

1. Read only: `CLAUDE.md`, `docs/CURRENT_STATE.md`, `docs/NEXT_STEPS.md`, `docs/PRIVACY_SECURITY.md`.
2. Summarize the current state in ~10 bullets.
3. Ask which task to continue.
4. **Do not scan the whole repo** — read more files only when the chosen task requires them
   (use Grep/Glob to locate; Read only what's needed).

The `start-session` skill automates steps 1–3.

---

## Non-Negotiable Rules

These cannot be overridden by any agent, developer, or user request. Surface violations
immediately; they block all other work.

| # | Rule |
|---|---|
| 1 | **Gmail scope is `gmail.readonly` only.** Never add a second scope. |
| 2 | **Never store raw email bodies, attachment content, or PDF text.** `format=metadata` is the default. Body/attachment content may be fetched **transiently in forensic mode only** (`format=full` in `_fetch_body()`; `messages.attachments.get` in `_fetch_attachment_bytes()`), parsed in memory, and discarded immediately — never persisted, logged, or returned by any API. Only structured fields + coded reason tokens are stored. |
| 3 | **Never store OAuth tokens in plaintext.** Keyring or AES-256 encrypted file only. |
| 4 | **No bank integration code of any kind.** No Plaid, Teller, scraping, or bank credentials. |
| 5 | **No external data transmission.** No analytics SDKs, no error-reporting services. |
| 6 | **`tests/privacy/` must never fail.** Failing privacy tests block all other work. |
| 7 | **Mock data first** for new detection work — prototype against `data/mock/` before live Gmail. |
| 8 | **Deterministic rules first.** No AI/LLM detection until deterministic rules are documented, tested, and shown insufficient. |

---

## Context Budget Modes

Pick the mode that fits the task. Do not default to minimal-read for architectural work —
shallow context produces bad plans. **Never scan the whole repo by default.**

**NORMAL** — bug fixes, adding patterns, test/UI tweaks, small changes.
- Read `docs/CURRENT_STATE.md` first; then only files directly relevant (Grep/Glob to locate).
- Targeted tests first; full suite once at the end. `tsc --noEmit` only if `.ts/.tsx` changed.
- Plan Mode for any change touching > 2 files or needing architectural decisions.
- No implementation before explicit ExitPlanMode approval ("sounds good" is not approval).

**DEEP ARCHITECTURE** — payment_events, subscription linking, multi-account, parsers, PDF,
new migrations, or any change touching > 3 files / > 1 subsystem.
- Read all genuinely relevant backend + schema + test files for the area. Depth > token savings.
- Always Plan Mode; always full suite at the end.

**NEVER mode (always active, overrides everything)** — never read or print:
- `.env`, `.env.local`, any file with secrets or tokens
- Raw email bodies, raw HTML, snippets, raw PDF text, or OAuth token values
- Raw DB rows containing user PII
- Binary files, images, or media unless explicitly asked

---

## Routing

Invoke a specialist when the task calls for that gate or the user asks. When in doubt about
privacy, invoke `privacy-security-reviewer` first. (Detailed routing rules: `docs/ARCHITECTURE.md`.)

| Task | Use |
|---|---|
| Start a session lean | skill `start-session` |
| Hand off before `/clear` / end of task | skill `handoff-summary` |
| Run tests without flooding context | skill `test-and-report` |
| Prepare a safe commit | skill `git-safe-commit` |
| Triage a real Gmail scan | skill `real-scan-triage` (or `scan-diagnosis` for report parsing) |
| Plan an architecture phase | skill `phase-plan` |
| ANY auth/schema/data/API/dependency change (mandatory) | agent `privacy-security-reviewer` |
| Product scope / new data field | agent `product-architect` |
| payment_events quality, currency, one-time vs recurring, refunds | agent `payment-data-quality-reviewer` |
| Gmail / OAuth / rate-limit | agent `gmail-integration-specialist` |
| Amount / sender / cycle parsing | agent `email-parser-specialist` |
| Detection rules / sender list / scoring | agent `subscription-detection-specialist` |
| Tests / fixtures / coverage | agent `qa-test-reviewer` |
| Is a finished feature user-visible? | agent `product-acceptance-reviewer` |

---

## Checklists

**Before commit** (skill `git-safe-commit`):
- `git status --short`; confirm `.env`, DB files, token files, `node_modules`, `.venv` are NOT staged.
- `python -m pytest tests/privacy/ -q` passes 100%; run relevant targeted tests.
- Commit only when the user explicitly approves. Commit/PR body answers: "What data does this collect, store, or transmit?"

**After a task / before `/clear`** (skill `handoff-summary`):
- Update `docs/CURRENT_STATE.md` (what changed, files, test count, known problems) and
  `docs/NEXT_STEPS.md` (exact next step). Then tell the user it is safe to `/clear`.

**Test & log discipline** (skill `test-and-report`):
- Targeted tests first; full suite only at the end. Report pass/fail **counts** + only failing
  test names and the first relevant traceback. **Never paste full test logs.**
- For `validation_report.py`: summarize first; save the full report to `reports/` only if needed.
  Never print raw subjects/senders/PII.

**After a phase completes:** update the phase status in `docs/ROADMAP.md` and the summary in `docs/CURRENT_STATE.md`.

---

## What Claude Must Not Do Without Explicit User Approval

- Add any Gmail scope beyond `gmail.readonly`
- Store raw email body, snippet, HTML, or raw PDF/attachment text in any table
- Add any new outbound HTTP call to a non-Google service
- Change the token storage mechanism
- Import Plaid, Teller, or any bank API client; add AI/LLM-based parsing code
- Add a new third-party dependency without a `privacy-security-reviewer` pass + `pip-audit`
- Increase data collected beyond `docs/PRIVACY_SECURITY.md`

> Attachment **content** download via `messages.attachments.get` is permitted (user-approved,
> Phase 3.7) ONLY inside `_fetch_attachment_bytes()`, ONLY in forensic mode, ONLY transiently —
> bytes/text parsed in memory and discarded. Uses existing `gmail.readonly` scope; raw text never stored.

---

## Where things live

| Need | File |
|---|---|
| Current phase, tests, known problems | `docs/CURRENT_STATE.md` |
| Next task to work on | `docs/NEXT_STEPS.md` |
| Session hygiene, `/clear`, handoff | `docs/CONTEXT_MANAGEMENT.md` |
| File layout, data flow, tables, routing detail | `docs/ARCHITECTURE.md` |
| Acceptance gate, explainable/correctable rules | `docs/PRODUCT_ACCEPTANCE.md` |
| Privacy policy / threat model | `docs/PRIVACY_SECURITY.md` |
| Phase history & exit criteria | `docs/ROADMAP.md` |
| Real Gmail scan validation | `docs/REAL_GMAIL_SCAN_VALIDATION.md` |
