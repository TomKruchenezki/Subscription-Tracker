---
name: real-scan-triage
description: Analyze real Gmail scan results (validation_report.py output plus the user's UI observations). Focus on account visibility, false positives, one-time payment leakage into the Review Queue, payment-processor vs merchant confusion, missing amount/currency/cycle, and weak cycle inference. Do not scan the whole repo.
---

# Real Scan Triage Skill

Goal: turn a real Gmail scan + the user's UI observations into a short, actionable diagnosis.
Complements `scan-diagnosis` (which parses `validation_report.py` output); this one centers on a
real-account scan and the specific failure modes below.

## Inputs

- Output of `python scripts/validation_report.py` (summarize key numbers; don't paste it all).
- The user's UI observations / screenshots — service names + counts only (no raw subjects/senders).
- `docs/REAL_GMAIL_SCAN_VALIDATION.md` (session template + backlog).

## Focus areas

1. **Account visibility** — are rows attributed to the right account (`account_alias`)? Were all
   connected accounts scanned?
2. **False positives** — one-time purchases / promos / notifications showing as subscriptions.
3. **One-time leakage** — one-time payments surfacing as recurring candidates in the Review Queue.
4. **Processor vs merchant** — PayPal/processor shown instead of the real merchant name.
5. **Missing amount / currency / cycle** — UNKNOWN status, NULL amount, wrong currency (ILS→USD),
   `needs_attachment_review`.
6. **Weak cycle inference** — ANNUAL/WEEKLY on a known monthly service.
7. **PDF (Phase 3.7)** — were PDFs parsed and amounts recovered? Are receipts NOT over-confirmed?
   (see the "ATTACHMENT / PDF COVERAGE" section of the report).

## Output

- The top 1–3 problems worth fixing next, each as: symptom → likely cause → recommended fix/owner
  (map to `docs/NEXT_STEPS.md` or the backlog in `docs/REAL_GMAIL_SCAN_VALIDATION.md`).
- Do NOT scan the whole repo; open a specific file only to confirm a specific cause.
- NEVER record raw subjects/senders/PII — service names + statistics only.
