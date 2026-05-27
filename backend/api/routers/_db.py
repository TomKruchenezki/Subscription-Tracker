"""Shared DB connection context manager for routers."""
import os
from contextlib import contextmanager
from backend.db.setup import get_connection, init_db


def _db_path() -> str:
    """Read DB_PATH from environment at call time (not at import time).

    Reading at call time ensures that test fixtures can set os.environ["DB_PATH"]
    after module import and have the correct DB used for each request.
    """
    return os.getenv("DB_PATH", "data/subscriptions.db")


@contextmanager
def get_conn():
    conn = get_connection(_db_path())
    try:
        yield conn
    finally:
        conn.close()


def ensure_db():
    init_db(_db_path())
