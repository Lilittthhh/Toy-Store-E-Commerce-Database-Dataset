from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv


APP_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_FILE = (
    APP_ROOT / "db" / "migrations" / "001_add_app_users_and_crud_metadata.sql"
)
SESSION2_SNAPSHOT_FILE = APP_ROOT / "db" / "session2_pre_migration_snapshot.json"

SESSION2_TABLES = (
    "retailmetrics_event_log",
    "retailmetrics_consumer_offsets",
    "retailmetrics_consumer_partition_offsets",
    "retailmetrics_conversion_audit",
    "retailmetrics_refund_projection",
    "retailmetrics_session_projection",
    "retailmetrics_failure_audit",
    "retailmetrics_stream_runs",
)


def connection_settings() -> dict[str, Any]:
    """Load connection settings without ever supplying a password default."""
    load_dotenv(APP_ROOT / ".env", override=False)

    settings: dict[str, Any] = {
        "host": os.getenv("PGHOST", "localhost"),
        "port": int(os.getenv("PGPORT", "5432")),
        "dbname": os.getenv("PGDATABASE", "retailmetrics"),
        "user": os.getenv("PGUSER", "postgres"),
        "connect_timeout": int(os.getenv("PGCONNECT_TIMEOUT", "10")),
        "application_name": "retailmetrics_web_migration",
    }

    password = os.getenv("PGPASSWORD")
    if password:
        settings["password"] = password

    sslmode = os.getenv("PGSSLMODE")
    if sslmode:
        settings["sslmode"] = sslmode

    return settings


def public_connection_summary(settings: dict[str, Any]) -> str:
    """Return a printable connection target with no credential values."""
    return (
        f"host={settings['host']} port={settings['port']} "
        f"database={settings['dbname']} user={settings['user']}"
    )


def print_postgresql_error(exc: psycopg2.Error) -> None:
    """Print PostgreSQL's diagnostic fields without hiding the original error."""
    print("PostgreSQL error:")
    if exc.pgcode:
        print(f"  SQLSTATE: {exc.pgcode}")

    diagnostics = (
        ("severity", "severity"),
        ("message_primary", "message"),
        ("message_detail", "detail"),
        ("message_hint", "hint"),
        ("context", "context"),
        ("statement_position", "statement position"),
    )
    for attribute, label in diagnostics:
        value = getattr(exc.diag, attribute, None)
        if value:
            print(f"  {label}: {value}")

    print("  complete error:")
    print(str(exc).rstrip())


def capture_session2_fingerprint(conn) -> dict[str, Any]:
    """Capture Session 2 table structure and contents using read-only queries."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.relname
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relkind IN ('r', 'p')
              AND c.relname = ANY(%s)
            ORDER BY c.relname
            """,
            (list(SESSION2_TABLES),),
        )
        present_tables = [row[0] for row in cur.fetchall()]

        cur.execute(
            """
            SELECT
                table_name,
                ordinal_position,
                column_name,
                data_type,
                udt_name,
                is_nullable,
                column_default,
                character_maximum_length,
                numeric_precision,
                numeric_scale
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = ANY(%s)
            ORDER BY table_name, ordinal_position
            """,
            (list(SESSION2_TABLES),),
        )
        columns = [list(row) for row in cur.fetchall()]

        cur.execute(
            """
            SELECT
                child.relname,
                con.conname,
                con.contype,
                pg_get_constraintdef(con.oid, TRUE)
            FROM pg_constraint con
            JOIN pg_class child ON child.oid = con.conrelid
            JOIN pg_namespace n ON n.oid = child.relnamespace
            WHERE n.nspname = 'public'
              AND child.relname = ANY(%s)
            ORDER BY child.relname, con.conname
            """,
            (list(SESSION2_TABLES),),
        )
        constraints = [list(row) for row in cur.fetchall()]

        cur.execute(
            """
            SELECT tablename, indexname, indexdef
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND tablename = ANY(%s)
            ORDER BY tablename, indexname
            """,
            (list(SESSION2_TABLES),),
        )
        indexes = [list(row) for row in cur.fetchall()]

        row_counts: dict[str, int] = {}
        for table_name in present_tables:
            cur.execute(
                sql.SQL("SELECT COUNT(*) FROM public.{}").format(
                    sql.Identifier(table_name)
                )
            )
            row_counts[table_name] = int(cur.fetchone()[0])

        cur.execute(
            """
            SELECT
                current_database(),
                COALESCE(inet_server_addr()::text, 'local'),
                inet_server_port(),
                current_setting('server_version')
            """
        )
        database, server_address, server_port, server_version = cur.fetchone()

    return {
        "database_identity": {
            "database": database,
            "server_address": server_address,
            "server_port": server_port,
            "server_version": server_version,
        },
        "session2_tables_expected": list(SESSION2_TABLES),
        "session2_tables_present": present_tables,
        "columns": columns,
        "constraints": constraints,
        "indexes": indexes,
        "row_counts": row_counts,
    }


def save_session2_snapshot(fingerprint: dict[str, Any]) -> None:
    document = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "fingerprint": fingerprint,
    }
    temporary_path = SESSION2_SNAPSHOT_FILE.with_suffix(".json.tmp")
    temporary_path.write_text(
        json.dumps(document, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary_path.replace(SESSION2_SNAPSHOT_FILE)


def load_session2_snapshot() -> dict[str, Any]:
    document = json.loads(SESSION2_SNAPSHOT_FILE.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or "fingerprint" not in document:
        raise ValueError("Session 2 snapshot has an invalid format")
    return document
