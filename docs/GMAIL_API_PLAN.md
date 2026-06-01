# Gmail API Integration Plan

This document covers the OAuth 2.0 flow, email fetching strategy, rate limiting approach,
and the mock-to-real migration path. Implementation begins in Phase 2 of the roadmap —
Phase 1 uses mock data exclusively.

---

## OAuth 2.0 Flow

**Grant type:** Authorization Code with PKCE (recommended by Google for desktop/local apps)

**Application type in GCP:** Desktop app (OAuth 2.0 Client ID → Desktop application)

**Why the user must create their own GCP project:**
Sharing OAuth credentials in a repo is a security risk and violates Google's terms.
The setup guide in README.md walks users through the one-time GCP setup.

### Flow Steps

```
1. App generates PKCE code_verifier and code_challenge
2. App opens browser to Google's authorization URL:
       https://accounts.google.com/o/oauth2/v2/auth
       ?client_id=...
       &redirect_uri=http://localhost:8080/oauth/callback
       &response_type=code
       &scope=https://www.googleapis.com/auth/gmail.readonly
       &code_challenge=...
       &code_challenge_method=S256
       &access_type=offline
       &prompt=consent
3. User reviews permissions in browser (read-only Gmail access shown)
4. Google redirects to localhost:8080/oauth/callback with `code` param
5. App's local HTTP server (run temporarily) captures the code
6. App exchanges code + code_verifier for access_token + refresh_token
7. Refresh token → encrypted storage (keyring or encrypted file)
8. Access token → in-memory only, never persisted
```

### Scope Declaration (Non-Negotiable)

```python
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
```

This list must never be extended. `tests/privacy/test_gmail_scope.py` asserts its exact
value. Any PR that changes this list must be rejected.

---

## Email Fetching Strategy

All Gmail API calls are made from `backend/sources/gmail.py`.
The output is always a `List[EmailMetadata]` — the same interface as the mock source.

### Step 1: List Matching Messages

```
GET https://www.googleapis.com/gmail/v1/users/me/messages
    ?q={query}
    &maxResults=100
    &pageToken={pageToken}   (omit on first page)
```

**Query construction** — detect subscription-related emails using Gmail search operators:

```python
QUERY_PARTS = [
    "subject:receipt",
    "subject:invoice",
    "subject:subscription",
    "subject:renewal",
    "subject:billing",
    "subject:payment",
    "subject:(your plan)",
    "subject:(membership renewed)",
]

def build_query(last_scanned_at: datetime | None) -> str:
    parts = " OR ".join(f"({p})" for p in QUERY_PARTS)
    if last_scanned_at:
        date_str = last_scanned_at.strftime("%Y/%m/%d")
        parts += f" after:{date_str}"
    return parts
```

### Step 2: Fetch Message Metadata

For each message ID returned by the list call:

```
GET https://www.googleapis.com/gmail/v1/users/me/messages/{id}
    ?format=metadata
    &metadataHeaders=From
    &metadataHeaders=Subject
    &metadataHeaders=Date
```

**Critical:** `format=metadata` is the only valid value. The API will not return body
content with this format. This is enforced by `tests/privacy/test_no_body_fetch.py`.

**Headers requested:** `From`, `Subject`, `Date` — nothing else.

### Step 3: Parse and Emit EmailMetadata

```python
@dataclass
class EmailMetadata:
    message_id: str        # Gmail message ID (for dedup)
    sender_address: str
    sender_name: str
    subject: str
    email_date: datetime
    source: Literal["MOCK", "GMAIL"]
```

Both `backend/sources/mock.py` and `backend/sources/gmail.py` return `List[EmailMetadata]`.
The detection and parsing layers never interact with raw Gmail API responses.

---

## Transient content fetch (forensic mode only)

Two calls read content beyond headers. Both run **only** in forensic mode, use the
existing `gmail.readonly` scope (no scope change), and process the result **transiently
in memory** — the raw content is discarded immediately and is NEVER stored, logged, or
returned by any API. Each is isolated to a single method (enforced by
`tests/privacy/test_no_body_fetch.py`).

| Method | Where | What is kept |
|---|---|---|
| `messages.get` with `format=full` | `_fetch_body()` only | a plain-text excerpt for parsing (discarded after extraction) |
| `messages.attachments.get` | `_fetch_attachment_bytes()` only | nothing — bytes → `pdf_extractor` → structured fields, then discarded |

For attachments: `_fetch_body()`'s `format=full` payload already lists attachment PART
METADATA (filename, mime type, size, opaque `attachmentId`) with **no** new call. Only
the PDF bytes require `messages.attachments.get`, and only structured fields (amount,
currency, dates, cycle, coded reason tokens) are persisted — never the raw PDF text.

## What We Never Call

These API methods are not used and must never be added:

| Method | Reason excluded |
|---|---|
| `messages.get` with `format=raw` | Returns base64-encoded raw email |
| `messages.get` with `format=minimal` | Still exposes snippet (body excerpt) |
| `threads.get` | Returns full thread including bodies |
| Any method from `gmail.modify` scope | Not accessible — wrong scope |
| Any method from `gmail.compose` scope | Not accessible — wrong scope |

---

## Incremental Scanning

After the initial full scan, subsequent scans only fetch new emails.

- `last_scanned_at` is stored in `user_settings` (key: `last_scanned_at`)
- Each Gmail query appends `after:{YYYY/MM/DD}` using `last_scanned_at`
- After a successful scan completes, `last_scanned_at` is updated
- If a scan fails mid-way, `last_scanned_at` is NOT updated — the full range is retried

---

## Rate Limiting and Quota

Gmail API quota: 1 billion units/day (project-level). Relevant costs:

| API call | Units |
|---|---|
| `messages.list` | 5 units per call |
| `messages.get` (metadata) | 5 units per call |

For a mailbox with 500 matching emails: ~2,500 units for a full scan — well within quota.

**Exponential backoff on 429 / 500 responses:**

```python
RETRY_DELAYS = [1, 2, 4, 8, 16, 32, 60]   # seconds; cap at 60
MAX_RETRIES = 7
```

Implemented in `backend/utils/retry.py` as a decorator applied to all API call functions.

**Scan frequency:** Configurable via `scan_frequency_hours` (default: 24 hours).
Minimum enforced: 1 hour between scans (prevents runaway re-scans on app restart loops).

---

## Mock-to-Real Migration

The mock source (`USE_MOCK=true`) and the Gmail source use the same interface.
Switching is controlled entirely by environment configuration:

```python
# backend/sources/factory.py
def get_email_source() -> EmailSource:
    if os.getenv("USE_MOCK", "true").lower() == "true":
        return MockEmailSource("data/mock/mock_emails.json")
    return GmailEmailSource()
```

No detection, parsing, or database code changes when switching sources.
Integration tests verify both sources produce equivalent output for the same
subscription patterns.

---

## Error Handling

| Error | Handling |
|---|---|
| `google.auth.exceptions.RefreshError` | Token expired or revoked — clear stored token, prompt re-auth |
| `HttpError 429` (rate limited) | Exponential backoff via retry decorator |
| `HttpError 500` / `503` | Same backoff |
| `HttpError 403` (forbidden) | Likely scope issue — surface clear error message |
| Network timeout | Retry up to 3 times with 5s delay; surface error to UI if all retries fail |
| Malformed message (missing headers) | Log at WARNING, skip the message, continue scan |
