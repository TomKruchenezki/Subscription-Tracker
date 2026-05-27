-- Migration 004: Downgrade ACTIVE subscriptions with NULL amount to UNKNOWN
-- Safe, idempotent cleanup: will be upgraded back to ACTIVE when a confirmed
-- receipt with an extractable amount is processed in a future scan.

UPDATE subscriptions
SET    status     = 'UNKNOWN',
       updated_at = datetime('now')
WHERE  status = 'ACTIVE'
  AND  amount IS NULL;

INSERT OR IGNORE INTO schema_version (version, description, applied_at)
VALUES (5, 'Downgrade ACTIVE subscriptions with NULL amount to UNKNOWN', datetime('now'));
