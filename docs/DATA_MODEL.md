# Data Model

Local SQLite database. Path configured by `DB_PATH` env var (default: `data/subscriptions.db`).

**Hard constraint:** No column in any table may store email body text, HTML, raw content,
or attachments. This is enforced by `tests/privacy/test_no_body_in_schema.py`, which
inspects the live SQLite schema and fails the build if any column name contains:
`body`, `content`, `html`, `raw`, `full`, `snippet`, `payload`.

Note: `text` is intentionally excluded from this list — it is a SQL column type keyword
and would produce false positives on legitimate column type declarations.

---

## Table: `subscriptions`

One row per identified recurring subscription.

```sql
CREATE TABLE subscriptions (
    subscription_id  TEXT PRIMARY KEY,          -- UUID v4
    name             TEXT NOT NULL,             -- e.g. "Netflix", "Spotify"
    service_url      TEXT,                      -- e.g. "netflix.com"
    amount           REAL,                      -- e.g. 15.99
    currency         TEXT NOT NULL DEFAULT 'USD',
    billing_cycle    TEXT NOT NULL DEFAULT 'UNKNOWN',
                                                -- MONTHLY | ANNUAL | WEEKLY | UNKNOWN
    next_renewal     DATE,                      -- estimated next charge date
    category         TEXT NOT NULL DEFAULT 'OTHER',
                                                -- STREAMING | SAAS | NEWS | CLOUD | OTHER
    status           TEXT NOT NULL DEFAULT 'ACTIVE',
                                                -- ACTIVE | CANCELLED | PAUSED
    first_seen       DATETIME NOT NULL,         -- date of earliest matching email
    last_seen        DATETIME NOT NULL,         -- date of most recent matching email
    source           TEXT NOT NULL DEFAULT 'MOCK',
                                                -- MOCK | GMAIL
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

---

## Table: `email_records`

One row per email that matched the detection threshold. Stores metadata only.

```sql
CREATE TABLE email_records (
    record_id          TEXT PRIMARY KEY,        -- UUID v4
    subscription_id    TEXT NOT NULL REFERENCES subscriptions(subscription_id)
                           ON DELETE CASCADE,
    gmail_message_id   TEXT,                   -- Gmail message ID — dedup only,
                                               -- never displayed in UI
    sender_address     TEXT NOT NULL,          -- e.g. "no-reply@netflix.com"
    sender_name        TEXT,                   -- e.g. "Netflix"
    subject            TEXT NOT NULL,          -- subject line — NOT body (max 500 chars)
    email_date         DATETIME NOT NULL,
    amount_extracted   REAL,                   -- parsed amount, NULL if not found
    currency_extracted TEXT,
    confidence_score   REAL NOT NULL,          -- 0.0 to 1.0
    disposition        TEXT NOT NULL DEFAULT 'DETECTED',
                                               -- DETECTED | FLAGGED | IGNORED
    created_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT subject_length CHECK (length(subject) <= 500),
    CONSTRAINT valid_confidence CHECK (
        confidence_score >= 0.0 AND confidence_score <= 1.0
    ),
    CONSTRAINT valid_disposition CHECK (
        disposition IN ('DETECTED', 'FLAGGED', 'IGNORED')
    )
);
```

**Prohibited columns** (must never be added to this table):
`body`, `body_html`, `body_text`, `raw`, `snippet`, `payload`, `content`, `html_content`

The `disposition` column was added to enable the user-review queue (FLAGGED records)
and for accurate dashboard filtering. It is not body content.

---

## Table: `user_settings`

Key/value store for user preferences and scan state.

```sql
CREATE TABLE user_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

**Standard keys:**

| Key | Example value | Notes |
|---|---|---|
| `last_scanned_at` | `2025-01-15T08:30:00Z` | Updated after every Gmail scan |
| `scan_frequency_hours` | `24` | How often to auto-scan |
| `ignored_senders` | `["noreply@promo.com"]` | JSON list of excluded senders |
| `currency_preference` | `USD` | Display currency for dashboard |

**OAuth refresh token is NOT stored here.** It is stored in the OS keyring or
an encrypted file via `backend/auth/token_store.py`.

---

## Table: `schema_version`

Tracks applied migrations. Simple integer versioning.

```sql
CREATE TABLE schema_version (
    version     INTEGER NOT NULL,
    applied_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    description TEXT
);
```

Migrations live in `backend/db/migrations/` as numbered SQL files
(e.g., `001_initial_schema.sql`, `002_add_category.sql`).

---

## Indexes

```sql
-- Detection queries filter by sender domain
CREATE INDEX idx_email_records_sender ON email_records(sender_address);

-- Incremental scan queries filter by date
CREATE INDEX idx_email_records_date ON email_records(email_date);

-- Dashboard queries filter by status and cycle
CREATE INDEX idx_subscriptions_status ON subscriptions(status, billing_cycle);
```

---

## Privacy Compliance Enforcement

`tests/privacy/test_no_body_in_schema.py` performs:
1. Opens the SQLite database at `DB_PATH`
2. Queries `PRAGMA table_info(email_records)`
3. Asserts that no column name contains any of the prohibited terms
4. Runs on every `pytest` invocation — not opt-in

Any migration that adds a prohibited column must be rejected in code review before
it can be applied. The test acts as a safety net, not a replacement for review.
