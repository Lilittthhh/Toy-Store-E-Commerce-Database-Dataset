from pathlib import Path
import re


SQL = (Path(__file__).resolve().parents[2] / "db" / "migrations" /
       "004_order_delivery_confirmation.sql").read_text(encoding="utf-8")


def test_migration_004_is_transactional_and_preserves_imported_rows():
    statements = SQL.upper()
    assert statements.lstrip().startswith("-- ADDITIVE")
    assert "BEGIN;" in statements and statements.rstrip().endswith("COMMIT;")
    for forbidden in ("TRUNCATE", "DELETE FROM", "DROP TABLE", "DROP SCHEMA", "UPDATE PUBLIC.WEBSITE_SESSIONS"):
        assert forbidden not in statements
    assert re.search(
        r"WHERE\s+record_origin\s+IN\s*\('staff',\s*'customer'\)\s+AND\s+order_status\s*=\s*'completed'",
        SQL,
    )
    assert re.search(r"DROP CONSTRAINT\s+(?:IF EXISTS\s+)?ck_orders_status", SQL)
    assert SQL.index("DROP CONSTRAINT") < SQL.index("UPDATE public.orders") < SQL.index("ADD CONSTRAINT ck_orders_status")


def test_migration_004_delivery_metadata_and_outbox_events():
    for expected in (
        "delivered_at TIMESTAMPTZ", "delivered_confirmed_by_customer BOOLEAN NOT NULL DEFAULT FALSE",
        "ck_orders_delivery_confirmation",
        "order_ready_shipped", "order_delivered", "order_completed",
        "ck_notification_outbox_target", "ck_notification_outbox_event_channel",
    ):
        assert expected in SQL
    assert re.search(r"record_origin\s*=\s*'customer'", SQL)
