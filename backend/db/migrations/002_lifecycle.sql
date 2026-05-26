-- Phase 1.2: lifecycle columns on subscriptions and email_records
-- billing_period_start/end are added but left NULL in Phase 1.2 (extraction deferred)

ALTER TABLE subscriptions ADD COLUMN first_charge_date TEXT;
ALTER TABLE subscriptions ADD COLUMN last_charge_date  TEXT;
ALTER TABLE subscriptions ADD COLUMN cancelled_at      TEXT;
ALTER TABLE subscriptions ADD COLUMN trial_ends_at     TEXT;

ALTER TABLE email_records ADD COLUMN event_type           TEXT;
ALTER TABLE email_records ADD COLUMN billing_period_start TEXT;
ALTER TABLE email_records ADD COLUMN billing_period_end   TEXT;
ALTER TABLE email_records ADD COLUMN short_evidence       TEXT;

INSERT OR IGNORE INTO schema_version (version, description)
VALUES (3, 'Phase 1.2: lifecycle columns — first/last_charge_date, event_type, short_evidence');
