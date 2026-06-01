"""
Asserts that Gmail body fetching is restricted to exactly the right scope.

Two invariants are enforced at the AST level:

1. _fetch_metadata() NEVER uses format='full' — it must always use format='metadata'.
2. format='full' is ONLY permitted inside _fetch_body() — no other function may use it.
   format='raw' and format='minimal' are forbidden everywhere without exception.

Phase 2.4B added _fetch_body() for body_text_ephemeral forensic mode.
test_format_full_only_in_fetch_body() is the gate that keeps format='full' from
leaking into any other code path in gmail.py.
"""
import ast
import pytest
from pathlib import Path


def _get_gmail_tree():
    gmail_path = Path("backend/sources/gmail.py")
    if not gmail_path.exists():
        pytest.skip("backend/sources/gmail.py not found (Phase 2 module)")
    return ast.parse(gmail_path.read_text(encoding="utf-8")), gmail_path


def test_gmail_fetch_metadata_never_uses_full_format():
    """_fetch_metadata() must always use format='metadata' — never format='full'."""
    tree, _ = _get_gmail_tree()

    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef) and node.name == "_fetch_metadata"):
            continue
        # Found the function — check all format= keyword args inside it
        for subnode in ast.walk(node):
            if isinstance(subnode, ast.keyword) and subnode.arg == "format":
                value = (
                    ast.literal_eval(subnode.value)
                    if isinstance(subnode.value, ast.Constant)
                    else None
                )
                if value != "metadata":
                    pytest.fail(
                        f"_fetch_metadata() uses format='{value}'. "
                        "Only format='metadata' is permitted in _fetch_metadata() — "
                        "never fetch email bodies in the metadata path."
                    )
        return  # function found and validated

    # _fetch_metadata not yet implemented — skip rather than fail
    pytest.skip("_fetch_metadata() not found in gmail.py")


def test_format_full_only_in_fetch_body():
    """format='full' is allowed only in _fetch_body(). All other functions must not use it.
    format='raw' and format='minimal' are forbidden everywhere without exception.
    """
    tree, _ = _get_gmail_tree()

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        func_name = node.name
        if func_name == "_fetch_body":
            continue  # format="full" is permitted here — this is the sole exception

        for subnode in ast.walk(node):
            if isinstance(subnode, ast.keyword) and subnode.arg == "format":
                value = (
                    ast.literal_eval(subnode.value)
                    if isinstance(subnode.value, ast.Constant)
                    else None
                )
                if value in {"full", "raw", "minimal"}:
                    pytest.fail(
                        f"format='{value}' found in {func_name}(). "
                        "format='full' is only permitted in _fetch_body(); "
                        "format='raw' and format='minimal' are never permitted."
                    )


def test_attachments_get_only_in_fetch_attachment_bytes():
    """messages.attachments().get downloads attachment content (Phase 3.7).

    It is permitted ONLY inside _fetch_attachment_bytes(), which uses the bytes
    transiently and never stores them. Any other function referencing .attachments()
    is a privacy violation.
    """
    tree, _ = _get_gmail_tree()

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name == "_fetch_attachment_bytes":
            continue  # the sole permitted location
        for subnode in ast.walk(node):
            # Match the Gmail API CALL `...attachments()`, not attribute reads like
            # `metadata.attachments` (the ephemeral EmailMetadata field).
            if (
                isinstance(subnode, ast.Call)
                and isinstance(subnode.func, ast.Attribute)
                and subnode.func.attr == "attachments"
            ):
                pytest.fail(
                    f".attachments() called in {node.name}(). "
                    "Attachment content download is permitted only in "
                    "_fetch_attachment_bytes() — it must stay isolated and transient."
                )
