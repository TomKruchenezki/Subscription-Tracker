"""Unit tests for backend/auth/token_store.py — file backend (no OS keyring dependency)."""
import os
import pytest


@pytest.fixture(autouse=True)
def _use_file_backend(monkeypatch, tmp_path):
    """Force file backend and set a test encryption key for all token_store tests."""
    monkeypatch.setenv("TOKEN_STORAGE_BACKEND", "file")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "test-encryption-key-that-is-at-least-32-chars!")
    # Point the token file at a temp directory so tests don't touch the real auth/ dir
    import backend.auth.token_store as ts
    monkeypatch.setattr(ts, "_TOKEN_FILE", tmp_path / "token.json")
    yield


def test_save_and_load_roundtrip():
    from backend.auth import token_store
    token_store.save_token("user@example.com", "my-refresh-token-value")
    loaded = token_store.load_token("user@example.com")
    assert loaded == "my-refresh-token-value"


def test_load_missing_account_returns_none():
    from backend.auth import token_store
    result = token_store.load_token("nobody@example.com")
    assert result is None


def test_delete_removes_token():
    from backend.auth import token_store
    token_store.save_token("user@example.com", "to-be-deleted")
    token_store.delete_token("user@example.com")
    assert token_store.load_token("user@example.com") is None


def test_delete_nonexistent_does_not_raise():
    from backend.auth import token_store
    # Should not raise even when account was never saved
    token_store.delete_token("ghost@example.com")


def test_multiple_accounts_isolated(tmp_path, monkeypatch):
    """Saving two accounts should not overwrite each other."""
    import backend.auth.token_store as ts
    monkeypatch.setattr(ts, "_TOKEN_FILE", tmp_path / "multi.json")
    ts.save_token("alice@example.com", "alice-token")
    ts.save_token("bob@example.com", "bob-token")
    assert ts.load_token("alice@example.com") == "alice-token"
    assert ts.load_token("bob@example.com") == "bob-token"


def test_saved_token_is_not_plaintext(tmp_path, monkeypatch):
    """The token file must not contain the refresh token in plaintext."""
    import backend.auth.token_store as ts
    token_file = tmp_path / "encrypted.json"
    monkeypatch.setattr(ts, "_TOKEN_FILE", token_file)

    secret = "super-secret-refresh-token-12345"
    ts.save_token("user@example.com", secret)

    raw_bytes = token_file.read_bytes()
    assert secret.encode() not in raw_bytes, (
        "Refresh token must not appear in plaintext in the token file"
    )
    # Also verify the file doesn't contain obvious OAuth field names
    for field in (b"refresh_token", b"access_token", b"client_id", b"client_secret"):
        assert field not in raw_bytes, (
            f"Token file must not contain plaintext field {field!r}"
        )


def test_short_encryption_key_raises():
    """A key shorter than 32 chars must raise RuntimeError."""
    from backend.auth import token_store
    import os
    original = os.environ.get("TOKEN_ENCRYPTION_KEY")
    os.environ["TOKEN_ENCRYPTION_KEY"] = "tooshort"
    try:
        with pytest.raises(RuntimeError, match="at least 32"):
            token_store._derive_fernet_key()
    finally:
        if original is not None:
            os.environ["TOKEN_ENCRYPTION_KEY"] = original
        else:
            del os.environ["TOKEN_ENCRYPTION_KEY"]
