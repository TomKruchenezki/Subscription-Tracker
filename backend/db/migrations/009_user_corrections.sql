-- Migration 009: User corrections, email_records dismiss flag, scan_jobs checkpoint
--
-- Adds:
--   user_corrections table      — audit trail for user-driven corrections (dismiss, confirm, reject, relabel)
--   email_records.user_dismissed — fast flag for dismissed review queue items (no JOIN needed)
--   scan_jobs.last_checkpoint_idx — enables resume of interrupted forensic scans
--
-- Privacy: user_corrections stores only structured IDs and correction_type.
-- No raw email content (subject, sender, body, snippet) is stored.

CREATE TABLE IF NOT EXISTS user_corrections (
    correction_id   TEXT PRIMARY KEY,
    email_record_id TEXT REFERENCES email_records(record_id) ON DELETE CASCADE,
    subscription_id TEXT REFERENCES subscriptions(subscription_id) ON DELETE CASCADE,
    correction_type TEXT NOT NULL CHECK(correction_type IN (
        'DISMISSED_EMAIL',   -- user dismissed from review queue (not a subscription)
        'CONFIRMED_SUB',     -- user confirmed UNKNOWN subscription as real
        'REJECTED_SUB',      -- user deleted/rejected subscription (false positive)
        'RELABELED'          -- user corrected provider/product canonical name
    )),
    new_value       TEXT,    -- for RELABELED: new canonical name; NULL for others
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_corrections_record ON user_corrections(email_record_id);
CREATE INDEX IF NOT EXISTS idx_corrections_sub    ON user_corrections(subscription_id);
CREATE INDEX IF NOT EXISTS idx_corrections_type   ON user_corrections(correction_type);

-- Fast filter: avoid full JOIN when loading Review Queue
ALTER TABLE email_records ADD COLUMN user_dismissed INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_email_records_dismissed
    ON email_records(user_dismissed)
    WHERE user_dismissed = 1;

-- Scan checkpoint: enables efficient resume of interrupted large scans.
-- Stores the index into collected_ids[] where Phase 2 processing last committed.
ALTER TABLE scan_jobs ADD COLUMN last_checkpoint_idx INTEGER NOT NULL DEFAULT 0;

INSERT OR IGNORE INTO schema_version (version, description, applied_at)
VALUES (
    10,
    'user_corrections table, email_records.user_dismissed, scan_jobs.last_checkpoint_idx',
    datetime('now')
);
