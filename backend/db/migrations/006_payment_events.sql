-- Migration 006: payment_events table for individual financial events.
-- Captures each detected financial event from an email before deciding
-- whether to create/update a subscription. Stores NO raw email content
-- (no subject, sender_address, snippet, body_text, or body_html).

CREATE TABLE IF NOT EXISTS payment_events (
    event_id              TEXT PRIMARY KEY,
    source_message_id     TEXT NOT NULL,        -- traceability key only; NOT a FK
    source_provider       TEXT NOT NULL,
    source_account_id     TEXT NOT NULL DEFAULT 'mock_default',
    event_type            TEXT NOT NULL
        CHECK(event_type IN (
            'subscription_charge', 'one_time_charge', 'refund', 'cancellation',
            'trial_started', 'trial_ended', 'failed_payment', 'price_change',
            'unknown_payment'
        )),
    amount                REAL,                 -- NULL when not extracted
    currency              TEXT,                 -- ISO 4217 native currency; NULL when unknown
    merchant_name         TEXT NOT NULL,        -- canonical service name from detection pipeline
    event_date            TEXT NOT NULL,        -- ISO 8601 from email_date
    is_recurring_candidate  INTEGER NOT NULL DEFAULT 0,   -- 1 for RECEIPT/RENEWAL patterns
    is_one_time_candidate   INTEGER NOT NULL DEFAULT 0,   -- 1 for Tier 0 RECEIPT + no cycle
    subscription_id       TEXT REFERENCES subscriptions(subscription_id) ON DELETE SET NULL,
    confidence_score      REAL NOT NULL DEFAULT 0.0,
    created_at            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_payment_events_source_msg
    ON payment_events(source_message_id);
CREATE INDEX IF NOT EXISTS idx_payment_events_merchant
    ON payment_events(merchant_name, event_date);
CREATE INDEX IF NOT EXISTS idx_payment_events_subscription
    ON payment_events(subscription_id);

INSERT OR IGNORE INTO schema_version (version, description, applied_at)
VALUES (7, 'payment_events table for individual financial events', datetime('now'));
