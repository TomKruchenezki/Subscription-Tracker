"""
Asserts that the Gmail source always fetches with format="metadata".
Skips in Phase 1 because backend.sources.gmail is not yet implemented.
Auto-activates in Phase 2 when backend/sources/gmail.py is created.
"""
import ast
import pytest
from pathlib import Path


def test_gmail_source_uses_metadata_format():
    try:
        import backend.sources.gmail  # noqa: F401
    except ImportError:
        pytest.skip("backend.sources.gmail not yet implemented (Phase 2 module)")

    gmail_source_path = Path("backend/sources/gmail.py")
    if not gmail_source_path.exists():
        pytest.skip("backend/sources/gmail.py not found (Phase 2 module)")

    source = gmail_source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Scan for any messages().get() call that uses format != "metadata"
    forbidden_formats = {"full", "raw", "minimal"}
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "format":
            value = ast.literal_eval(node.value) if isinstance(node.value, ast.Constant) else None
            if value in forbidden_formats:
                pytest.fail(
                    f"Gmail API called with format='{value}'. "
                    "Only format='metadata' is permitted — never fetch email bodies."
                )
