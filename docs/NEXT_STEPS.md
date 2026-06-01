# Next Steps

Short and actionable. For full status read `docs/CURRENT_STATE.md`; for phase history read
`docs/ROADMAP.md`.

---

## Current status

**Phase 3.8 complete** — real-scan cleanup & usability. 617 tests pass / 1 skipped; privacy gate
green (29 tests); TypeScript clean. First real Gmail scan was run (2 accounts, 105 records).
Phase 3.8 addresses the issues found in that scan.

## Recommended next task (exact)

**Re-run a real Gmail forensic scan to validate Phase 3.8 improvements.** After the scan:

1. Confirm Cardcom/Z-Credit/Morning/RavPass/Grow rows are **absent from Review Queue** but visible
   in Payment Events as `one_time_charge` / `unknown_payment`.
2. Confirm Spotify is detected as **MONTHLY** (not ANNUAL) with the correct amount.
3. Confirm all dates display in **browser local timezone** (not UTC offset).
4. Confirm Review Queue shows account dropdown when > 1 account is present.
5. Confirm SubscriptionTable shows account badge ("multiple accounts" if applicable).
6. Run `python scripts/validation_report.py` and check the new Phase 3.8 sections
   (processor stats, PDF extraction rate, weak cycle, pre-3.8 untracked rows).
7. Note how many "pre-3.8" rows have `gmail_account_id IS NULL` — these will be populated on re-scan.

- **Skill:** `real-scan-triage`
- **Likely files:** `docs/REAL_GMAIL_SCAN_VALIDATION.md`, `scripts/validation_report.py`

## Top known product gaps

1. **Pre-3.8 email_records** have `gmail_account_id = NULL` — re-scan to populate.
2. **Multi-account body fetch** — uses first account's credentials for all message IDs.
   Full per-account routing is future work.
3. **Provider-specific PDF parsers** — extraction is generic; unusual invoice layouts yield `NO_FIELDS`.
4. **Image/scanned PDFs** are not OCR'd (text-based PDFs only).
5. **Confidence calibration** — known services stuck as FLAGGED. Add to Tier 1 or lower threshold.
6. **Subscription deduplication UI** — if user has same subscription from 2 accounts, they may
   see duplicate entries. Merge logic is future work.

## Not scheduled (need explicit re-scoping)

AI/LLM-assisted parsing (deterministic-first rule), bank integration, Outlook/IMAP. See `docs/ROADMAP.md`.

## Before starting any feature

- Run the `start-session` skill to confirm state.
- Mock data first for detection changes; the privacy gate must stay green.
- Anything touching auth/schema/sources/API/dependencies → `privacy-security-reviewer` gate.
