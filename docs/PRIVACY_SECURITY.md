# Privacy & Security

This document is the authoritative reference for what the subscription tracker collects,
what it never touches, and how it defends against compromise. All code changes that affect
data collection, storage, or transmission must be reviewed against this document.

---

## Privacy Principles

1. **Data minimization** — Collect only what is necessary to identify a subscription.
   Every stored field must have a documented reason.
2. **Local-first** — All data stays on the user's machine in a local SQLite file.
   No cloud sync, no remote database, no third-party analytics.
3. **User ownership** — The user can view every stored field, export it, and delete
   it all with a single command. There are no hidden records.
4. **No telemetry** — The app never makes outbound HTTP calls except to Google's
   OAuth and Gmail API endpoints. No error reporting services, no usage analytics.
5. **Minimal OAuth scope** — `gmail.readonly` is the only Gmail permission ever
   requested. This is enforced in code and verified by a privacy compliance test.

---

## What We Collect

### From Gmail (metadata — plus transient body/attachment parsing in forensic mode)

| Field | Source | Why |
|---|---|---|
| `sender_address` | `From` header | Identify the subscription provider |
| `sender_name` | `From` header display name | Human-readable service name |
| `subject` | `Subject` header | Extract amount, cycle, and service name |
| `email_date` | `Date` header | Track renewal timeline |
| `gmail_message_id` | Message ID | Deduplication only — never shown in UI |

**Forensic mode only** additionally reads, **transiently and in memory**, the email body
(`format=full` in `_fetch_body()`) and PDF attachments (`messages.attachments.get` in
`_fetch_attachment_bytes()`, parsed by `pdfminer.six`). The raw body, raw bytes, and
extracted PDF text are discarded immediately after parsing. Only **structured fields**
(amount, currency, dates, billing cycle) and **coded reason tokens** are persisted —
never the raw text. Both use the existing `gmail.readonly` scope (no scope change).
Attachment metadata stored: filename, mime type, size, detected type, processing status.

### Derived by the app (computed locally, never transmitted)

| Field | Source |
|---|---|
| `subscription_name` | Resolved from sender domain |
| `amount` | Regex extracted from subject line |
| `currency` | Regex extracted from subject line |
| `billing_cycle` | Keyword detected in subject line |
| `next_renewal` | Estimated from last charge date + cycle |
| `confidence_score` | Scoring algorithm output |
| `category` | Rule-based label (STREAMING, SAAS, NEWS, OTHER) |

### User configuration (stored locally)

| Field | Notes |
|---|---|
| OAuth refresh token | Encrypted at rest — see Token Storage below |
| `last_scanned_at` | Timestamp of most recent Gmail scan |
| `scan_frequency_hours` | User preference |
| `ignored_senders` | User-defined exclusion list |

---

## What We Never Store

- **Raw email body text** — may be parsed transiently in forensic mode (`_fetch_body()`),
  but is never stored, logged, or returned by any API. Only a structured extract is used.
- **Raw PDF/attachment text or bytes** — parsed transiently in forensic mode
  (`_fetch_attachment_bytes()` → `pdfminer.six`), then discarded. Only structured fields
  and coded reason tokens are persisted (Phase 3.7). Never the raw text.
- **Inline images / non-PDF attachment content** — classified by metadata only; not parsed.
- **CC / BCC recipients**
- **Email thread history or replies**
- **Emails that do not match subscription patterns** — only emails that pass the
  detection threshold are recorded in `email_records`
- **IP address, device fingerprint, or browser metadata**
- **Bank account numbers, routing numbers, or any financial account identifiers**
- **Contacts from the user's address book**

---

## Threat Model

### Threat 1 — OAuth Token Theft

**Scenario:** An attacker reads the stored refresh token from disk.

**Impact:** They could read the user's Gmail metadata (subjects, senders, dates)
using the read-only token. They cannot send email, delete email, or access email bodies.

**Mitigations:**
- Refresh token is encrypted at rest using the OS keyring (`keyring` library) or
  AES-256 with a PBKDF2-derived key when keyring is unavailable.
- Access token is kept in memory only and never persisted to disk.
- Token is never written to `.env`, log files, or any plaintext file.
- **Important limitation of the file backend:** When `TOKEN_STORAGE_BACKEND=file`, the
  `TOKEN_ENCRYPTION_KEY` must come from somewhere. If it is stored in `.env`, an attacker
  who reads `.env` can decrypt the token file — co-location defeats the encryption.
  The file backend is intended for CI/headless environments only (where no human attacker
  has disk access). For personal use, always prefer `TOKEN_STORAGE_BACKEND=keyring`.

### Threat 2 — Database File Exfiltration

**Scenario:** An attacker copies `subscriptions.db`.

**Impact:** They obtain sender addresses, subject lines, amounts, and renewal dates
for matched subscriptions. No email bodies, no bank data, no credentials.

**Mitigations:**
- The database contains no email bodies and no financial account numbers,
  limiting its sensitivity.
- Future option: enable SQLite encryption via SQLCipher (not in MVP scope).

### Threat 3 — Gmail Scope Creep

**Scenario:** A future developer adds a broader Gmail scope to access email bodies
or enable write operations.

**Mitigations:**
- `CLAUDE.md` lists scope expansion as a non-negotiable violation.
- `tests/privacy/test_gmail_scope.py` asserts that the scopes list equals
  `["https://www.googleapis.com/auth/gmail.readonly"]` exactly. This test runs
  on every commit and blocks the build on failure.
- Agent definitions for `privacy-security-reviewer` and `gmail-integration-specialist`
  both enforce this rule.

### Threat 4 — Log Leakage of Sensitive Data

**Scenario:** Email content, token values, or user PII appears in log output
and is captured by a logging aggregator or visible to another process.

**Mitigations:**
- `LOG_LEVEL=INFO` by default. Subject lines may only appear in logs at DEBUG level.
- Token values are never logged at any level — the logging configuration filters
  fields named `token`, `secret`, `key`, `credential`.
- A privacy compliance test scans log output from a full mock pipeline run and
  asserts no log line from email-processing code exceeds 500 characters (a heuristic
  that would catch accidental body logging).

### Threat 5 — Dependency Supply Chain Compromise

**Scenario:** A compromised Python package dependency exfiltrates data.

**Mitigations:**
- Minimal dependency footprint — no analytics SDKs, no error-reporting clients,
  no third-party data enrichment libraries.
- All dependencies pinned to exact versions in `requirements.txt`.
- `pip-audit` run as part of the GitHub Actions CI pipeline (`.github/workflows/ci.yml`).

---

## OAuth Security Details

| Property | Value |
|---|---|
| Scope | `https://www.googleapis.com/auth/gmail.readonly` |
| Grant type | Authorization Code with PKCE |
| Application type | Desktop app (loopback redirect) |
| Token storage | OS keyring preferred; encrypted file for CI/headless only |
| Access token | Memory only — never persisted |
| Refresh token | Encrypted at rest |

Users can revoke app access at any time at:
`https://myaccount.google.com/permissions`

The app surfaces this link in the UI under Settings → Revoke Gmail Access.

---

## Data Deletion

To permanently delete all stored data:

```bash
python main.py --delete-all
```

This command:
1. Drops and recreates all tables in `subscriptions.db` (effectively a wipe)
2. Deletes the encrypted token from the OS keyring or token file
3. Clears the `user_settings` table
4. Prints a confirmation that all local data has been removed

There is no server-side backup because there is no server.
