---
name: start-session
description: Start a new session with minimal context. Read only CLAUDE.md, docs/CURRENT_STATE.md, docs/NEXT_STEPS.md, and docs/PRIVACY_SECURITY.md, then summarize the current state in ~10 bullets and wait for the user to pick a task.
---

# Start Session Skill

Goal: begin a session lean, using repo files as memory — not chat history.

## Steps

1. Read ONLY these four files (do not open anything else yet):
   - `CLAUDE.md`
   - `docs/CURRENT_STATE.md`
   - `docs/NEXT_STEPS.md`
   - `docs/PRIVACY_SECURITY.md`
2. Summarize the current project state in ~10 bullets:
   - current phase + what just shipped
   - test status (counts) + privacy gate status
   - top 2–3 known problems / gaps
   - the recommended next task (from `docs/NEXT_STEPS.md`)
   - the hard privacy boundaries (gmail.readonly only; no raw body/snippet/PDF text stored)
3. Ask the user which task to continue. **STOP and wait.**

## Rules

- Do NOT scan the whole repo. Open further files only after the user picks a task, and only
  those the task needs (Grep/Glob to locate; Read just what's needed).
- Do NOT infer state from earlier chat history — trust the docs.
- NEVER read `.env`/tokens/raw bodies/snippets/HTML/PDF text/PII rows.
