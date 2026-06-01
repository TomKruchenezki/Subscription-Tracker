# Next Steps

Short and actionable. For full status read `docs/CURRENT_STATE.md`; for phase history read
`docs/ROADMAP.md`.

---

## Current status

**Phase 3.7 complete** — safe PDF/attachment receipt parsing (transient extraction, structured-only
persistence, correction-aware). 579 tests pass / 1 skipped; privacy gate green; TypeScript clean.
Validated with **synthetic PDF fixtures only** — not yet against a real Gmail account.

## Recommended next task (exact)

**Validate Phase 3.7 against a real Gmail account.** Connect Gmail, run a forensic scan (e.g. 2y),
then use the `real-scan-triage` skill + `docs/REAL_GMAIL_SCAN_VALIDATION.md`. Confirm:

- An email whose amount is only in a PDF invoice now shows the amount (ReviewQueue 📎 → details).
- `email_attachments` / `attachment_extracted_fields` populate; **no raw PDF text stored**.
- `python scripts/validation_report.py` → "ATTACHMENT / PDF COVERAGE" section looks sensible.
- A PDF receipt with no recurring evidence is **not** auto-confirmed; a refund PDF is not a charge.
- Mark a PDF-derived event one-time → reprocess → it is not recreated as a subscription.

- **Likely files:** `backend/sources/gmail.py`, `backend/parser/pdf_extractor.py`,
  `backend/detector/detector.py`, `scripts/validation_report.py`.
- **Likely tests:** `tests/unit/test_pdf_extractor.py`, `test_detector_pdf.py`,
  `test_pdf_corrections.py`, `tests/privacy/`.

## Top known product gaps

1. **Real-scan validation of PDF extraction** is pending (the task above).
2. **Timezone display** — timestamps are stored/processed in **UTC**; user-facing display timezone
   (Asia/Jerusalem) is not handled, so dates may render in UTC. Verify current behavior, then decide
   and implement a display timezone. (Display-only; do not change stored values.)
3. **Provider-specific PDF parsers** — extraction is generic; unusual invoice layouts yield `NO_FIELDS`.
4. **Image/scanned PDFs** are not OCR'd (text-based PDFs only).
5. **Full multi-account selector UI** — backend scans all accounts; there is no per-account UI.
6. **Precision/recall backlog** — one-time purchases leaking into the Review Queue, confidence
   calibration for known services stuck as FLAGGED. See the backlog in `docs/REAL_GMAIL_SCAN_VALIDATION.md`.

## Not scheduled (need explicit re-scoping)

AI/LLM-assisted parsing (deterministic-first rule), bank integration, Outlook/IMAP. See `docs/ROADMAP.md`.

## Before starting any feature

- Run the `start-session` skill to confirm state.
- Mock data first for detection changes; the privacy gate must stay green.
- Anything touching auth/schema/sources/API/dependencies → `privacy-security-reviewer` gate.
