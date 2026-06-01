-- Migration 010: Explainability fields, detection_state, user_corrections expansion
--
-- Phase 3.6: Make the detection system explainable and correction-aware.
--
-- Privacy guarantee: all new TEXT fields store structured summaries only.
-- No raw email subject, body, HTML, snippet, sender address, or PII is stored in these fields.
-- decision_reason / evidence_summary / missing_evidence / suggested_action are computed
-- from structured detection signals (tier, pattern, amount, billing_cycle, score) only.

-- ── email_records: per-email explanation fields ────────────────────────────────
ALTER TABLE email_records ADD COLUMN decision_reason   TEXT;
ALTER TABLE email_records ADD COLUMN evidence_summary  TEXT;
ALTER TABLE email_records ADD COLUMN missing_evidence  TEXT;
ALTER TABLE email_records ADD COLUMN suggested_action  TEXT;

-- Per-email detection quality state (more nuanced than DETECTED/FLAGGED disposition)
ALTER TABLE email_records ADD COLUMN detection_state TEXT
    CHECK(detection_state IS NULL OR detection_state IN (
        'CONFIRMED_SUBSCRIPTION', 'LIKELY_SUBSCRIPTION', 'POSSIBLE_SUBSCRIPTION',
        'ONE_TIME_PAYMENT', 'REFUND', 'CANCELLATION', 'TRIAL',
        'NEEDS_ATTACHMENT_REVIEW', 'NEEDS_USER_REVIEW', 'IGNORED'
    ));

-- ── subscriptions: aggregate detection quality state ──────────────────────────
-- Does NOT replace status (ACTIVE/CANCELLED/PAUSED/TRIAL/UNKNOWN).
-- status = lifecycle/operational; detection_state = evidence quality.
ALTER TABLE subscriptions ADD COLUMN detection_state TEXT
    CHECK(detection_state IS NULL OR detection_state IN (
        'CONFIRMED_ACTIVE', 'LIKELY_SUBSCRIPTION', 'POSSIBLE_SUBSCRIPTION',
        'ONE_TIME_PAYMENT', 'NEEDS_ATTACHMENT_REVIEW', 'NEEDS_USER_REVIEW'
    ));

-- source_account_id on subscriptions (for multi-account visibility)
ALTER TABLE subscriptions ADD COLUMN source_account_id TEXT;

-- ── payment_events: explanation + one-time user flag ──────────────────────────
ALTER TABLE payment_events ADD COLUMN decision_reason       TEXT;
ALTER TABLE payment_events ADD COLUMN user_marked_one_time  INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_pe_user_marked_one_time
    ON payment_events(user_marked_one_time)
    WHERE user_marked_one_time = 1;

-- ── user_corrections: expand correction types + sender_address column ──────────
-- SQLite cannot ALTER TABLE to change a CHECK constraint, so we recreate.
-- sender_address enables sender-level blocking: corrections that affect future emails.
CREATE TABLE IF NOT EXISTS user_corrections_v2 (
    correction_id   TEXT PRIMARY KEY,
    email_record_id TEXT REFERENCES email_records(record_id) ON DELETE CASCADE,
    subscription_id TEXT REFERENCES subscriptions(subscription_id) ON DELETE CASCADE,
    sender_address  TEXT,  -- sender-level scope: affects all future emails from this address
    correction_type TEXT NOT NULL CHECK(correction_type IN (
        'DISMISSED_EMAIL',   -- user dismissed single review queue item
        'CONFIRMED_SUB',     -- user confirmed UNKNOWN subscription as real
        'REJECTED_SUB',      -- user deleted subscription — block re-creation from same sender
        'RELABELED',         -- user corrected provider/product canonical name
        'MARKED_ONE_TIME',   -- user marked event as one-time (not recurring subscription)
        'MERGED'             -- subscriptions merged (source into target via new_value)
    )),
    new_value       TEXT,   -- RELABELED: corrected name; MERGED: target_subscription_id
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

INSERT INTO user_corrections_v2
    SELECT correction_id, email_record_id, subscription_id,
           NULL AS sender_address,
           correction_type, new_value, created_at
    FROM user_corrections;

DROP TABLE user_corrections;
ALTER TABLE user_corrections_v2 RENAME TO user_corrections;

CREATE INDEX IF NOT EXISTS idx_corrections_record  ON user_corrections(email_record_id);
CREATE INDEX IF NOT EXISTS idx_corrections_sub     ON user_corrections(subscription_id);
CREATE INDEX IF NOT EXISTS idx_corrections_type    ON user_corrections(correction_type);
CREATE INDEX IF NOT EXISTS idx_corrections_sender  ON user_corrections(sender_address)
    WHERE sender_address IS NOT NULL;

-- ── schema_version ─────────────────────────────────────────────────────────────
INSERT OR IGNORE INTO schema_version (version, description, applied_at)
VALUES (
    11,
    'Phase 3.6: explanation fields on email_records/payment_events, detection_state on subscriptions/email_records, user_corrections expansion (MARKED_ONE_TIME, MERGED, sender_address)',
    datetime('now')
);
