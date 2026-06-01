---
name: privacy-review
description: Privacy checklist for new tables, new API endpoints, new data collection paths. Covers payment_events, email_records, body_text handling, and token safety.
---

# Privacy Review Checklist

Run this checklist on any new table, new endpoint, or new data collection path.
Every item must explicitly PASS or FAIL before the change is considered complete.

## Database Schema

- [ ] No `body_text`, `body_html`, `raw_body`, or `payload` column in any new table
- [ ] No `subject`, `sender_address`, `snippet` column in any new table
  - Exception: `email_records` already stores these — that is the intentional boundary
  - `payment_events` and all future tables must NOT repeat them
- [ ] No `short_evidence` column in `payment_events` or any financial event table
- [ ] `source_message_id` in new tables is an opaque traceability key only (acceptable)
- [ ] `merchant_name` is a canonical name (e.g., "Spotify") — not a raw sender address
- [ ] Any new column storing user data has been approved by both product-architect and
  privacy-security-reviewer

## Code Paths

- [ ] `format="full"` only appears inside `_fetch_body()` in `gmail.py` — never elsewhere
- [ ] `_fetch_body()` result is assigned to `EmailMetadata.body_text` (ephemeral, in-memory only)
- [ ] `body_text` is never passed to any DB insert function (`insert_email_record`, `insert_payment_event`, etc.)
- [ ] `body_text` is never passed as a logger format argument
- [ ] `body_text` is never included in any API response model
- [ ] **Phase 3.7:** `messages.attachments().get` only appears inside `_fetch_attachment_bytes()` (verified by `test_attachments_get_only_in_fetch_attachment_bytes`)
- [ ] PDF bytes / extracted text are transient — `pdf_extractor.extract_pdf_fields()` returns only structured fields, never raw text; `PdfEvidence` has no raw-text field
- [ ] `email_attachments` / `attachment_extracted_fields` have no raw-content columns (`*_text`, `body`, `html`, `snippet`, `content`, `payload`) — verified by `tests/privacy/test_attachment_no_raw_content.py`
- [ ] `*_reasons` / `*_indicators` columns hold short coded tokens, never PDF sentences

## Token and Secret Safety

- [ ] No OAuth tokens, API keys, or secrets printed in logs or test output
- [ ] `token.json` (if it exists) is encrypted — not plaintext JSON
- [ ] No new `.env` variables storing secrets are read outside `backend/auth/`

## Tests

- [ ] `tests/privacy/` suite still passes: `python -m pytest tests/privacy/ -v`
- [ ] New table migrations are covered by `tests/privacy/test_body_not_stored.py` or a new equivalent
- [ ] No test fixture includes raw email body content

## Validation Report

- [ ] `scripts/validation_report.py` does not query or print `body_text` values
- [ ] New report sections show only aggregate counts and canonical names — never raw email content
