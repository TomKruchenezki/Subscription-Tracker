"""
Asserts that no log line emitted by backend.* during a mock pipeline run
exceeds 500 characters (a proxy for accidentally logging email bodies or subjects).
"""
import logging
import pytest

MAX_LOG_LINE_LENGTH = 500


class _CapturingHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord):
        self.records.append(record)


def test_no_oversized_log_lines_during_mock_scan():
    handler = _CapturingHandler()
    backend_logger = logging.getLogger("backend")
    backend_logger.addHandler(handler)
    original_level = backend_logger.level
    backend_logger.setLevel(logging.DEBUG)

    try:
        # Import and run the minimal detection path with mock data
        try:
            from backend.sources.mock import MockEmailSource
            from backend.detector.detector import process_email
            import sqlite3

            source = MockEmailSource()
            emails = source.fetch()
            # Run a few emails through the detector with a throw-away in-memory DB
            conn = sqlite3.connect(":memory:")
            conn.execute("PRAGMA foreign_keys = ON")
            from pathlib import Path
            sql = (Path(__file__).parent.parent.parent / "backend" / "db" /
                   "migrations" / "001_initial_schema.sql").read_text()
            conn.executescript(sql)

            for email in emails[:5]:
                try:
                    process_email(conn, email)
                except Exception:
                    pass
            conn.close()
        except ImportError:
            pytest.skip("Detection pipeline not yet implemented")

        violations = [
            r for r in handler.records
            if len(r.getMessage()) > MAX_LOG_LINE_LENGTH
        ]
        assert violations == [], (
            f"Found {len(violations)} log line(s) exceeding {MAX_LOG_LINE_LENGTH} chars. "
            "This may indicate accidental logging of email body content."
        )
    finally:
        backend_logger.removeHandler(handler)
        backend_logger.setLevel(original_level)
