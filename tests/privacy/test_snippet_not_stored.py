"""
Asserts that Gmail snippet text is never persisted to the database,
never passed to the DB insert function, and not exposed in validation reports.

The snippet field on EmailMetadata is processing-time only: it may be read from
the Gmail API response and used by parsers, but it must be discarded before any
database write and must never appear in log output or report text.
"""
import ast
import re
import pytest
from pathlib import Path


def test_snippet_not_in_db_schema():
    """email_records and subscriptions tables must not have a snippet or body column."""
    schema_path = Path("backend/db/migrations/001_initial_schema.sql")
    if not schema_path.exists():
        pytest.skip("Schema file not found")
    schema = schema_path.read_text(encoding="utf-8").lower()
    assert "snippet" not in schema, (
        "DB schema must not store snippet text — snippet is processing-time only"
    )
    assert "body_text" not in schema, (
        "DB schema must not store body text"
    )


def test_snippet_not_passed_to_insert_email_record():
    """insert_email_record() must not accept a snippet parameter."""
    setup_path = Path("backend/db/setup.py")
    if not setup_path.exists():
        pytest.skip("backend/db/setup.py not found")
    source = setup_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "insert_email_record":
            param_names = [a.arg for a in node.args.args]
            assert "snippet" not in param_names, (
                "insert_email_record must not accept a 'snippet' parameter — "
                "snippet is processing-time only, never stored"
            )
            return
    # If the function was not found, skip rather than fail (might not be implemented yet)
    pytest.skip("insert_email_record function not found in setup.py")


def test_snippet_not_in_email_metadata_db_fields():
    """EmailMetadata.snippet must not be forwarded to any DB call in detector.py."""
    detector_path = Path("backend/detector/detector.py")
    if not detector_path.exists():
        pytest.skip("detector.py not found")
    source = detector_path.read_text(encoding="utf-8")
    # Check that no call to insert_email_record passes a snippet= keyword argument
    assert "snippet=" not in source, (
        "detector.py must not pass snippet= to any DB function — "
        "snippet is processing-time only, never stored"
    )


def test_snippet_value_not_logged_in_gmail_source():
    """gmail.py must not log the raw snippet value as a format argument."""
    gmail_path = Path("backend/sources/gmail.py")
    if not gmail_path.exists():
        pytest.skip("gmail.py not found (Phase 2 module)")
    source = gmail_path.read_text(encoding="utf-8")
    # Reject patterns like: logger.info("...", snippet) or logger.debug("%s", snippet)
    # Allow: variable assignment (snippet = ...) and passing to EmailMetadata constructor
    log_with_snippet = re.compile(
        r"logger\.\w+\([^)]*,\s*snippet\s*[,)]",
        re.DOTALL,
    )
    assert not log_with_snippet.search(source), (
        "gmail.py must not pass the snippet variable as a logger format argument — "
        "log only aggregate stats, never raw snippet content"
    )


def test_validation_report_does_not_expose_snippet():
    """validation_report.py must not query or print the snippet column."""
    report_path = Path("scripts/validation_report.py")
    if not report_path.exists():
        pytest.skip("validation_report.py not found")
    source = report_path.read_text(encoding="utf-8").lower()
    assert "snippet" not in source, (
        "validation_report.py must not reference or print snippet values — "
        "the report must show only aggregate counts and extracted fields"
    )
