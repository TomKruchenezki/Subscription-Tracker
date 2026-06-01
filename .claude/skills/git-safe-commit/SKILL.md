---
name: git-safe-commit
description: Prepare a safe commit. Run git status --short, ensure secrets / DB files / token files / node_modules / .venv are not staged, run privacy and relevant tests, suggest a commit message, and never commit without explicit user approval.
---

# Git Safe Commit Skill

Goal: prepare a commit safely. **NEVER commit without the user's explicit approval.**

## Checks (in order)

1. `git status --short` — review exactly what would be committed.
2. Confirm NONE of these are staged: `.env`, `.env.local`, `*.db` / `data/*.db`, token files
   (`token.json`, keyring exports), `node_modules/`, `.venv/`, build artifacts, and anything under
   `reports/` that could contain raw output. If any are staged (or risky and untracked), stop and
   flag it; check `.gitignore`.
3. Privacy gate: `python -m pytest tests/privacy/ -q` (must be 100%).
4. Targeted tests relevant to the change (use the `test-and-report` skill).
5. If on the default branch, propose creating a feature branch first.

## Then

- Summarize the staged changes (files + one line each).
- Suggest a commit message; include the `Co-Authored-By` trailer per the harness convention.
- Note for the commit/PR body: "What data does this change collect, store, or transmit?"
- **STOP and ask the user to approve** before running `git commit`.

## Rules

- Do not bypass hooks or signing.
- Never `git add` secrets, DB files, or tokens.
