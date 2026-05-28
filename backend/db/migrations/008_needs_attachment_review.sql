-- Migration 008: Add needs_attachment_review flag to payment_events.
--
-- Set to 1 by the detector when:
--   - amount is NULL (no amount extractable from email metadata/subject)
--   - merchant is Tier 1 (known service)
--   - pattern is RECEIPT or RENEWAL (financial signal present)
--
-- This flags events where the charge is real but the amount is only in an
-- attachment (PDF invoice). Useful for Phase 3.5 attachment/PDF parsing queue.
-- Also surfaced in PaymentEventsTable as a 📎 indicator.
--
-- SQLite ALTER TABLE ADD COLUMN is safe and idempotent — column is added with
-- DEFAULT 0 so existing rows remain valid.

ALTER TABLE payment_events ADD COLUMN
    needs_attachment_review INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_payment_events_attachment
    ON payment_events(needs_attachment_review)
    WHERE needs_attachment_review = 1;

INSERT OR IGNORE INTO schema_version (version, description, applied_at)
VALUES (9, 'payment_events: needs_attachment_review flag for amount-in-attachment events',
        datetime('now'));
