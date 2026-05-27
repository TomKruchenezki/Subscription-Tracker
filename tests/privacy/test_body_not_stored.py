"""
Asserts that Gmail body text is never persisted to the database,
never passed to the DB insert function, and not exposed in validation reports.

The body_text field on EmailMetadata is processing-time only: it may be fetched
from the Gmail API response in forensic mode and used by parsers, but it must be
discarded before any database write and must never appear in log output or report text.
"""
import ast
import re
import pytest
from pathlib import Path


def test_body_text_not_in_db_schema():
    """email_records and subscriptions tables must not have a body_text or body_html column."""
    schema_path = Path("backend/db/migrations/001_initial_schema.sql")
    if not schema_path.exists():
        pytest.skip("Schema file not found")
    schema = schema_path.read_text(encoding="utf-8").lower()
    assert "body_text" not in schema, (
        "DB schema must not store body_text — body is processing-time only, never stored"
    )
    assert "body_html" not in schema, (
        "DB schema must not store body_html — body is processing-time only, never stored"
    )


def test_body_text_not_passed_to_insert_email_record():
    """insert_email_record() must not accept a body_text parameter."""
    setup_path = Path("backend/db/setup.py")
    if not setup_path.exists():
        pytest.skip("backend/db/setup.py not found")
    source = setup_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "insert_email_record":
            param_names = [a.arg for a in node.args.args]
            assert "body_text" not in param_names, (
                "insert_email_record must not accept a 'body_text' parameter — "
                "body_text is processing-time only, never stored"
            )
            return
    pytest.skip("insert_email_record function not found in setup.py")


def test_body_text_not_passed_to_db_in_detector():
    """detector.py must not pass body_text= to any DB function."""
    detector_path = Path("backend/detector/detector.py")
    if not detector_path.exists():
        pytest.skip("detector.py not found")
    source = detector_path.read_text(encoding="utf-8")
    assert "body_text=" not in source, (
        "detector.py must not pass body_text= to any DB function — "
        "body_text is processing-time only, never stored"
    )


def test_body_text_value_not_logged_in_gmail_source():
    """gmail.py must not log the raw body_text value as a format argument."""
    gmail_path = Path("backend/sources/gmail.py")
    if not gmail_path.exists():
        pytest.skip("gmail.py not found (Phase 2 module)")
    source = gmail_path.read_text(encoding="utf-8")
    # Reject patterns like: logger.info("...", body_text) or logger.debug("%s", body_text)
    # Allow: variable assignment (body_text = ...) and passing to EmailMetadata constructor
    log_with_body = re.compile(
        r"logger\.\w+\([^)]*,\s*body_text\s*[,)]",
        re.DOTALL,
    )
    assert not log_with_body.search(source), (
        "gmail.py must not pass the body_text variable as a logger format argument — "
        "log only aggregate stats, never raw body content"
    )


def test_validation_report_does_not_expose_body_text():
    """validation_report.py must not query or print the body_text column."""
    report_path = Path("scripts/validation_report.py")
    if not report_path.exists():
        pytest.skip("validation_report.py not found")
    source = report_path.read_text(encoding="utf-8").lower()
    assert "body_text" not in source, (
        "validation_report.py must not reference or print body_text values — "
        "the report must show only aggregate counts and extracted fields"
    )
