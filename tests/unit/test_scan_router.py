"""Unit tests for scan router: mode parameter, scan_range shortcuts, threshold overrides."""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient


@pytest.fixture()
def client(db_path):
    """TestClient against the real FastAPI app using an in-memory test DB."""
    import os
    os.environ["DB_PATH"] = db_path
    os.environ["USE_MOCK"] = "true"
    from backend.api.app import app
    return TestClient(app)


@pytest.fixture()
def gmail_client(db_path):
    """TestClient with USE_MOCK=false for Gmail account selection tests."""
    import os
    os.environ["DB_PATH"] = db_path
    os.environ["USE_MOCK"] = "false"
    from backend.api.app import app
    return TestClient(app)


# ── Scan range shortcuts ───────────────────────────────────────────────────────

@pytest.mark.parametrize("scan_range,expected_days", [
    ("1m",  30),
    ("3m",  90),
    ("6m",  180),
    ("1y",  365),
    ("2y",  730),
    ("5y",  1825),
])
def test_scan_range_computes_correct_date_from(client, scan_range, expected_days):
    """scan_range shortcut must set date_from to approximately N days ago."""
    captured: list[dict] = []

    original_fetch = None

    def _patched_fetch(self, *, date_from=None, date_to=None, mode="deep", content_access_level="metadata_plus_snippet"):
        captured.append({"date_from": date_from, "mode": mode})
        return []

    from backend.sources.mock import MockEmailSource
    with patch.object(MockEmailSource, "fetch", _patched_fetch):
        resp = client.post(f"/api/scan?scan_range={scan_range}")

    assert resp.status_code == 200
    assert len(captured) == 1

    date_from = captured[0]["date_from"]
    assert date_from is not None, "date_from must be set when scan_range is provided"

    now = datetime.now(timezone.utc)
    expected = now - timedelta(days=expected_days)
    diff = abs((date_from - expected).total_seconds())
    assert diff < 60, (
        f"scan_range={scan_range!r} produced date_from={date_from}, "
        f"expected ~{expected_days} days ago (diff={diff:.0f}s)"
    )


# ── Mode parameter ─────────────────────────────────────────────────────────────

def test_scan_mode_defaults_to_deep(client):
    captured: list[dict] = []

    def _patched_fetch(self, *, date_from=None, date_to=None, mode="deep", content_access_level="metadata_plus_snippet"):
        captured.append({"mode": mode})
        return []

    from backend.sources.mock import MockEmailSource
    with patch.object(MockEmailSource, "fetch", _patched_fetch):
        resp = client.post("/api/scan")

    assert resp.status_code == 200
    assert captured[0]["mode"] == "deep"


@pytest.mark.parametrize("mode", ["quick", "deep", "forensic"])
def test_scan_mode_passed_to_source_fetch(client, mode):
    captured: list[dict] = []

    def _patched_fetch(self, *, date_from=None, date_to=None, mode="deep", content_access_level="metadata_plus_snippet"):
        captured.append({"mode": mode})
        return []

    from backend.sources.mock import MockEmailSource
    with patch.object(MockEmailSource, "fetch", _patched_fetch):
        resp = client.post(f"/api/scan?mode={mode}")

    assert resp.status_code == 200
    assert captured[0]["mode"] == mode


def test_invalid_mode_returns_422(client):
    resp = client.post("/api/scan?mode=turbo")
    assert resp.status_code == 422


# ── Mode threshold override ────────────────────────────────────────────────────

def test_scan_forensic_mode_uses_lower_threshold(client):
    """forensic mode should call process_email with review_threshold=0.30."""
    captured: list[dict] = []

    from backend.models.email_metadata import EmailMetadata
    from datetime import timezone

    def _patched_fetch(self, *, date_from=None, date_to=None, mode="deep", content_access_level="metadata_plus_snippet"):
        # Return one email so process_email is called
        return [EmailMetadata(
            source_message_id="test-msg-1",
            source_provider="MOCK",
            source_account_id="mock_default",
            source_account_email="demo@mock.local",
            sender_address="noreply@example-unknown.com",
            sender_name=None,
            subject="Your payment receipt $5.00",
            email_date=datetime.now(timezone.utc),
        )]

    from backend.sources.mock import MockEmailSource
    import backend.api.routers.scan as scan_router

    original_process = None

    def _patched_process(conn, email, review_threshold=None):
        captured.append({"review_threshold": review_threshold})
        from backend.detector.detector import DetectionResult
        return DetectionResult(
            source_message_id=email.source_message_id,
            disposition="IGNORED",
            confidence_score=0.1,
            subscription_id=None,
            canonical_name=None,
            event_type=None,
        )

    with (
        patch.object(MockEmailSource, "fetch", _patched_fetch),
        patch("backend.api.routers.scan.process_email", _patched_process),
    ):
        resp = client.post("/api/scan?mode=forensic")

    assert resp.status_code == 200
    assert len(captured) == 1
    assert captured[0]["review_threshold"] == pytest.approx(0.30), (
        f"forensic mode must pass threshold=0.30, got {captured[0]['review_threshold']}"
    )


def test_scan_quick_mode_uses_higher_threshold(client):
    """quick mode should call process_email with review_threshold=0.50."""
    captured: list[dict] = []
    from datetime import timezone

    def _patched_fetch(self, *, date_from=None, date_to=None, mode="deep", content_access_level="metadata_plus_snippet"):
        from backend.models.email_metadata import EmailMetadata
        return [EmailMetadata(
            source_message_id="test-msg-2",
            source_provider="MOCK",
            source_account_id="mock_default",
            source_account_email="demo@mock.local",
            sender_address="noreply@example-unknown.com",
            sender_name=None,
            subject="Your payment receipt $5.00",
            email_date=datetime.now(timezone.utc),
        )]

    def _patched_process(conn, email, review_threshold=None):
        captured.append({"review_threshold": review_threshold})
        from backend.detector.detector import DetectionResult
        return DetectionResult(
            source_message_id=email.source_message_id,
            disposition="IGNORED",
            confidence_score=0.1,
            subscription_id=None,
            canonical_name=None,
            event_type=None,
        )

    from backend.sources.mock import MockEmailSource
    with (
        patch.object(MockEmailSource, "fetch", _patched_fetch),
        patch("backend.api.routers.scan.process_email", _patched_process),
    ):
        resp = client.post("/api/scan?mode=quick")

    assert resp.status_code == 200
    assert captured[0]["review_threshold"] == pytest.approx(0.50)


# ── Gmail account selection ────────────────────────────────────────────────────

def test_scan_gmail_no_account_returns_409(gmail_client):
    """USE_MOCK=false + no Gmail account in DB → 409 with helpful message."""
    with patch("backend.api.routers.scan.get_active_gmail_account", return_value=None):
        resp = gmail_client.post("/api/scan?mode=quick&scan_range=1m")
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert "Gmail" in detail


def test_scan_gmail_uses_active_account_id(gmail_client):
    """USE_MOCK=false + one Gmail account → account_id is passed to get_email_source."""
    captured: list[str | None] = []
    fake_row = {"account_id": "user@gmail.com", "source_provider": "GMAIL", "is_active": 1}

    def fake_source(account_id=None):
        captured.append(account_id)
        mock_src = MagicMock()
        mock_src.fetch.return_value = []
        return mock_src

    with (
        patch("backend.api.routers.scan.get_active_gmail_account", return_value=fake_row),
        patch("backend.api.routers.scan.get_email_source", side_effect=fake_source),
    ):
        resp = gmail_client.post("/api/scan?mode=quick&scan_range=1m")

    assert resp.status_code == 200
    assert len(captured) == 1
    assert captured[0] == "user@gmail.com"


def test_scan_gmail_multiple_accounts_uses_first(gmail_client):
    """Multiple Gmail accounts → the account returned by get_active_gmail_account is used."""
    captured: list[str | None] = []
    # get_active_gmail_account is LIMIT 1 ORDER BY created_at, so first account wins
    fake_row = {"account_id": "first@gmail.com", "source_provider": "GMAIL", "is_active": 1}

    def fake_source(account_id=None):
        captured.append(account_id)
        mock_src = MagicMock()
        mock_src.fetch.return_value = []
        return mock_src

    with (
        patch("backend.api.routers.scan.get_active_gmail_account", return_value=fake_row),
        patch("backend.api.routers.scan.get_email_source", side_effect=fake_source),
    ):
        resp = gmail_client.post("/api/scan?mode=quick&scan_range=1m")

    assert resp.status_code == 200
    assert captured[0] == "first@gmail.com"


def test_scan_mock_mode_skips_gmail_account_lookup(client):
    """USE_MOCK=true → get_active_gmail_account is never called."""
    with patch("backend.api.routers.scan.get_active_gmail_account") as mock_lookup:
        resp = client.post("/api/scan")
    assert resp.status_code == 200
    mock_lookup.assert_not_called()


# ── Phase 2.6: source_provider filtering in endpoints ─────────────────────────

def _seed_mock_and_gmail_rows(db_path: str) -> None:
    """Insert one MOCK and one GMAIL subscription + email_record into the test DB."""
    import sqlite3, uuid
    conn = sqlite3.connect(db_path)
    now = "2026-01-01T00:00:00Z"

    for provider, name, amount in [("MOCK", "MockSvc", 5.00), ("GMAIL", "GmailSvc", 20.00)]:
        sub_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO subscriptions
               (subscription_id, name, service_url, amount, currency, billing_cycle,
                next_renewal, category, status, first_seen, last_seen,
                source_provider, created_at, updated_at)
               VALUES (?,?,NULL,?,?,?,NULL,?,?,?,?,?,?,?)""",
            (sub_id, name, amount, "USD", "MONTHLY", "SAAS", "ACTIVE",
             now, now, provider, now, now),
        )
        record_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO email_records
               (record_id, subscription_id, source_message_id, source_provider,
                source_account_id, source_account_email, sender_address,
                sender_name, subject, email_date, amount_extracted,
                currency_extracted, confidence_score, disposition, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (record_id, sub_id, f"msg-{provider}-001", provider,
             f"acct_{provider}", f"test@{provider.lower()}.local",
             f"billing@{name.lower()}.com", name, f"{name} receipt",
             now, amount, "USD", 0.9, "DETECTED", now),
        )
    conn.commit()
    conn.close()


def test_summary_gmail_mode_excludes_mock_rows(db_path, gmail_client):
    """GET /api/summary in Gmail mode returns active_count=1 (only GMAIL sub)."""
    _seed_mock_and_gmail_rows(db_path)
    with patch("backend.api.routers.scan.get_active_gmail_account",
               return_value={"account_id": "u@g.com", "is_active": 1}):
        resp = gmail_client.get("/api/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["active_count"] == 1, (
        f"Gmail mode summary should count 1 GMAIL sub, got {data['active_count']}"
    )
    assert data["total_monthly_cost"] == pytest.approx(20.00), (
        f"Gmail mode should sum only GMAIL sub ($20), got {data['total_monthly_cost']}"
    )
    assert data["has_mock_data"] is True, "has_mock_data must be True when MOCK rows exist"


def test_subscriptions_gmail_mode_excludes_mock_rows(db_path, gmail_client):
    """GET /api/subscriptions in Gmail mode returns only the GMAIL subscription."""
    _seed_mock_and_gmail_rows(db_path)
    resp = gmail_client.get("/api/subscriptions")
    assert resp.status_code == 200
    subs = resp.json()
    assert len(subs) == 1, f"Gmail mode should return 1 subscription (GMAIL only), got {len(subs)}"
    assert subs[0]["source_provider"] == "GMAIL"
    assert subs[0]["name"] == "GmailSvc"


def test_email_records_gmail_mode_excludes_mock_rows(db_path, gmail_client):
    """GET /api/email-records in Gmail mode returns only GMAIL email_records."""
    _seed_mock_and_gmail_rows(db_path)
    resp = gmail_client.get("/api/email-records")
    assert resp.status_code == 200
    records = resp.json()
    assert len(records) == 1, (
        f"Gmail mode should return 1 email_record (GMAIL only), got {len(records)}"
    )
    assert records[0]["source_provider"] == "GMAIL"


def test_mock_mode_shows_all_sources(db_path, client):
    """GET /api/subscriptions in MOCK mode (USE_MOCK=true) returns both MOCK and GMAIL rows."""
    _seed_mock_and_gmail_rows(db_path)
    resp = client.get("/api/subscriptions")
    assert resp.status_code == 200
    subs = resp.json()
    providers = {s["source_provider"] for s in subs}
    assert "MOCK" in providers, "Mock mode must show MOCK subscriptions"
    assert "GMAIL" in providers, "Mock mode must also show GMAIL subscriptions"
    assert len(subs) == 2, f"Mock mode should return both subs (2 total), got {len(subs)}"
