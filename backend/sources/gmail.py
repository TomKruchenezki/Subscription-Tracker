"""
Gmail email source adapter.

Implements the EmailSource interface using the Gmail API v1.
Returns list[EmailMetadata] — identical shape to MockEmailSource.
The detection, parsing, and database layers never interact with raw Gmail responses.

Privacy constraints (enforced by tests/privacy/):
    - _fetch_metadata() uses format="metadata" only — NEVER full/raw/minimal
    - Only headers ["From", "Subject", "Date"] are requested via metadataHeaders
    - The "snippet" field from the API response is read for parser use but NEVER stored
    - _fetch_body() uses format="full" ONLY for body_text_ephemeral forensic mode;
      raw body is processed in memory and discarded — NEVER stored, logged, or returned
    - No attachment fetching (messages.attachments not called)
    - No thread fetching (threads.get not called)
    - Access token is never persisted; only the refresh token is stored (in token_store)
"""
import logging
from datetime import datetime, timezone
from email.utils import parseaddr, parsedate_to_datetime

from backend.models.email_metadata import EmailMetadata
from backend.sources.base import EmailSource
from backend.utils.retry import with_retry

logger = logging.getLogger(__name__)

# ── Multi-pass query definitions ──────────────────────────────────────────────
# Each pass is a separate messages.list call. Results are deduplicated by message ID
# before metadata is fetched — an email matching multiple passes is fetched once.

_PASSES: dict[int, str] = {
    1: (
        "from:(netflix.com OR spotify.com OR github.com OR notion.so OR figma.com "
        "OR slack.com OR dropbox.com OR adobe.com OR zoom.us OR atlassian.com "
        "OR openai.com OR anthropic.com OR apple.com OR google.com OR youtube.com "
        "OR hulu.com OR disneyplus.com OR max.com OR primevideo.com OR bitwarden.com "
        "OR 1password.com OR linear.app OR vercel.com OR digitalocean.com "
        "OR substack.com OR nytimes.com OR canva.com OR wix.com OR udemy.com "
        "OR coursera.org OR linkedin.com OR grammarly.com OR nordvpn.com "
        "OR monday.com OR airtable.com OR paypal.com)"
    ),
    2: (
        'subject:(receipt OR invoice OR "payment confirmation" OR "billing statement" '
        'OR charged OR "we charged")'
    ),
    3: (
        'subject:(subscription OR renewal OR "membership renewed" OR "auto-renew" '
        'OR "your plan" OR "your membership")'
    ),
    4: (
        'subject:(trial OR cancellation OR cancelled OR refund OR "failed payment" '
        'OR "payment failed" OR "price change" OR "payment declined")'
    ),
    5: (
        'subject:(payment OR billing OR "your account") '
        '-subject:("% off" OR sale OR promo OR coupon)'
    ),
    6: (
        'subject:(charged OR "order confirmation" OR transaction OR "thank you for") '
        "-from:(amazon.com OR ebay.com OR etsy.com OR shopify.com "
        "OR fedex.com OR ups.com OR usps.com)"
    ),
}

_MODE_PASSES: dict[str, list[int]] = {
    "quick":    [1, 2],
    "deep":     [1, 2, 3, 4],
    "forensic": [1, 2, 3, 4, 5, 6],
}

_MODE_MAX_MESSAGES: dict[str, int | None] = {
    "quick":    500,
    "deep":     2000,
    "forensic": None,   # unlimited — paginate until exhausted
}

_PAGE_SIZE = 100        # Gmail API max per page
_METADATA_HEADERS = ["From", "Subject", "Date"]


class GmailEmailSource(EmailSource):
    """Gmail-backed email source. Authenticates using stored refresh token."""

    def __init__(self, account_id: str | None = None):
        """
        Args:
            account_id: The connected_accounts.account_id for the Gmail account.
                        Defaults to the first active GMAIL account in the DB.
        """
        from backend.auth import token_store
        from backend.auth.oauth import build_gmail_service
        import os

        self._account_id = account_id or os.getenv("GMAIL_ACCOUNT_ID", "")
        if not self._account_id:
            raise RuntimeError(
                "No Gmail account_id configured. "
                "Connect a Gmail account via /api/accounts/gmail/auth-url first."
            )

        refresh_token = token_store.load_token(self._account_id)
        if not refresh_token:
            raise RuntimeError(
                f"No stored token for account {self._account_id}. "
                "Re-connect Gmail via /api/accounts/gmail/auth-url."
            )

        self._service = build_gmail_service(refresh_token)
        logger.info("GmailEmailSource initialized for account %s", self._account_id)

    def fetch(
        self,
        *,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        mode: str = "deep",
        content_access_level: str = "metadata_plus_snippet",
    ) -> list[EmailMetadata]:
        """Fetch subscription-relevant emails from Gmail using multi-pass queries.

        Args:
            date_from:            Only include emails on or after this date.
            date_to:              Only include emails on or before this date.
            mode:                 "quick" (passes 1-2), "deep" (1-4), "forensic" (1-6).
            content_access_level: "metadata_plus_snippet" (default) or
                                  "body_text_ephemeral" (forensic only — reads body
                                  in memory for parsing, discards immediately).

        Returns:
            Deduplicated list of EmailMetadata records.
        """
        if mode not in _MODE_PASSES:
            logger.warning("Unknown scan mode %r — defaulting to 'deep'", mode)
            mode = "deep"

        passes = _MODE_PASSES[mode]
        max_messages = _MODE_MAX_MESSAGES[mode]
        fetch_body = content_access_level == "body_text_ephemeral"

        logger.info(
            "Starting Gmail scan: mode=%s, passes=%s, max=%s, access=%s",
            mode, passes, max_messages or "unlimited", content_access_level,
        )

        # Step 1: Collect all message IDs across passes (deduplicated)
        seen_ids: set[str] = set()
        ordered_ids: list[str] = []

        for pass_num in passes:
            query = _build_query(_PASSES[pass_num], date_from, date_to)
            logger.info("Pass %d query: %s", pass_num, query[:120])

            ids = self._list_message_ids(query, max_messages, seen_ids)
            for msg_id in ids:
                seen_ids.add(msg_id)
                ordered_ids.append(msg_id)

            if max_messages and len(ordered_ids) >= max_messages:
                logger.info("Message cap %d reached at pass %d", max_messages, pass_num)
                break

        logger.info("Collected %d unique message IDs across %d passes", len(ordered_ids), len(passes))

        # Step 2: Fetch metadata (and optionally body) for each unique ID
        emails: list[EmailMetadata] = []
        for msg_id in ordered_ids:
            metadata = self._fetch_metadata(msg_id)
            if metadata is None:
                continue
            if fetch_body:
                # PRIVACY: body_text is fetched ephemerally — processed in memory,
                # never stored in the database, never logged, never returned by API.
                metadata.body_text = self._fetch_body(msg_id)
            emails.append(metadata)

        logger.info("Fetched metadata for %d emails", len(emails))
        return emails

    @with_retry()
    def _list_message_ids(
        self,
        query: str,
        max_messages: int | None,
        already_seen: set[str],
    ) -> list[str]:
        """Paginate through messages.list results for a single query pass."""
        ids: list[str] = []
        page_token: str | None = None

        while True:
            kwargs: dict = {
                "userId": "me",
                "q": query,
                "maxResults": _PAGE_SIZE,
            }
            if page_token:
                kwargs["pageToken"] = page_token

            result = self._service.users().messages().list(**kwargs).execute()
            messages = result.get("messages", [])

            for msg in messages:
                msg_id = msg["id"]
                if msg_id not in already_seen:
                    ids.append(msg_id)
                    if max_messages and (len(already_seen) + len(ids)) >= max_messages:
                        return ids

            page_token = result.get("nextPageToken")
            if not page_token:
                break

        return ids

    @with_retry()
    def _fetch_metadata(self, message_id: str) -> EmailMetadata | None:
        """Fetch header metadata for a single Gmail message.

        PRIVACY: format="metadata" is the ONLY valid value here.
        test_no_body_fetch.py will fail if format=full, format=raw, or format=minimal
        appear anywhere in this file.
        """
        try:
            msg = self._service.users().messages().get(
                userId="me",
                id=message_id,
                format="metadata",
                metadataHeaders=_METADATA_HEADERS,
            ).execute()
        except Exception as exc:
            logger.warning("Failed to fetch message %s: %s — skipping", message_id, exc)
            return None

        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}

        from_raw = headers.get("From", "")
        sender_name, sender_address = parseaddr(from_raw)
        if not sender_address:
            logger.debug("Message %s has no From address — skipping", message_id)
            return None

        subject = headers.get("Subject", "(no subject)")

        date_raw = headers.get("Date", "")
        try:
            email_date = parsedate_to_datetime(date_raw)
            if email_date.tzinfo is None:
                email_date = email_date.replace(tzinfo=timezone.utc)
        except Exception:
            logger.debug("Message %s has unparseable Date %r — using now", message_id, date_raw)
            email_date = datetime.now(timezone.utc)

        # Snippet: short body preview included in format="metadata" responses at no extra cost.
        # Used only for parser extraction — NEVER stored in the database or logged.
        snippet = msg.get("snippet") or None

        # Get the account's email address for source_account_email
        # (cached on first call to avoid repeated API calls)
        account_email = self._get_account_email()

        return EmailMetadata(
            source_message_id=message_id,
            source_provider="GMAIL",
            source_account_id=self._account_id,
            source_account_email=account_email,
            sender_address=sender_address.lower(),
            sender_name=sender_name or None,
            subject=subject,
            email_date=email_date,
            snippet=snippet,
        )

    @with_retry()
    def _fetch_body(self, message_id: str) -> str | None:
        """Fetch full message body for ephemeral parsing (forensic mode only).

        PRIVACY: format="full" is used ONLY in this method — NEVER in _fetch_metadata().
        test_no_body_fetch.py verifies this at the AST level.

        The raw Gmail response and all body content are processed in memory and
        discarded immediately — NEVER stored, logged, or returned to callers.
        Only the extracted plain-text excerpt (max 2000 chars) is returned.
        """
        try:
            msg = self._service.users().messages().get(
                userId="me",
                id=message_id,
                format="full",
            ).execute()
            payload = msg.get("payload", {})
            return _extract_body_text(payload)
        except Exception as exc:
            logger.warning("Failed to fetch body for %s: %s — skipping body", message_id, exc)
            return None

    def _get_account_email(self) -> str:
        """Return the authenticated Gmail address. Cached after first call."""
        if not hasattr(self, "_account_email_cache"):
            try:
                profile = self._service.users().getProfile(userId="me").execute()
                self._account_email_cache: str = profile.get("emailAddress", self._account_id)
            except Exception:
                self._account_email_cache = self._account_id
        return self._account_email_cache


def _build_query(
    base_query: str,
    date_from: datetime | None,
    date_to: datetime | None,
) -> str:
    """Append Gmail date operators to a base query string."""
    parts = [base_query]
    if date_from:
        parts.append(f"after:{date_from.strftime('%Y/%m/%d')}")
    if date_to:
        parts.append(f"before:{date_to.strftime('%Y/%m/%d')}")
    return " ".join(parts)


# ── Ephemeral body-text extraction helpers ────────────────────────────────────
# These are module-level so test_no_body_fetch.py can verify that format="full"
# appears only in _fetch_body() (a GmailEmailSource method), not in these helpers.

def _extract_body_text(payload: dict, max_chars: int = 2000) -> str | None:
    """Walk MIME parts to extract plain text from a Gmail format='full' payload.

    Prefers text/plain; strips text/html as fallback. Binary parts and attachments
    are skipped. Truncated to max_chars to limit memory use and privacy surface.

    PRIVACY: Raw content is never returned — only the extracted plain-text excerpt.
    """
    mime_type = payload.get("mimeType", "")

    # Direct text/plain body
    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        return _b64_decode(data)[:max_chars] if data else None

    # text/html fallback — strip tags
    if mime_type == "text/html":
        data = payload.get("body", {}).get("data", "")
        return _strip_html(_b64_decode(data))[:max_chars] if data else None

    # Multipart: recurse, prefer text/plain over text/html
    if "parts" in payload:
        plain = None
        html_fallback = None
        for part in payload["parts"]:
            pt = part.get("mimeType", "")
            if pt == "text/plain" and plain is None:
                data = part.get("body", {}).get("data", "")
                if data:
                    plain = _b64_decode(data)[:max_chars]
            elif pt == "text/html" and html_fallback is None:
                data = part.get("body", {}).get("data", "")
                if data:
                    html_fallback = _strip_html(_b64_decode(data))[:max_chars]
            elif pt.startswith("multipart/"):
                result = _extract_body_text(part, max_chars)
                if result:
                    return result
            # Skip: image/*, application/*, text/calendar, etc.
        return plain or html_fallback

    return None


def _b64_decode(data: str) -> str:
    """URL-safe base64 decode to UTF-8 text. Returns empty string on failure."""
    import base64
    try:
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    except Exception:
        return ""


def _strip_html(raw: str) -> str:
    """Strip HTML tags using stdlib html.parser. Safe for malformed HTML."""
    import html as _html
    from html.parser import HTMLParser

    class _Strip(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self._parts: list[str] = []

        def handle_data(self, data: str) -> None:
            self._parts.append(data)

    p = _Strip()
    p.feed(_html.unescape(raw))
    return " ".join(p._parts)
