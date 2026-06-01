---
name: handoff-summary
description: Before /clear or after finishing a task, update docs/CURRENT_STATE.md and docs/NEXT_STEPS.md with what changed, files changed, tests run, pass/fail status, known risks, and the exact next step. Concise — no long logs or raw data.
---

# Handoff Summary Skill

Goal: write project memory to the repo so the next (cold) session can resume from four small docs.

## Update `docs/CURRENT_STATE.md`

- What changed this session (features / tables / fixes).
- Files changed (paths).
- Tests run + pass/fail/skip counts (NOT logs). Privacy gate status. TypeScript status if relevant.
- Current known problems / risks.

## Update `docs/NEXT_STEPS.md`

- The **exact** next step: file + action, specific enough to start cold.
- Refresh the top known gaps if they changed.

## Rules

- Keep it concise. No long logs, no raw email/PDF content, no PII.
- If a full report is needed later, save it to `reports/` and reference it — don't paste it into a doc.
- After updating both docs, tell the user it is safe to `/clear`.
