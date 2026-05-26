"""Shared DB connection context manager for routers."""
import os
from contextlib import contextmanager
from backend.db.setup import get_connection, init_db

_DB_PATH = os.getenv("DB_PATH", "data/subscriptions.db")


@contextmanager
def get_conn():
    conn = get_connection(_DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


def ensure_db():
    init_db(_DB_PATH)
