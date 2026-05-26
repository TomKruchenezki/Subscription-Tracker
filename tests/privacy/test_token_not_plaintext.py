"""
Asserts that if a token file exists on disk, it is not plaintext Google OAuth JSON.
Skips if no token file is present (expected in Phase 1 mock-only mode).
"""
import json
import os
import pytest
from pathlib import Path

PLAINTEXT_INDICATORS = {"access_token", "refresh_token", "token_uri", "client_id"}

_CANDIDATE_PATHS = [
    Path("token.json"),
    Path("data/token.json"),
    Path(".token"),
    Path("backend/auth/token.json"),
]


def test_token_file_not_plaintext():
    token_path: Path | None = None
    for candidate in _CANDIDATE_PATHS:
        if candidate.exists():
            token_path = candidate
            break

    if token_path is None:
        pytest.skip("No token file found — expected in Phase 1 mock-only mode")

    content = token_path.read_text(encoding="utf-8", errors="replace")

    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            found = PLAINTEXT_INDICATORS & set(parsed.keys())
            assert not found, (
                f"Token file at {token_path} appears to be plaintext Google OAuth JSON "
                f"(contains keys: {found}). Tokens must be encrypted at rest."
            )
    except json.JSONDecodeError:
        # Not valid JSON — either encrypted or binary; both are acceptable
        pass
