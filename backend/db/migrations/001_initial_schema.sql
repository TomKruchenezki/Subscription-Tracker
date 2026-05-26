-- Phase 1.1 schema: provider-agnostic naming, connected_accounts table
-- Privacy constraint: no column may store email body content (enforced by test_no_body_in_schema.py)

CREATE TABLE IF NOT EXISTS connected_accounts (
    account_id      TEXT PRIMARY KEY,
    source_provider TEXT NOT NULL,
    account_email   TEXT NOT NULL,
    display_name    TEXT,
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

INSERT OR IGNORE INTO connected_accounts
    (account_id, source_provider, account_email, display_name)
VALUES ('mock_default', 'MOCK', 'demo@mock.local', 'Mock Demo Account');

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
    source_provider TEXT NOT NULL DEFAULT 'MOCK',
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    CONSTRAINT valid_billing_cycle   CHECK (billing_cycle IN ('MONTHLY', 'ANNUAL', 'WEEKLY', 'UNKNOWN')),
    CONSTRAINT valid_category        CHECK (category IN ('STREAMING', 'SAAS', 'NEWS', 'CLOUD', 'OTHER')),
    CONSTRAINT valid_status          CHECK (status IN ('ACTIVE', 'CANCELLED', 'PAUSED')),
    CONSTRAINT valid_source_provider CHECK (source_provider IN ('MOCK', 'GMAIL', 'MICROSOFT', 'IMAP', 'UNKNOWN'))
);

CREATE TABLE IF NOT EXISTS email_records (
    record_id            TEXT PRIMARY KEY,
    subscription_id      TEXT REFERENCES subscriptions(subscription_id) ON DELETE CASCADE,
    source_message_id    TEXT UNIQUE,
    source_provider      TEXT NOT NULL DEFAULT 'MOCK',
    source_account_id    TEXT NOT NULL DEFAULT 'mock_default',
    source_account_email TEXT NOT NULL DEFAULT 'demo@mock.local',
    sender_address       TEXT NOT NULL,
    sender_name          TEXT,
    subject              TEXT NOT NULL,
    email_date           TEXT NOT NULL,
    amount_extracted     REAL,
    currency_extracted   TEXT,
    confidence_score     REAL NOT NULL DEFAULT 0.0,
    disposition          TEXT NOT NULL DEFAULT 'DETECTED',
    created_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
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
CREATE INDEX IF NOT EXISTS idx_email_records_subscription_id   ON email_records(subscription_id);
CREATE INDEX IF NOT EXISTS idx_email_records_source_message_id ON email_records(source_message_id);
CREATE INDEX IF NOT EXISTS idx_email_records_source_account_id ON email_records(source_account_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status            ON subscriptions(status);
CREATE INDEX IF NOT EXISTS idx_subscriptions_source_provider   ON subscriptions(source_provider);

INSERT OR IGNORE INTO schema_version (version, description)
VALUES (2, 'Provider-agnostic naming: source_message_id, connected_accounts, source_provider');
