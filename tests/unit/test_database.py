"""Schema and CRUD constraint tests using the in-memory db_path fixture."""
import sqlite3
import pytest
from backend.db.setup import (
    get_connection, upsert_subscription, insert_email_record,
    get_subscriptions, get_subscription_by_id, get_email_records,
)


@pytest.fixture
def conn(db_path):
    c = get_connection(db_path)
    yield c
    c.close()


def test_schema_version_exists(conn):
    row = conn.execute("SELECT COUNT(*) as cnt FROM schema_version").fetchone()
    assert row["cnt"] >= 1


def test_valid_disposition_constraint(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO email_records (record_id, source_message_id, source_provider, "
            "source_account_id, source_account_email, sender_address, "
            "subject, email_date, confidence_score, disposition) "
            "VALUES ('r1', 's1', 'MOCK', 'mock_default', 'demo@mock.local', "
            "'a@b.com', 'Test', '2025-01-01T00:00:00Z', 0.5, 'INVALID')"
        )
        conn.commit()


def test_subject_length_constraint(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO email_records (record_id, source_message_id, source_provider, "
            "source_account_id, source_account_email, sender_address, "
            "subject, email_date, confidence_score, disposition) "
            "VALUES ('r2', 's2', 'MOCK', 'mock_default', 'demo@mock.local', "
            "'a@b.com', ?, '2025-01-01T00:00:00Z', 0.5, 'DETECTED')",
            ("x" * 501,),
        )
        conn.commit()


def test_valid_confidence_constraint(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO email_records (record_id, source_message_id, source_provider, "
            "source_account_id, source_account_email, sender_address, "
            "subject, email_date, confidence_score, disposition) "
            "VALUES ('r3', 's3', 'MOCK', 'mock_default', 'demo@mock.local', "
            "'a@b.com', 'Test', '2025-01-01T00:00:00Z', 1.5, 'DETECTED')"
        )
        conn.commit()


def test_cascade_delete(conn):
    sub_id = upsert_subscription(
        conn, name="TestService", amount=9.99, currency="USD",
        billing_cycle="MONTHLY", category="SAAS", status="ACTIVE", source_provider="MOCK",
    )
    conn.commit()
    insert_email_record(
        conn, source_message_id="sm1", source_provider="MOCK",
        source_account_id="mock_default", source_account_email="demo@mock.local",
        subscription_id=sub_id, sender_address="a@b.com", sender_name=None,
        subject="Test receipt", email_date="2025-01-01T00:00:00Z",
        amount_extracted=9.99, currency_extracted="USD",
        confidence_score=0.9, disposition="DETECTED",
    )
    conn.commit()

    records_before = get_email_records(conn)
    assert len(records_before) == 1

    conn.execute("DELETE FROM subscriptions WHERE subscription_id = ?", (sub_id,))
    conn.commit()

    records_after = get_email_records(conn)
    assert len(records_after) == 0, "email_records must CASCADE DELETE with subscription"


def test_upsert_subscription_idempotent(conn):
    upsert_subscription(
        conn, name="Netflix", amount=15.49, currency="USD",
        billing_cycle="MONTHLY", category="STREAMING", status="ACTIVE", source_provider="MOCK",
    )
    conn.commit()
    upsert_subscription(
        conn, name="Netflix", amount=17.99, currency="USD",
        billing_cycle="MONTHLY", category="STREAMING", status="ACTIVE", source_provider="MOCK",
    )
    conn.commit()

    subs = get_subscriptions(conn)
    netflix = [s for s in subs if s["name"] == "Netflix"]
    assert len(netflix) == 1, "Upserting same name must not create duplicate subscription"


def test_dedup_email_record(conn):
    sub_id = upsert_subscription(
        conn, name="Spotify", amount=9.99, currency="USD",
        billing_cycle="MONTHLY", category="STREAMING", status="ACTIVE", source_provider="MOCK",
    )
    conn.commit()
    first = insert_email_record(
        conn, source_message_id="spotify_001", source_provider="MOCK",
        source_account_id="mock_default", source_account_email="demo@mock.local",
        subscription_id=sub_id, sender_address="a@b.com", sender_name=None,
        subject="Spotify receipt", email_date="2025-01-01T00:00:00Z",
        amount_extracted=9.99, currency_extracted="USD",
        confidence_score=0.9, disposition="DETECTED",
    )
    conn.commit()
    second = insert_email_record(
        conn, source_message_id="spotify_001", source_provider="MOCK",
        source_account_id="mock_default", source_account_email="demo@mock.local",
        subscription_id=sub_id, sender_address="a@b.com", sender_name=None,
        subject="Spotify receipt", email_date="2025-01-01T00:00:00Z",
        amount_extracted=9.99, currency_extracted="USD",
        confidence_score=0.9, disposition="DETECTED",
    )
    conn.commit()
    assert first is not None
    assert second is None, "Duplicate source_message_id must return None (dedup)"
    assert len(get_email_records(conn)) == 1
