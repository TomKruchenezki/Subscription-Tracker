-- Migration 012: Phase 3.8 — real-scan cleanup columns.
--
-- Adds structured metadata columns to email_records for:
--   * Processor/merchant separation (sender_domain, payment_processor,
--     merchant_name_candidate, is_processor_email)
--   * Multi-account visibility (gmail_account_id)
--   * Cycle-confidence tracking (cycle_source, cycle_confidence)
--
-- Privacy guarantees:
--   sender_domain         — extracted programmatically from sender_address (no new data)
--   payment_processor     — canonical name (e.g. "Cardcom"), never raw content
--   merchant_name_candidate — structured candidate from PDF structured fields / cleaned
--                             subject heuristic / user correction.
--                             MUST NEVER store raw body text, raw PDF text, snippets,
--                             or long unprocessed strings.
--   is_processor_email    — 0/1 flag; used to suppress processor rows from Review Queue
--   gmail_account_id      — opaque account identifier (not the Gmail address itself)
--   cycle_source          — which evidence source produced the billing cycle inference
--   cycle_confidence      — STRONG (positional) | WEAK (context-word) | NONE

ALTER TABLE email_records ADD COLUMN sender_domain            TEXT;
ALTER TABLE email_records ADD COLUMN payment_processor        TEXT;
ALTER TABLE email_records ADD COLUMN merchant_name_candidate  TEXT;
ALTER TABLE email_records ADD COLUMN is_processor_email       INTEGER NOT NULL DEFAULT 0;
ALTER TABLE email_records ADD COLUMN gmail_account_id         TEXT;
ALTER TABLE email_records ADD COLUMN cycle_source             TEXT;
ALTER TABLE email_records ADD COLUMN cycle_confidence         TEXT;

CREATE INDEX IF NOT EXISTS idx_email_records_processor ON email_records(is_processor_email);
CREATE INDEX IF NOT EXISTS idx_email_records_account   ON email_records(gmail_account_id);

INSERT OR IGNORE INTO schema_version (version, description, applied_at)
VALUES (
    13,
    'Phase 3.8: sender_domain, payment_processor, merchant_name_candidate, is_processor_email, gmail_account_id, cycle_source, cycle_confidence on email_records',
    datetime('now')
);
