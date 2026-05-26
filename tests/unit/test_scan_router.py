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

    def _patched_fetch(self, *, date_from=None, date_to=None, mode="deep"):
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

    def _patched_fetch(self, *, date_from=None, date_to=None, mode="deep"):
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

    def _patched_fetch(self, *, date_from=None, date_to=None, mode="deep"):
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

    def _patched_fetch(self, *, date_from=None, date_to=None, mode="deep"):
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

    def _patched_fetch(self, *, date_from=None, date_to=None, mode="deep"):
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
