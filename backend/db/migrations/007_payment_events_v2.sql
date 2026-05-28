-- Migration 007: Fix payment_events event_type semantics.
--
-- Phase 3.3 created payment_events for ALL email_records (including non-financial ones)
-- and collapsed RENEWAL into 'subscription_charge'. This migration drops the incorrectly
-- populated table and recreates it with:
--   1. 'renewal_charge' added to the event_type CHECK constraint
--   2. Indexes on event_date and event_type for dashboard queries
--
-- Data note: Phase 3.3 data was created with wrong logic. Dropping it is intentional.
-- A fresh forensic scan repopulates payment_events with correct event types.
--
-- Privacy: table stores NO raw email content. merchant_name is the canonical service
-- name from sender_list.py, never the raw sender address or email subject.

DROP TABLE IF EXISTS payment_events;

CREATE TABLE payment_events (
    event_id              TEXT PRIMARY KEY,
    source_message_id     TEXT NOT NULL,        -- traceability key only; NOT a FK
    source_provider       TEXT NOT NULL,
    source_account_id     TEXT NOT NULL DEFAULT 'mock_default',
    event_type            TEXT NOT NULL
        CHECK(event_type IN (
            'subscription_charge', 'renewal_charge', 'one_time_charge',
            'refund', 'cancellation',
            'trial_started', 'trial_ended', 'failed_payment', 'price_change',
            'unknown_payment'
        )),
    amount                REAL,                 -- NULL when not extracted
    currency              TEXT,                 -- ISO 4217 native currency; NULL when unknown
    merchant_name         TEXT NOT NULL,        -- canonical service name, e.g. 'Spotify'
    event_date            TEXT NOT NULL,        -- ISO 8601 date from email_date
    is_recurring_candidate  INTEGER NOT NULL DEFAULT 0,
    is_one_time_candidate   INTEGER NOT NULL DEFAULT 0,
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
CREATE INDEX IF NOT EXISTS idx_payment_events_type
    ON payment_events(event_type);
CREATE INDEX IF NOT EXISTS idx_payment_events_date
    ON payment_events(event_date DESC);

INSERT OR IGNORE INTO schema_version (version, description, applied_at)
VALUES (8, 'payment_events v2: add renewal_charge, drop incorrect Phase 3.3 data', datetime('now'));
