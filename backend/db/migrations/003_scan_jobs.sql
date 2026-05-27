-- Migration 003: scan_jobs table for background scan progress tracking
--
-- Stores scan job state so:
--   - The frontend can poll GET /api/scan/status/{scan_id} for live progress
--   - Server restarts mark in-flight jobs as 'interrupted' (safe re-run via dedup)
--   - No raw email content is stored here — only counts and metadata

CREATE TABLE IF NOT EXISTS scan_jobs (
    scan_id              TEXT PRIMARY KEY,
    account_id           TEXT,
    mode                 TEXT NOT NULL,
    scan_range           TEXT,
    content_access_level TEXT NOT NULL,
    status               TEXT NOT NULL DEFAULT 'pending'
                         CHECK(status IN ('pending','collecting','processing',
                                          'completed','failed','interrupted')),
    collected_ids        TEXT,               -- JSON array of Gmail message IDs
    total_ids            INTEGER DEFAULT 0,
    processed_count      INTEGER DEFAULT 0,
    detected_count       INTEGER DEFAULT 0,
    flagged_count        INTEGER DEFAULT 0,
    ignored_count        INTEGER DEFAULT 0,
    body_fetched_count   INTEGER DEFAULT 0,
    body_skipped_count   INTEGER DEFAULT 0,
    body_failed_count    INTEGER DEFAULT 0,
    error_message        TEXT,
    created_at           TEXT NOT NULL,
    started_at           TEXT,
    completed_at         TEXT,
    last_activity_at     TEXT
);

-- Privacy note: scan_jobs stores NO email content:
--   no subjects, no sender addresses, no body text, no source_message_ids.
--   Only counts, scan metadata, and the list of Gmail message IDs (opaque strings).

INSERT OR IGNORE INTO schema_version (version, description, applied_at)
VALUES (4, 'scan_jobs table for background scan progress tracking', datetime('now'));
