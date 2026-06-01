-- Migration 011: Safe PDF/attachment receipt & invoice parsing (Phase 3.7).
--
-- Two tables capture attachment metadata and STRUCTURED PDF-derived evidence.
-- They store NO raw email or attachment content:
--   no body_text, body_html, snippet, raw PDF text, raw bytes, subject, or tokens.
--
-- Privacy guarantee (mirrors the existing ephemeral _fetch_body pattern):
--   Gmail attachment bytes are downloaded transiently (in memory), text is extracted
--   transiently with pdfminer.six, structured fields are derived, and the bytes AND
--   text are discarded immediately. Only the structured fields + short coded reason
--   tokens below are persisted.
--
-- Note: email_records.detection_state CHECK (migration 010) is intentionally left
-- UNCHANGED. PDF/attachment processing status lives on these new tables, not on
-- email_records — "add a separate field rather than replacing the existing status".

-- ── email_attachments: privacy-safe attachment metadata ───────────────────────
CREATE TABLE IF NOT EXISTS email_attachments (
    attachment_row_id        TEXT PRIMARY KEY,
    email_record_id          TEXT REFERENCES email_records(record_id) ON DELETE CASCADE,
    source_message_id        TEXT NOT NULL,           -- traceability key (opaque Gmail msg id)
    source_account_id        TEXT,
    gmail_attachment_id      TEXT,                    -- opaque Gmail attachment handle, NOT content
    filename                 TEXT,                    -- local-only metadata; never transmitted
    mime_type                TEXT,
    size_bytes               INTEGER,
    detected_attachment_type TEXT
        CHECK(detected_attachment_type IS NULL OR detected_attachment_type IN (
            'PDF_INVOICE', 'PDF_RECEIPT', 'PDF_OTHER', 'IMAGE', 'OTHER', 'UNSUPPORTED'
        )),
    processing_status        TEXT NOT NULL DEFAULT 'PENDING'
        CHECK(processing_status IN (
            'PENDING', 'PARSED', 'PARSE_FAILED', 'UNSUPPORTED', 'SKIPPED'
        )),
    parser_version           TEXT,
    created_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_attachments_record   ON email_attachments(email_record_id);
CREATE INDEX IF NOT EXISTS idx_attachments_message  ON email_attachments(source_message_id);
CREATE INDEX IF NOT EXISTS idx_attachments_status   ON email_attachments(processing_status);

-- ── attachment_extracted_fields: STRUCTURED PDF-derived evidence (no raw text) ─
-- All *_reasons / *_indicators columns hold SHORT CODED TOKENS (e.g.
-- 'amount_in_pdf;billing_period_found'), never sentences or text copied from the PDF.
CREATE TABLE IF NOT EXISTS attachment_extracted_fields (
    field_row_id            TEXT PRIMARY KEY,
    attachment_row_id       TEXT REFERENCES email_attachments(attachment_row_id) ON DELETE CASCADE,
    email_record_id         TEXT,
    source_message_id       TEXT,
    provider                TEXT,                     -- canonical provider (e.g. 'Spotify')
    product_name            TEXT,
    amount                  REAL,
    currency                TEXT,                     -- ISO 4217; NULL when unknown
    invoice_date            TEXT,
    payment_date            TEXT,
    billing_period_start    TEXT,
    billing_period_end      TEXT,
    inferred_cycle          TEXT,                     -- MONTHLY/ANNUAL/... or NULL
    tax_amount              REAL,
    invoice_number          TEXT,
    subscription_indicators TEXT,                     -- coded tokens, e.g. 'auto_renew;monthly_plan'
    evidence_reasons        TEXT,                     -- coded tokens, e.g. 'amount_in_pdf'
    missing_evidence        TEXT,                     -- coded tokens, e.g. 'no_recurring_wording'
    penalty_reasons         TEXT,                     -- coded tokens, e.g. 'receipt_one_time_no_recurring'
    confidence_score        REAL NOT NULL DEFAULT 0.0,
    extraction_status       TEXT
        CHECK(extraction_status IS NULL OR extraction_status IN (
            'OK', 'NO_TEXT', 'NO_FIELDS', 'FAILED'
        )),
    parser_version          TEXT,
    created_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_attfields_attachment ON attachment_extracted_fields(attachment_row_id);
CREATE INDEX IF NOT EXISTS idx_attfields_record     ON attachment_extracted_fields(email_record_id);
CREATE INDEX IF NOT EXISTS idx_attfields_message    ON attachment_extracted_fields(source_message_id);

INSERT OR IGNORE INTO schema_version (version, description, applied_at)
VALUES (
    12,
    'Phase 3.7: email_attachments + attachment_extracted_fields (structured PDF-derived evidence; no raw text)',
    datetime('now')
);
