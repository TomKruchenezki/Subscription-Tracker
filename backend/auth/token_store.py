"""
Encrypted token storage for OAuth refresh tokens.

Only the refresh token is persisted. The access token is obtained at runtime
by refreshing credentials and is never written to disk.

Backends (controlled by TOKEN_STORAGE_BACKEND env var):
    keyring  (default/recommended) — OS credential store via the `keyring` library.
             Tokens are protected by the OS login/keychain, no key management needed.
    file     — AES-128 (Fernet) encrypted JSON file at backend/auth/token.json.
             Requires TOKEN_ENCRYPTION_KEY env var (≥32 chars).

Privacy constraint (enforced by tests/privacy/test_token_not_plaintext.py):
    The token file, if used, must never contain plaintext OAuth fields:
    access_token, refresh_token, token_uri, client_id, client_secret.
    The Fernet-encrypted file passes this test because the content is base64-encoded
    ciphertext, not a JSON object with recognizable field names.
"""
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_KEYRING_SERVICE = "subscription-tracker"
_TOKEN_FILE = Path(__file__).parent / "token.json"


# ── Backend selection ─────────────────────────────────────────────────────────

def _backend() -> str:
    return os.getenv("TOKEN_STORAGE_BACKEND", "keyring").lower()


# ── Public API ────────────────────────────────────────────────────────────────

def save_token(account_id: str, refresh_token: str) -> None:
    """Encrypt and persist a refresh token for the given account."""
    if _backend() == "keyring":
        _keyring_save(account_id, refresh_token)
    else:
        _file_save(account_id, refresh_token)
    logger.info("Token saved for account %s (backend=%s)", account_id, _backend())


def load_token(account_id: str) -> str | None:
    """Load and decrypt the refresh token for the given account.

    Returns None if no token is stored for this account.
    """
    if _backend() == "keyring":
        return _keyring_load(account_id)
    else:
        return _file_load(account_id)


def delete_token(account_id: str) -> None:
    """Remove the stored token for the given account."""
    if _backend() == "keyring":
        _keyring_delete(account_id)
    else:
        _file_delete(account_id)
    logger.info("Token deleted for account %s", account_id)


# ── Keyring backend ───────────────────────────────────────────────────────────

def _keyring_save(account_id: str, refresh_token: str) -> None:
    try:
        import keyring
        keyring.set_password(_KEYRING_SERVICE, account_id, refresh_token)
    except Exception as exc:
        raise RuntimeError(
            f"keyring save failed for account {account_id}: {exc}. "
            "Set TOKEN_STORAGE_BACKEND=file if keyring is not available."
        ) from exc


def _keyring_load(account_id: str) -> str | None:
    try:
        import keyring
        return keyring.get_password(_KEYRING_SERVICE, account_id)
    except Exception as exc:
        logger.warning("keyring load failed for %s: %s", account_id, exc)
        return None


def _keyring_delete(account_id: str) -> None:
    try:
        import keyring
        import keyring.errors
        keyring.delete_password(_KEYRING_SERVICE, account_id)
    except Exception:
        pass  # already missing — not an error


# ── File backend (AES-128 via Fernet) ─────────────────────────────────────────

def _derive_fernet_key() -> bytes:
    """Derive a 32-byte Fernet key from TOKEN_ENCRYPTION_KEY using PBKDF2."""
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    import base64

    raw_key = os.getenv("TOKEN_ENCRYPTION_KEY", "")
    if len(raw_key) < 32:
        raise RuntimeError(
            "TOKEN_ENCRYPTION_KEY must be at least 32 characters. "
            "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"subscription-tracker-token-salt",
        iterations=100_000,
    )
    derived = kdf.derive(raw_key.encode())
    return base64.urlsafe_b64encode(derived)


def _file_save(account_id: str, refresh_token: str) -> None:
    from cryptography.fernet import Fernet

    key = _derive_fernet_key()
    f = Fernet(key)

    # Load existing tokens (other accounts), update, re-encrypt as a whole
    existing = _file_load_all_raw()
    existing[account_id] = refresh_token
    plaintext = json.dumps(existing).encode()
    encrypted = f.encrypt(plaintext)

    _TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    _TOKEN_FILE.write_bytes(encrypted)


def _file_load(account_id: str) -> str | None:
    tokens = _file_load_all_raw()
    return tokens.get(account_id)


def _file_delete(account_id: str) -> None:
    existing = _file_load_all_raw()
    if account_id in existing:
        del existing[account_id]
        if existing:
            _file_save.__wrapped__ if hasattr(_file_save, "__wrapped__") else None
            # Re-save remaining tokens
            from cryptography.fernet import Fernet
            key = _derive_fernet_key()
            f = Fernet(key)
            plaintext = json.dumps(existing).encode()
            _TOKEN_FILE.write_bytes(f.encrypt(plaintext))
        else:
            # No accounts left — remove the file
            if _TOKEN_FILE.exists():
                _TOKEN_FILE.unlink()


def _file_load_all_raw() -> dict[str, str]:
    """Load and decrypt all tokens from file. Returns empty dict if file missing."""
    if not _TOKEN_FILE.exists():
        return {}
    try:
        from cryptography.fernet import Fernet, InvalidToken
        key = _derive_fernet_key()
        f = Fernet(key)
        decrypted = f.decrypt(_TOKEN_FILE.read_bytes())
        return json.loads(decrypted)
    except Exception as exc:
        logger.error("Failed to decrypt token file: %s", exc)
        return {}
