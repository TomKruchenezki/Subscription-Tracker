"""
Accounts router: connected account management and Gmail OAuth flow.

Endpoints:
    GET  /api/accounts                    — list connected accounts
    GET  /api/accounts/gmail/auth-url     — start OAuth flow (returns Google auth URL)
    GET  /api/oauth/callback              — OAuth callback (Google redirects here)
    DELETE /api/accounts/{account_id}     — disconnect account

OAuth flow (browser-driven):
    1. Frontend calls GET /api/accounts/gmail/auth-url
    2. Backend returns {auth_url, state}
    3. Frontend redirects browser: window.location.href = auth_url
    4. User consents → Google redirects to GET /api/oauth/callback?code=...&state=...
    5. Backend exchanges code → stores refresh_token → creates connected_accounts record
    6. Backend redirects browser → http://localhost:3000/accounts?connected=true
"""
import logging
import os

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from backend.api.routers._db import get_conn, ensure_db
from backend.db.setup import (
    get_connected_accounts,
    get_connected_account,
    upsert_connected_account,
    deactivate_connected_account,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_FRONTEND_BASE = os.getenv("FRONTEND_URL", "http://localhost:3000")


# ── Response models ───────────────────────────────────────────────────────────

class ConnectedAccount(BaseModel):
    account_id: str
    source_provider: str
    account_email: str
    display_name: str | None
    is_active: bool


class AuthUrlResponse(BaseModel):
    auth_url: str
    state: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/api/accounts", response_model=list[ConnectedAccount])
def list_accounts():
    """List all connected email accounts."""
    ensure_db()
    with get_conn() as conn:
        rows = get_connected_accounts(conn)
    return [
        ConnectedAccount(
            account_id=row["account_id"],
            source_provider=row["source_provider"],
            account_email=row["account_email"],
            display_name=row["display_name"],
            is_active=bool(row["is_active"]),
        )
        for row in rows
    ]


@router.get("/api/accounts/gmail/auth-url", response_model=AuthUrlResponse)
def gmail_auth_url():
    """Generate a Gmail OAuth authorization URL.

    The frontend should redirect the browser to the returned auth_url.
    Google will redirect back to /api/oauth/callback after the user consents.
    """
    _check_oauth_env()
    from backend.auth.oauth import generate_auth_url
    auth_url, state = generate_auth_url()
    return AuthUrlResponse(auth_url=auth_url, state=state)


@router.get("/api/oauth/callback")
def oauth_callback(
    code: str = Query(..., description="Authorization code from Google"),
    state: str = Query(..., description="CSRF state token"),
    error: str | None = Query(None, description="Error from Google if user denied"),
):
    """OAuth callback endpoint — Google redirects the browser here after consent.

    On success: exchanges code for tokens, stores refresh_token, creates account record,
    then redirects browser to the frontend with ?connected=true.

    On error: redirects browser to frontend with ?oauth_error=<reason>.
    """
    ensure_db()

    if error:
        logger.warning("OAuth denied by user or Google: %s", error)
        return RedirectResponse(
            url=f"{_FRONTEND_BASE}/accounts?oauth_error={error}",
            status_code=302,
        )

    try:
        from backend.auth.oauth import exchange_code
        creds = exchange_code(code, state)
    except ValueError as exc:
        logger.error("OAuth code exchange failed: %s", exc)
        return RedirectResponse(
            url=f"{_FRONTEND_BASE}/accounts?oauth_error=exchange_failed",
            status_code=302,
        )

    try:
        # Fetch the user's Gmail profile to get their account ID and email
        from backend.auth.oauth import build_gmail_service
        service = build_gmail_service(creds.refresh_token)
        profile = service.users().getProfile(userId="me").execute()
        account_email = profile["emailAddress"]
        # Use the email as account_id (unique, human-readable, stable for personal accounts)
        account_id = account_email
    except Exception as exc:
        logger.error("Failed to fetch Gmail profile after OAuth: %s", exc)
        return RedirectResponse(
            url=f"{_FRONTEND_BASE}/accounts?oauth_error=profile_fetch_failed",
            status_code=302,
        )

    # Store the refresh token encrypted
    from backend.auth import token_store
    try:
        token_store.save_token(account_id, creds.refresh_token)
    except Exception as exc:
        logger.error("Token storage failed for %s: %s", account_id, exc)
        return RedirectResponse(
            url=f"{_FRONTEND_BASE}/accounts?oauth_error=token_storage_failed",
            status_code=302,
        )

    # Create/update connected_accounts record
    with get_conn() as conn:
        upsert_connected_account(
            conn,
            account_id=account_id,
            source_provider="GMAIL",
            account_email=account_email,
            display_name=account_email,
        )
        conn.commit()

    logger.info("Gmail account connected: %s", account_id)

    # Set env var so GmailEmailSource can find this account in the current process
    os.environ["GMAIL_ACCOUNT_ID"] = account_id

    return RedirectResponse(
        url=f"{_FRONTEND_BASE}/accounts?connected=true",
        status_code=302,
    )


@router.delete("/api/accounts/{account_id}", status_code=204)
def disconnect_account(account_id: str):
    """Disconnect an account: revoke stored token and mark account inactive."""
    ensure_db()

    with get_conn() as conn:
        row = get_connected_account(conn, account_id)
        if not row:
            raise HTTPException(status_code=404, detail="Account not found")
        deactivate_connected_account(conn, account_id)
        conn.commit()

    # Delete stored token
    from backend.auth import token_store
    try:
        token_store.delete_token(account_id)
    except Exception as exc:
        logger.warning("Token deletion failed for %s: %s — account marked inactive", account_id, exc)

    # Clear env var if it matches
    if os.getenv("GMAIL_ACCOUNT_ID") == account_id:
        os.environ.pop("GMAIL_ACCOUNT_ID", None)

    logger.info("Account disconnected: %s", account_id)
    # 204 No Content — no body returned


# ── Helpers ───────────────────────────────────────────────────────────────────

def _check_oauth_env() -> None:
    """Raise if required Gmail OAuth env vars are not set."""
    missing = [
        var for var in ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET",
                        "GOOGLE_OAUTH_REDIRECT_URI")
        if not os.getenv(var)
    ]
    if missing:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Gmail OAuth not configured. Missing env vars: {', '.join(missing)}. "
                "See .env.example for setup instructions."
            ),
        )
