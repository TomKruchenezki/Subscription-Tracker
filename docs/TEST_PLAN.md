# Test Plan

---

## Testing Philosophy

1. **Privacy compliance tests are the gate** — they must never fail under any circumstances.
   A failing privacy test blocks all other work, regardless of feature pressure.
2. **Mock data first** — all unit tests run against synthetic fixtures in `data/mock/`.
   No real Gmail API calls in unit tests, ever.
3. **Tests are written before implementation** — privacy tests and interface tests are
   written as part of Phase 1 scaffolding, before the code they test exists.
4. **Deterministic assertions** — every test asserts a specific expected value, not
   just "no exception was raised". Confidence scores, detected subscriptions, and
   database state are all asserted precisely.

---

## Directory Structure

```
conftest.py                       # root conftest — registers --integration flag,
                                  # provides db_path fixture (in-memory schema)
pytest.ini                        # registers custom markers (integration, slow)

tests/
  privacy/                        # MUST NEVER FAIL — run on every pytest invocation
    test_no_body_in_schema.py     # uses db_path fixture from conftest.py
    test_gmail_scope.py           # skips gracefully in Phase 1 (ImportError)
    test_no_body_fetch.py         # skips gracefully in Phase 1 (ImportError)
    test_no_logging_of_bodies.py
    test_token_not_plaintext.py

  unit/
    test_amount_extractor.py
    test_sender_resolver.py
    test_cycle_detector.py
    test_confidence_scorer.py
    test_detector.py
    test_database.py
    test_api_endpoints.py

  integration/                    # requires pytest --integration flag
    test_gmail_api.py             # mocked HTTP, not live Gmail
    test_full_pipeline.py         # mock → detect → store → retrieve

data/mock/
  mock_emails.json                # 50+ synthetic email metadata records
  expected_detections.json        # expected outcome for each record
```

**`conftest.py` responsibilities:**
- Register `--integration` as a custom pytest command-line option
  (`pytest_addoption` hook with `parser.addoption("--integration", action="store_true")`)
- Provide `db_path` fixture: creates an in-memory SQLite database, applies all migration
  SQL files from `backend/db/migrations/`, yields the path, tears down after test
- Skip integration tests automatically unless `--integration` is passed
  (`autouse` marker applied via `pytest_collection_modifyitems`)

---

## Privacy Compliance Tests (`tests/privacy/`)

These tests run automatically on every `pytest` invocation. They cannot be skipped.

### `test_no_body_in_schema.py`

**What it checks:** The live SQLite schema contains no column names with prohibited terms.

**Bootstrap note:** The database must exist for this test to run. `conftest.py` provides
a `db_path` fixture that creates an in-memory SQLite database with the full schema applied
from the migration files, so the test runs correctly even on a fresh checkout with no
`subscriptions.db` on disk.

```python
PROHIBITED_TERMS = ["body", "content", "html", "raw", "full", "snippet", "payload"]
# Note: "text" is intentionally excluded — it is a SQL column type keyword.

def test_email_records_has_no_body_columns(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.execute("PRAGMA table_info(email_records)")
    columns = [row[1].lower() for row in cursor.fetchall()]
    for term in PROHIBITED_TERMS:
        assert not any(term in col for col in columns), (
            f"Column containing '{term}' found in email_records: {columns}"
        )
```

### `test_gmail_scope.py`

**What it checks:** The OAuth scope list equals exactly the expected value.

**Phase note:** `backend.auth.oauth` is a Phase 2 module. In Phase 1 the import will fail.
The test handles this gracefully with `pytest.skip` so the privacy suite still passes.

```python
EXPECTED_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

def test_oauth_scopes_are_readonly_only():
    try:
        from backend.auth.oauth import SCOPES
    except ImportError:
        pytest.skip("backend.auth.oauth not yet implemented (Phase 2 module)")
    assert SCOPES == EXPECTED_SCOPES, (
        f"OAuth scopes changed! Expected {EXPECTED_SCOPES}, got {SCOPES}"
    )
```

### `test_no_body_fetch.py`

**What it checks:** Gmail API `messages.get` is always called with `format="metadata"`.

**Phase note:** `backend.sources.gmail` is a Phase 2 module. Same `try/except ImportError →
pytest.skip(...)` pattern applies. The test is written in Phase 1 but skips until Phase 2.

Uses `unittest.mock.patch` to intercept the Gmail API client.
Asserts that every call to `messages().get()` has `format="metadata"` in its kwargs.
Also asserts that `metadataHeaders` only contains `["From", "Subject", "Date"]`.

### `test_no_logging_of_bodies.py`

**What it checks:** Log output from a full mock pipeline run contains no suspiciously
long lines from email-processing code (heuristic for accidental body logging).

```python
MAX_EMAIL_LOG_LINE_LENGTH = 500

def test_no_body_content_in_logs(caplog):
    with caplog.at_level(logging.DEBUG):
        run_full_mock_pipeline()
    for record in caplog.records:
        if record.name.startswith("backend."):
            assert len(record.message) <= MAX_EMAIL_LOG_LINE_LENGTH, (
                f"Suspiciously long log line from {record.name}: {record.message[:100]}..."
            )
```

### `test_token_not_plaintext.py`

**What it checks:** If a token file exists at the configured path, its contents are
not a valid plain JSON Google credential object.

```python
def test_token_file_is_not_plaintext_json(token_file_path):
    if not os.path.exists(token_file_path):
        pytest.skip("No token file present — nothing to check")
    with open(token_file_path, "rb") as f:
        contents = f.read()
    try:
        parsed = json.loads(contents)
        # If it parsed as JSON, check it's not a Google credential
        assert "access_token" not in parsed
        assert "refresh_token" not in parsed
    except json.JSONDecodeError:
        pass  # Non-JSON content = encrypted, which is what we want
```

---

## Unit Test: Amount Extractor (`tests/unit/test_amount_extractor.py`)

Parametrized test cases covering:

| Subject | Expected amount | Expected currency |
|---|---|---|
| `"Your Netflix subscription: $15.49"` | `15.49` | `USD` |
| `"Invoice #1234 — $9.99 charged"` | `9.99` | `USD` |
| `"Spotify receipt: 9.99 USD"` | `9.99` | `USD` |
| `"Annual plan: $99.00/year"` | `99.00` | `USD` |
| `"Your free trial has ended"` | `None` | `None` |
| `"50% off your next month"` | `None` | `None` (amount outside range or promotional) |
| `"Charged £8.99"` | `8.99` | `GBP` |
| `"Renewal: €12.99 EUR"` | `12.99` | `EUR` |
| `"Amount: $0.99"` | `0.99` | `USD` (lower bound) |
| `"Invoice: $999.99"` | `999.99` | `USD` (upper bound) |
| `"Invoice: $1500.00"` | `None` | `None` (above range) |

---

## Unit Test: Confidence Scorer (`tests/unit/test_confidence_scorer.py`)

Parametrized test cases asserting exact score output:

| Scenario | Expected score | Expected disposition |
|---|---|---|
| Tier 1 sender + receipt pattern + amount | 1.0 | DETECTED |
| Tier 1 sender + renewal pattern | 0.85 | DETECTED |
| Tier 1 sender + promotional pattern | 0.30 | IGNORED |
| Tier 2 sender + receipt pattern | 0.60 | FLAGGED |
| No sender match + invoice pattern + amount | 0.40 | FLAGGED |
| No sender match + promotional | 0.00 | IGNORED |
| Tier 1 sender + no subject match | 0.60 | FLAGGED |

---

## Unit Test: Detector (`tests/unit/test_detector.py`)

- Test that a duplicate `gmail_message_id` does not create a second `email_records` row
- Test that a cancellation confirmation updates `status` to `CANCELLED` on existing record
- Test that a trial end email creates an ACTIVE subscription with a note
- Test that an Amazon order email from `amazon.com` is NOT detected (exclusion list)
- Test that `primevideo.com` billing IS detected (different domain, same company)

---

## Mock Email Fixture Design (`data/mock/mock_emails.json`)

Minimum 50 synthetic email records before Phase 2 begins.

Each record must include:

```json
{
  "message_id": "mock_001",
  "sender_address": "no-reply@netflix.com",
  "sender_name": "Netflix",
  "subject": "Your Netflix membership receipt",
  "email_date": "2025-01-15T08:00:00Z",
  "source": "MOCK",
  "expected_outcome": "DETECTED",
  "expected_subscription_name": "Netflix",
  "expected_amount": 15.49,
  "expected_billing_cycle": "MONTHLY"
}
```

**Coverage targets:**

| Category | Minimum count |
|---|---|
| Tier 1 sender receipts (clear billing emails) | 12 |
| Renewal notices | 8 |
| Trial end notifications | 5 |
| Cancellation confirmations | 5 |
| Promotional / marketing emails (should NOT detect) | 8 |
| Ambiguous edge cases (expected: FLAGGED) | 7 |
| Noise — non-subscription emails | 5 |
| **Total** | **50** |

**Data rules for fixtures:**
- No real email addresses — use `@example-service.com` pattern
- Use round numbers for amounts: $4.99, $9.99, $14.99, $15.49, $99.00, $12.00
- Use future dates relative to 2025 so fixtures remain realistic
- No personally identifiable content anywhere in the fixture data

---

## Integration Test Design (`tests/integration/`)

Requires `pytest --integration` flag and is skipped in normal CI.

### `test_gmail_api.py`

- Uses `responses` library to mock HTTP calls to Gmail API endpoints
- Verifies that the Gmail source correctly builds the metadata query
- Verifies that the HTTP response is parsed into `List[EmailMetadata]` correctly
- Verifies that pagination is handled (multiple pages of results)
- Verifies that `format=metadata` appears in every mocked request

### `test_full_pipeline.py`

- Runs the full pipeline: source → parser → detector → database → API response
- Uses the mock source
- Asserts that the database state after a run matches `expected_detections.json`
- Asserts that no prohibited column names appear in stored data

---

## Test Execution Commands

```bash
# Run all tests (privacy + unit) — no credentials needed
pytest

# Run only privacy compliance tests
pytest tests/privacy/ -v

# Run only unit tests
pytest tests/unit/ -v

# Run with integration tests (requires test Gmail credentials)
pytest --integration

# Run with coverage report
pytest --cov=backend --cov-report=term-missing

# Run a specific test file
pytest tests/unit/test_detector.py -v
```

Privacy compliance tests are never excluded from any run. There is no `--no-privacy`
flag and one must not be added.
