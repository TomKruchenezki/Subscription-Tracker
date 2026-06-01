---
name: test-and-report
description: Run tests without flooding the context window. Run targeted tests first and the full suite only at the end; report pass/fail counts plus only failing test names and the first relevant traceback. Never paste huge logs.
---

# Test and Report Skill

Goal: get test signal into the session without dumping logs into the context window.

## Procedure

1. Targeted tests for the change first: `python -m pytest tests/unit/test_<module>.py -q`
2. Privacy gate when touching anything privacy-relevant: `python -m pytest tests/privacy/ -q`
3. Full suite only once, at the end: `python -m pytest tests/ -q`
4. Frontend changes: `cd frontend && npx tsc --noEmit`

## Reporting (in chat)

- Report the pass/fail/skip **counts** (e.g. "579 passed, 1 skipped").
- List ONLY failing test names.
- Include ONLY the first relevant traceback for a failure (the assertion + its cause).
- Do NOT paste full logs, full output, or passing-test noise.
- Never print raw email/PDF content or PII that a test fixture might surface.

## Tip

Slice long output (e.g. show only the summary line / the last ~15 lines) rather than the whole run.
