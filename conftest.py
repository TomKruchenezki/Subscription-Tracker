import pytest
import sqlite3
from pathlib import Path

_MIGRATIONS_DIR = Path(__file__).parent / "backend" / "db" / "migrations"
_MIGRATIONS = sorted(_MIGRATIONS_DIR.glob("*.sql"))


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
    for migration in _MIGRATIONS:
        conn.executescript(migration.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    return path
