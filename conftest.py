import pytest
import sqlite3
from pathlib import Path

_MIGRATIONS_SQL = (
    Path(__file__).parent / "backend" / "db" / "migrations" / "001_initial_schema.sql"
).read_text(encoding="utf-8")


def pytest_addoption(parser):
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="Run integration tests that require Gmail credentials",
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--integration"):
        skip_integration = pytest.mark.skip(reason="Pass --integration to run")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip_integration)


@pytest.fixture
def db_path(tmp_path):
    """In-memory SQLite database with full schema applied. Used by unit tests."""
    path = str(tmp_path / "test.db")
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_MIGRATIONS_SQL)
    conn.commit()
    conn.close()
    return path
