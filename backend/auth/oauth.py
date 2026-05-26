"""
OAuth 2.0 Authorization Code + PKCE flow for Gmail (local dev).

Privacy constraint (enforced by tests/privacy/test_gmail_scope.py):
    SCOPES must be exactly ["https://www.googleapis.com/auth/gmail.readonly"].
    This list must never be extended.

Flow:
    1. generate_auth_url()   → returns (auth_url, state); stores PKCE verifier in memory
    2. Browser hits Google → user consents → Google redirects to /oauth/callback?code=&state=
    3. exchange_code(code, state) → returns google.oauth2.credentials.Credentials
    4. Caller saves credentials.refresh_token via token_store; access token is NOT persisted
"""
import base64
import hashlib
import logging
import os
import secrets
import time
from typing import TYPE_CHECKING
from urllib.parse import urlencode

if TYPE_CHECKING:
    from google.oauth2.credentials import Credentials

logger = logging.getLogger(__name__)

# ── Scope declaration (non-negotiable) ────────────────────────────────────────
# test_gmail_scope.py asserts this exact value. Never add additional scopes.
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# ── Google OAuth endpoints ─────────────────────────────────────────────────────
_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

# ── In-memory PKCE state store ────────────────────────────────────────────────
# Maps state → (code_verifier, created_at_unix). Single-user local app; cleared on restart.
_PENDING_FLOWS: dict[str, tuple[str, float]] = {}
_FLOW_TTL_SECONDS = 600  # 10 minutes


def _clean_expired_flows() -> None:
    now = time.time()
    expired = [s for s, (_, t) in _PENDING_FLOWS.items() if now - t > _FLOW_TTL_SECONDS]
    for s in expired:
        del _PENDING_FLOWS[s]


def generate_auth_url() -> tuple[str, str]:
    """Generate a Google OAuth authorization URL with PKCE.

    Returns:
        (auth_url, state) — redirect the browser to auth_url; state is for CSRF validation.
    """
    _clean_expired_flows()

    # PKCE: generate code_verifier and derive code_challenge (S256)
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b"=").decode()

    state = secrets.token_urlsafe(32)
    _PENDING_FLOWS[state] = (code_verifier, time.time())

    client_id = os.environ["GOOGLE_OAUTH_CLIENT_ID"]
    redirect_uri = os.environ["GOOGLE_OAUTH_REDIRECT_URI"]

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPES[0],
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent",  # force refresh_token to be returned every time
        "state": state,
    }
    auth_url = f"{_GOOGLE_AUTH_URL}?{urlencode(params)}"
    logger.info("Generated OAuth auth URL (state=%s)", state[:8] + "…")
    return auth_url, state


def exchange_code(code: str, state: str) -> "Credentials":
    """Exchange an authorization code for credentials using PKCE.

    Args:
        code: The authorization code from Google's callback.
        state: The state parameter from the callback (CSRF validation).

    Returns:
        google.oauth2.credentials.Credentials with refresh_token populated.

    Raises:
        ValueError: If state is unknown, expired, or code exchange fails.
    """
    from google.oauth2.credentials import Credentials
    import urllib.request
    import json

    _clean_expired_flows()

    if state not in _PENDING_FLOWS:
        raise ValueError(f"Unknown or expired OAuth state: {state[:8]}…")

    code_verifier, _ = _PENDING_FLOWS.pop(state)

    client_id = os.environ["GOOGLE_OAUTH_CLIENT_ID"]
    client_secret = os.environ["GOOGLE_OAUTH_CLIENT_SECRET"]
    redirect_uri = os.environ["GOOGLE_OAUTH_REDIRECT_URI"]

    payload = urlencode({
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": code_verifier,
    }).encode()

    req = urllib.request.Request(
        _GOOGLE_TOKEN_URL,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            token_data = json.loads(resp.read())
    except Exception as exc:
        raise ValueError(f"Token exchange failed: {exc}") from exc

    if "refresh_token" not in token_data:
        raise ValueError(
            "Google did not return a refresh_token. "
            "Ensure prompt=consent is set and the account hasn't been previously authorized."
        )

    creds = Credentials(
        token=token_data.get("access_token"),
        refresh_token=token_data["refresh_token"],
        token_uri=_GOOGLE_TOKEN_URL,
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )
    logger.info("OAuth token exchange successful — refresh_token obtained")
    return creds


def build_gmail_service(refresh_token: str):
    """Build an authorized Gmail API service from a stored refresh token.

    The access token is obtained automatically by the Google client library
    and is never persisted to disk.

    Args:
        refresh_token: The stored (decrypted) refresh token string.

    Returns:
        A googleapiclient Resource for the Gmail API v1.
    """
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    client_id = os.environ["GOOGLE_OAUTH_CLIENT_ID"]
    client_secret = os.environ["GOOGLE_OAUTH_CLIENT_SECRET"]

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=_GOOGLE_TOKEN_URL,
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )
    # Refresh now to get a fresh access_token (never stored)
    creds.refresh(Request())
    return build("gmail", "v1", credentials=creds)
