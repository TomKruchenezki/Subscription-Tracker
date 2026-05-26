"""
Asserts that the Gmail OAuth scope is exactly gmail.readonly.
Skips in Phase 1 because backend.auth.oauth is not yet implemented.
Auto-activates in Phase 2 when backend/auth/oauth.py is created.
"""
import pytest

EXPECTED_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def test_oauth_scopes_are_readonly_only():
    try:
        from backend.auth.oauth import SCOPES
    except ImportError:
        pytest.skip("backend.auth.oauth not yet implemented (Phase 2 module)")

    assert SCOPES == EXPECTED_SCOPES, (
        f"Gmail scope must be exactly {EXPECTED_SCOPES}, got {SCOPES}. "
        "Never add write, send, delete, or compose scopes."
    )
