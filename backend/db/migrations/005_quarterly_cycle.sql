-- Migration 005: Add QUARTERLY to billing_cycle CHECK constraint.
--
-- cycle_detector.py already returns "QUARTERLY" for quarterly billing subjects, but the
-- original CHECK constraint in 001_initial_schema.sql does not include it.  SQLite does
-- not support ALTER TABLE ADD CONSTRAINT, so we recreate the subscriptions table.
--
-- The table includes all columns added by 001_initial_schema + 002_lifecycle:
--   first_charge_date, last_charge_date, cancelled_at, trial_ends_at
-- Foreign key enforcement is temporarily disabled during the swap.

PRAGMA foreign_keys = OFF;

CREATE TABLE IF NOT EXISTS subscriptions_v2 (
    subscription_id TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    service_url     TEXT,
    amount          REAL,
    currency        TEXT NOT NULL DEFAULT 'USD',
    billing_cycle   TEXT NOT NULL DEFAULT 'UNKNOWN',
    next_renewal    TEXT,
    category        TEXT NOT NULL DEFAULT 'OTHER',
    status          TEXT NOT NULL DEFAULT 'ACTIVE',
    first_seen      TEXT NOT NULL,
    last_seen       TEXT NOT NULL,
    source_provider TEXT NOT NULL DEFAULT 'MOCK',
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    first_charge_date TEXT,
    last_charge_date  TEXT,
    cancelled_at      TEXT,
    trial_ends_at     TEXT,
    CONSTRAINT valid_billing_cycle   CHECK (billing_cycle IN ('MONTHLY','ANNUAL','QUARTERLY','WEEKLY','UNKNOWN')),
    CONSTRAINT valid_category        CHECK (category IN ('STREAMING','SAAS','NEWS','CLOUD','OTHER')),
    CONSTRAINT valid_status          CHECK (status IN ('ACTIVE','CANCELLED','PAUSED','TRIAL','UNKNOWN')),
    CONSTRAINT valid_source_provider CHECK (source_provider IN ('MOCK','GMAIL','MICROSOFT','IMAP','UNKNOWN'))
);

INSERT INTO subscriptions_v2
    SELECT
        subscription_id, name, service_url, amount, currency, billing_cycle,
        next_renewal, category, status, first_seen, last_seen, source_provider,
        created_at, updated_at,
        first_charge_date, last_charge_date, cancelled_at, trial_ends_at
    FROM subscriptions;

DROP TABLE subscriptions;
ALTER TABLE subscriptions_v2 RENAME TO subscriptions;

CREATE INDEX IF NOT EXISTS idx_subscriptions_status          ON subscriptions(status);
CREATE INDEX IF NOT EXISTS idx_subscriptions_source_provider ON subscriptions(source_provider);

PRAGMA foreign_keys = ON;

INSERT OR IGNORE INTO schema_version (version, description, applied_at)
VALUES (6, 'Add QUARTERLY to billing_cycle CHECK constraint', datetime('now'));
