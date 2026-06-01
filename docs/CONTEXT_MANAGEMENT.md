# Context Management

How to keep Claude Code sessions small and continuable. **The repo is the memory — not chat
history.** A session that relies on long history is fragile and expensive; a session that reads
a few small docs and writes a handoff before clearing is cheap and resumable.

---

## Starting a new session

Run the `start-session` skill, or manually:

1. Read only these four files (nothing else yet):
   - `CLAUDE.md` — rules + protocol
   - `docs/CURRENT_STATE.md` — where the project is
   - `docs/NEXT_STEPS.md` — what to do next
   - `docs/PRIVACY_SECURITY.md` — the privacy boundary
2. Summarize the current state in ~10 bullets.
3. Ask the user which task to continue.
4. **Do not scan the whole repo.** Open more files only when the chosen task needs them —
   use Grep/Glob to locate, then Read just those.

Do **not** reconstruct state from earlier chat turns; trust the docs.

---

## NORMAL vs DEEP (which mode?)

| Use NORMAL when… | Use DEEP ARCHITECTURE when… |
|---|---|
| Bug fix, add a pattern, test/UI tweak | New migration, schema/data-model change |
| Change touches ≤ 2 files | Change touches > 3 files / > 1 subsystem |
| Logic is localized | payment_events, subscription linking, parsers, PDF, multi-account |
| Read CURRENT_STATE + the few relevant files | Read all genuinely relevant backend + schema + test files |

Both modes: never read `.env`/tokens/raw bodies/snippets/PDF text/PII rows (NEVER mode in CLAUDE.md).

---

## When to `/clear`

`/clear` whenever:
- A task is finished and the next one is unrelated.
- The conversation is getting long (you're re-reading the same files, or summaries are growing).
- You switched topics (e.g. from a feature to a docs pass).

**Always write a handoff first** (next section) — `/clear` discards chat, so unsaved state is lost.

---

## Handoff before clearing

Run the `handoff-summary` skill, or manually update **`docs/CURRENT_STATE.md`** and
**`docs/NEXT_STEPS.md`** with:

- What changed (features/tables/fixes) and which files.
- Tests run + pass/fail counts (not logs).
- Known risks / open issues.
- The **exact** next step (file + action), so a cold session can resume immediately.

Keep it concise. **No long logs, no raw data, no PII.** Then tell the user it is safe to `/clear`.

A good handoff means the next session reads four small docs and is immediately productive.

---

## Keep reports and logs out of chat

- **Tests:** use the `test-and-report` skill — report counts + only failing names + the first
  relevant traceback. Never paste a full pytest log into chat.
- **Validation report:** summarize the key numbers in chat; if the full output is needed, save it
  to `reports/` (gitignored if it could contain anything sensitive) instead of pasting it.
- **Scans / screenshots:** record service names and statistics only — never raw subjects/senders
  (see `docs/REAL_GMAIL_SCAN_VALIDATION.md`).

The less raw output that enters the context window, the longer and cheaper the session stays.

---

## Quick reference

| Situation | Do this |
|---|---|
| New session | skill `start-session` |
| Finished a task / about to `/clear` | skill `handoff-summary` |
| Need to run tests | skill `test-and-report` |
| About to commit | skill `git-safe-commit` |
| Looking at real scan results | skill `real-scan-triage` |
| Planning a multi-file change | Plan Mode + skill `phase-plan` |
