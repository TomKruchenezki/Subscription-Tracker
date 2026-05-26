"""Unit tests for backend/sources/gmail.py — all Gmail API calls are mocked."""
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call

from backend.sources.base import EmailSource
from backend.models.email_metadata import EmailMetadata


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_message(msg_id: str, from_val: str, subject: str, date: str) -> dict:
    """Build a mock Gmail messages.get() response (metadata format only)."""
    return {
        "id": msg_id,
        "payload": {
            "headers": [
                {"name": "From", "value": from_val},
                {"name": "Subject", "value": subject},
                {"name": "Date", "value": date},
            ]
        },
    }


def _make_source(service_mock, account_id: str = "user@example.com") -> "GmailEmailSource":
    """Build a GmailEmailSource with mocked token store and Gmail service."""
    from backend.sources.gmail import GmailEmailSource
    with (
        patch("backend.auth.token_store.load_token", return_value="fake-refresh-token"),
        patch("backend.auth.oauth.build_gmail_service", return_value=service_mock),
    ):
        src = GmailEmailSource(account_id=account_id)
    return src


def _make_service(messages_by_query: dict[str, list[str]], message_data: dict[str, dict]) -> MagicMock:
    """
    Build a mock Gmail service.

    messages_by_query: {query_fragment: [list of message IDs for that query]}
    message_data: {message_id: <messages.get() response dict>}
    """
    service = MagicMock()

    def _list_execute(**kwargs):
        q = kwargs.get("q", "")
        # Match pass query by checking for a keyword unique to each pass
        for fragment, ids in messages_by_query.items():
            if fragment in q:
                return {"messages": [{"id": i} for i in ids]}
        return {"messages": []}

    list_mock = MagicMock()
    list_mock.execute.side_effect = lambda: _list_execute(
        **list_mock._call_kwargs
    )

    # messages().list() — capture kwargs on each call
    call_log: list[dict] = []

    def _list(**kwargs):
        call_log.append(kwargs)
        m = MagicMock()
        q = kwargs.get("q", "")
        ids = []
        for fragment, msg_ids in messages_by_query.items():
            if fragment in q:
                ids = msg_ids
                break
        m.execute.return_value = {"messages": [{"id": i} for i in ids]}
        return m

    def _get(**kwargs):
        msg_id = kwargs.get("id", "")
        m = MagicMock()
        m.execute.return_value = message_data.get(msg_id, {"id": msg_id, "payload": {"headers": []}})
        return m

    service.users.return_value.messages.return_value.list.side_effect = _list
    service.users.return_value.messages.return_value.get.side_effect = _get
    service.users.return_value.getProfile.return_value.execute.return_value = {
        "emailAddress": "user@example.com"
    }

    return service


# ── Interface conformance ──────────────────────────────────────────────────────

def test_gmail_source_is_email_source_subclass():
    from backend.sources.gmail import GmailEmailSource
    assert issubclass(GmailEmailSource, EmailSource)


# ── format=metadata enforcement ────────────────────────────────────────────────

def test_fetch_always_uses_format_metadata():
    """Every messages.get() call must use format='metadata'."""
    msg_data = {
        "msg1": _make_message("msg1", "noreply@netflix.com", "Netflix receipt $15.49",
                               "Mon, 01 Jan 2024 10:00:00 +0000"),
    }
    service = _make_service({"netflix.com": ["msg1"]}, msg_data)
    src = _make_source(service)
    src.fetch(mode="quick")

    get_calls = service.users.return_value.messages.return_value.get.call_args_list
    for c in get_calls:
        kwargs = c.kwargs if c.kwargs else (c[1] if len(c) > 1 else {})
        assert kwargs.get("format") == "metadata", (
            f"messages.get() called with format={kwargs.get('format')!r} — must be 'metadata'"
        )


def test_fetch_only_requests_three_metadata_headers():
    """Only From, Subject, Date headers must be requested."""
    msg_data = {
        "msg1": _make_message("msg1", "noreply@spotify.com", "Spotify receipt $9.99",
                               "Mon, 01 Jan 2024 10:00:00 +0000"),
    }
    service = _make_service({"spotify.com": ["msg1"]}, msg_data)
    src = _make_source(service)
    src.fetch(mode="quick")

    get_calls = service.users.return_value.messages.return_value.get.call_args_list
    for c in get_calls:
        kwargs = c.kwargs if c.kwargs else (c[1] if len(c) > 1 else {})
        headers = kwargs.get("metadataHeaders", [])
        assert sorted(headers) == sorted(["From", "Subject", "Date"]), (
            f"Only From/Subject/Date must be requested, got: {headers}"
        )


# ── Deduplication ──────────────────────────────────────────────────────────────

def test_dedup_same_id_from_multiple_passes():
    """A message ID appearing in both pass 1 and pass 2 must be fetched only once."""
    msg_data = {
        "shared": _make_message("shared", "noreply@netflix.com", "Netflix receipt",
                                "Mon, 01 Jan 2024 10:00:00 +0000"),
    }
    # Same ID returned by both passes
    service = _make_service(
        {"netflix.com": ["shared"], "receipt": ["shared"]},
        msg_data,
    )
    src = _make_source(service)
    result = src.fetch(mode="quick")

    # Only one EmailMetadata object despite two passes returning the same ID
    assert len(result) == 1
    assert result[0].source_message_id == "shared"

    get_calls = service.users.return_value.messages.return_value.get.call_args_list
    assert len(get_calls) == 1, (
        f"messages.get() called {len(get_calls)} times for a single unique ID — must be 1"
    )


# ── EmailMetadata field population ────────────────────────────────────────────

def test_email_metadata_fields_populated():
    """All 8 required EmailMetadata fields must be populated."""
    msg_data = {
        "m1": _make_message(
            "m1",
            "Netflix <noreply@netflix.com>",
            "Your Netflix receipt - $15.49",
            "Mon, 01 Jan 2024 10:00:00 +0000",
        ),
    }
    service = _make_service({"netflix.com": ["m1"]}, msg_data)
    src = _make_source(service)
    results = src.fetch(mode="quick")

    assert len(results) == 1
    em = results[0]
    assert em.source_message_id == "m1"
    assert em.source_provider == "GMAIL"
    assert em.source_account_id == "user@example.com"
    assert em.source_account_email == "user@example.com"
    assert "netflix.com" in em.sender_address
    assert em.subject == "Your Netflix receipt - $15.49"
    assert isinstance(em.email_date, datetime)
    assert em.email_date.tzinfo is not None, "email_date must be timezone-aware"


# ── Mode / pass selection ──────────────────────────────────────────────────────

def test_quick_mode_uses_only_two_passes():
    """quick mode: only pass 1 (from:) and pass 2 (subject:receipt...) queries run."""
    service = _make_service({}, {})
    src = _make_source(service)
    src.fetch(mode="quick")

    list_calls = service.users.return_value.messages.return_value.list.call_args_list
    queries = [c.kwargs.get("q", "") for c in list_calls]
    assert len(queries) == 2, f"quick mode must make exactly 2 list calls, got {len(queries)}"
    assert any("from:" in q for q in queries), "Pass 1 (from:) must be included in quick mode"
    assert any("receipt" in q for q in queries), "Pass 2 (receipt) must be included in quick mode"


def test_deep_mode_uses_four_passes():
    """deep mode: passes 1–4."""
    service = _make_service({}, {})
    src = _make_source(service)
    src.fetch(mode="deep")

    list_calls = service.users.return_value.messages.return_value.list.call_args_list
    assert len(list_calls) == 4, f"deep mode must make 4 list calls, got {len(list_calls)}"


def test_forensic_mode_uses_six_passes():
    """forensic mode: passes 1–6."""
    service = _make_service({}, {})
    src = _make_source(service)
    src.fetch(mode="forensic")

    list_calls = service.users.return_value.messages.return_value.list.call_args_list
    assert len(list_calls) == 6, f"forensic mode must make 6 list calls, got {len(list_calls)}"


# ── Date range query construction ─────────────────────────────────────────────

def test_date_from_appended_to_queries():
    """date_from should produce after:YYYY/MM/DD in the Gmail query."""
    service = _make_service({}, {})
    src = _make_source(service)
    src.fetch(
        mode="quick",
        date_from=datetime(2024, 3, 1, tzinfo=timezone.utc),
    )

    list_calls = service.users.return_value.messages.return_value.list.call_args_list
    for c in list_calls:
        q = c.kwargs.get("q", "")
        assert "after:2024/03/01" in q, (
            f"Query must contain 'after:2024/03/01' when date_from is set, got: {q!r}"
        )


def test_date_to_appended_to_queries():
    """date_to should produce before:YYYY/MM/DD in the Gmail query."""
    service = _make_service({}, {})
    src = _make_source(service)
    src.fetch(
        mode="quick",
        date_to=datetime(2024, 12, 31, tzinfo=timezone.utc),
    )

    list_calls = service.users.return_value.messages.return_value.list.call_args_list
    for c in list_calls:
        q = c.kwargs.get("q", "")
        assert "before:2024/12/31" in q


# ── Unknown mode falls back gracefully ────────────────────────────────────────

def test_unknown_mode_falls_back_to_deep():
    service = _make_service({}, {})
    src = _make_source(service)
    src.fetch(mode="unknown_mode_xyz")  # must not raise
    list_calls = service.users.return_value.messages.return_value.list.call_args_list
    assert len(list_calls) == 4, "Unknown mode must fall back to deep (4 passes)"
