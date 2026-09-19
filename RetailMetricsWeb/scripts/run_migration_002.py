from __future__ import annotations

import argparse
import hashlib
import json
import sys

import psycopg2

from migration_002_support import (
    MIGRATION_002_FILE,
    MIGRATION_002_SNAPSHOT_FILE,
    MIGRATION_002_STAGING_SNAPSHOT_FILE,
    STAGING_DATABASE,
    build_snapshot,
    run_preflight,
    save_snapshot,
    validate_migration_002_text,
)
from migration_support import connection_settings, print_postgresql_error, public_connection_summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply RetailMetricsWeb migration 002 exactly once.")
    parser.add_argument("--yes", action="store_true", help="Skip database-name confirmation.")
    parser.add_argument(
        "--staging",
        action="store_true",
        help=f"Permit only the isolated {STAGING_DATABASE} target and use its separate snapshot.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not MIGRATION_002_FILE.is_file():
        print(f"ERROR: migration file not found: {MIGRATION_002_FILE}", file=sys.stderr)
        return 1
    snapshot_file = (
        MIGRATION_002_STAGING_SNAPSHOT_FILE if args.staging else MIGRATION_002_SNAPSHOT_FILE
    )
    expected_database = STAGING_DATABASE if args.staging else "retailmetrics"
    if snapshot_file.exists():
        print(f"ERROR: deployment snapshot already exists: {snapshot_file}", file=sys.stderr)
        print("Refusing to overwrite evidence or rerun migration 002.", file=sys.stderr)
        return 1

    try:
        migration_sql = MIGRATION_002_FILE.read_text(encoding="utf-8")
        validate_migration_002_text(migration_sql)
        settings = connection_settings()
    except (OSError, TypeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if settings["dbname"] != expected_database:
        print(
            f"ERROR: {'staging' if args.staging else 'production'} mode requires "
            f"PGDATABASE={expected_database}; observed {settings['dbname']!r}.",
            file=sys.stderr,
        )
        return 1

    digest = hashlib.sha256(migration_sql.encode("utf-8")).hexdigest()
    print("RetailMetricsWeb customer-portal migration runner")
    print(f"Target:    {public_connection_summary(settings)}")
    print(f"Migration: {MIGRATION_002_FILE}")
    print(f"SHA-256:   {digest}")
    print("Credentials are read from the environment/.env and the password is never displayed.")

    if not args.yes:
        try:
            confirmation = input(f"Type the database name '{settings['dbname']}' to continue: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nMigration cancelled before connecting.")
            return 1
        if confirmation != settings["dbname"]:
            print("Migration cancelled: database name did not match.")
            return 1

    conn = None
    try:
        conn = psycopg2.connect(**settings)
        conn.set_session(isolation_level="REPEATABLE READ", readonly=True, autocommit=False)
        with conn.cursor() as cur:
            errors, facts = run_preflight(
                cur, settings["dbname"], settings["host"], expected_database
            )
        if errors:
            conn.rollback()
            print("PREFLIGHT: FAIL", file=sys.stderr)
            for error in errors:
                print(f"  - {error}", file=sys.stderr)
            print("Migration 002 was not executed and no snapshot was written.", file=sys.stderr)
            return 1

        snapshot = build_snapshot(conn, facts, digest)
        conn.rollback()
        save_snapshot(snapshot, snapshot_file)
        print("PREFLIGHT: PASS")
        print(f"Pre-migration snapshot: {snapshot_file}")

        # The SQL owns its single BEGIN/COMMIT transaction. Submit it once.
        conn.set_session(readonly=False, autocommit=True)
        with conn.cursor() as cur:
            cur.execute(migration_sql)

        print("Migration 002 completed successfully.")
        print("Run VERIFY_CUSTOMER_PORTAL_MIGRATION.bat next.")
        return 0
    except psycopg2.Error as exc:
        if conn is not None and not conn.closed:
            try:
                with conn.cursor() as cur:
                    cur.execute("ROLLBACK")
            except psycopg2.Error:
                pass
        print_postgresql_error(exc)
        print("Migration 002 failed; no automatic retry was attempted.", file=sys.stderr)
        return 1
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        if conn is not None and not conn.closed:
            conn.rollback()
        print(f"ERROR: {exc}", file=sys.stderr)
        print("Migration 002 was not executed.", file=sys.stderr)
        return 1
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
