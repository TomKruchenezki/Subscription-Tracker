-- Phase 1 initial schema: subscriptions, email_records, user_settings, schema_version
-- Privacy constraint: no column may store email body content (enforced by test_no_body_in_schema.py)

CREATE TABLE IF NOT EXISTS subscriptions (
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
    source          TEXT NOT NULL DEFAULT 'MOCK',
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    CONSTRAINT valid_billing_cycle CHECK (billing_cycle IN ('MONTHLY', 'ANNUAL', 'WEEKLY', 'UNKNOWN')),
    CONSTRAINT valid_category      CHECK (category IN ('STREAMING', 'SAAS', 'NEWS', 'CLOUD', 'OTHER')),
    CONSTRAINT valid_status        CHECK (status IN ('ACTIVE', 'CANCELLED', 'PAUSED')),
    CONSTRAINT valid_source        CHECK (source IN ('MOCK', 'GMAIL'))
);

CREATE TABLE IF NOT EXISTS email_records (
    record_id         TEXT PRIMARY KEY,
    subscription_id   TEXT REFERENCES subscriptions(subscription_id) ON DELETE CASCADE,
    gmail_message_id  TEXT UNIQUE,
    sender_address    TEXT NOT NULL,
    sender_name       TEXT,
    subject           TEXT NOT NULL,
    email_date        TEXT NOT NULL,
    amount_extracted  REAL,
    currency_extracted TEXT,
    confidence_score  REAL NOT NULL DEFAULT 0.0,
    disposition       TEXT NOT NULL DEFAULT 'DETECTED',
    created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    CONSTRAINT valid_disposition CHECK (disposition IN ('DETECTED', 'FLAGGED', 'IGNORED')),
    CONSTRAINT valid_confidence  CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
    CONSTRAINT subject_length    CHECK (length(subject) <= 500)
);

CREATE TABLE IF NOT EXISTS user_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS schema_version (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    description TEXT
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_email_records_subscription_id  ON email_records(subscription_id);
CREATE INDEX IF NOT EXISTS idx_email_records_gmail_message_id ON email_records(gmail_message_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status           ON subscriptions(status);
CREATE INDEX IF NOT EXISTS idx_subscriptions_source           ON subscriptions(source);

INSERT OR IGNORE INTO schema_version (version, description) VALUES (1, 'Initial schema');
