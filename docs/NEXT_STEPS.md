# Next Steps — Phase 3 Roadmap

Do not implement any phase before the previous one is validated
(forensic scan run, amounts confirmed, tests passing).

---

## Phase 3.1 — payment_events Table + Event-to-Subscription Linking

**Prerequisite:** Run forensic + 1y scan after Phase 3.0. Confirm
Google/Spotify/Zoom transition from UNKNOWN → ACTIVE with correct amounts.

**Goal:** Introduce a `payment_events` table that records individual payment
occurrences separate from the latest subscription state. Enables:
- Confirmed total paid per subscription
- One-time vs recurring classification
- Richer payment history without bloating `email_records`

**Key constraints:**
- `product-architect` must approve the schema before any migration is written
- `privacy-security-reviewer` gate required before any new column is created
- No raw body, no raw subject, no sender address stored in payment_events

**Proposed fields:**
`payment_event_id`, `subscription_id`, `source_message_id` (hash only),
`amount`, `currency`, `payment_date`, `event_type`, `confidence_score`, `created_at`

---

## Phase 3.2 — Provider-Specific Parsers

**Prerequisite:** Phase 3.1 complete and validated.

**Goal:** Extract product names and plan variants from email body_text for providers
where the canonical name is too generic:

| Provider | Problem | Goal |
|----------|---------|------|
| Google Play | Canonical name is "Google", not actual product | Extract "Google One", "YouTube Premium", etc. |
| Spotify | "Premium Student", "Family" variants not distinguished | Extract plan type from subject/body |
| Zoom | "Payment Processed" subject → no billing cycle | Extract cycle from body_text |
| Substack | Billing vs newsletter content | Suppress non-billing Substack emails |

**Key constraints:**
- `product_name` column on subscriptions needs product-architect + privacy gate
- Body text always ephemeral — parsing in the `_fetch_body()` chain only, never stored
- Each provider requires dedicated mock fixtures + parametrized tests before implementation

---

## Phase 3.3 — Attachment/PDF Parsing (Billing Candidates Only)

**Prerequisite:** Phase 3.2 complete; body_text extraction proven robust across
providers.

**Goal:** For emails where body_text yields no amount but a PDF attachment is present
(e.g., invoice-style billing emails), parse the first page ephemerally for amount/cycle.

**Key constraints:**
- Binary parsing dependencies (pdfminer or PyMuPDF) require privacy-security-reviewer approval before adding to requirements.txt
- `attachments.get()` is within `gmail.readonly` scope but needs explicit privacy review of the extraction pipeline
- Parsing is strictly ephemeral — raw bytes discarded immediately after extraction, never logged
- Scope-limited to emails already DETECTED or high-confidence FLAGGED (score ≥ 0.60)
- Only first page of first attachment is read — no multi-page, no embedded images
