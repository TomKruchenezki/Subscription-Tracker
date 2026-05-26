"""Unit tests for backend/auth/oauth.py."""
import os
import pytest


# ── Scope assertion ────────────────────────────────────────────────────────────

def test_scopes_constant_is_readonly_only():
    from backend.auth.oauth import SCOPES
    assert SCOPES == ["https://www.googleapis.com/auth/gmail.readonly"], (
        "SCOPES must be exactly ['https://www.googleapis.com/auth/gmail.readonly']. "
        "Never add additional scopes."
    )


def test_scopes_has_exactly_one_entry():
    from backend.auth.oauth import SCOPES
    assert len(SCOPES) == 1, "SCOPES must contain exactly one scope"


# ── Auth URL generation ────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _mock_oauth_env(monkeypatch):
    """Provide minimal env vars so generate_auth_url() can run without real credentials."""
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", "http://localhost:8000/oauth/callback")


def test_generate_auth_url_returns_google_domain():
    from backend.auth.oauth import generate_auth_url
    auth_url, state = generate_auth_url()
    assert auth_url.startswith("https://accounts.google.com/"), (
        f"Auth URL must point to Google, got: {auth_url[:60]}"
    )


def test_generate_auth_url_includes_pkce_params():
    from backend.auth.oauth import generate_auth_url
    auth_url, _ = generate_auth_url()
    assert "code_challenge=" in auth_url
    assert "code_challenge_method=S256" in auth_url


def test_generate_auth_url_includes_readonly_scope():
    from backend.auth.oauth import generate_auth_url
    auth_url, _ = generate_auth_url()
    assert "gmail.readonly" in auth_url


def test_generate_auth_url_includes_state():
    from backend.auth.oauth import generate_auth_url
    auth_url, state = generate_auth_url()
    assert "state=" in auth_url
    assert state
    assert len(state) >= 10


def test_generate_auth_url_includes_offline_access():
    """access_type=offline is required to receive a refresh_token."""
    from backend.auth.oauth import generate_auth_url
    auth_url, _ = generate_auth_url()
    assert "access_type=offline" in auth_url


def test_two_calls_generate_different_states():
    from backend.auth.oauth import generate_auth_url
    _, state1 = generate_auth_url()
    _, state2 = generate_auth_url()
    assert state1 != state2, "Each OAuth flow must use a unique state value"


def test_two_calls_generate_different_pkce_challenges():
    from backend.auth.oauth import generate_auth_url
    url1, _ = generate_auth_url()
    url2, _ = generate_auth_url()
    # Extract code_challenge values
    challenge1 = [p for p in url1.split("&") if p.startswith("code_challenge=")][0]
    challenge2 = [p for p in url2.split("&") if p.startswith("code_challenge=")][0]
    assert challenge1 != challenge2, "Each OAuth flow must use a unique PKCE code_challenge"


# ── State expiry ───────────────────────────────────────────────────────────────

def test_exchange_code_raises_on_unknown_state():
    from backend.auth.oauth import exchange_code
    with pytest.raises(ValueError, match="Unknown or expired"):
        exchange_code(code="fake-code", state="nonexistent-state-value")


# ── No file writes ─────────────────────────────────────────────────────────────

def test_oauth_module_does_not_write_files(tmp_path, monkeypatch):
    """oauth.py must never write tokens to disk — that's token_store.py's job."""
    monkeypatch.chdir(tmp_path)
    from backend.auth.oauth import generate_auth_url
    generate_auth_url()
    written = list(tmp_path.iterdir())
    assert written == [], f"oauth.py must not write any files, but wrote: {written}"
