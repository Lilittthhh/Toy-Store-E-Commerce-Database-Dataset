from __future__ import annotations

import argparse
import hashlib
import json
import sys

import psycopg2

from migration_support import (
    MIGRATION_FILE,
    SESSION2_SNAPSHOT_FILE,
    capture_session2_fingerprint,
    connection_settings,
    print_postgresql_error,
    public_connection_summary,
    save_session2_snapshot,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply the approved RetailMetricsWeb migration once."
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the interactive database-name confirmation.",
    )
    return parser.parse_args()


def validate_migration_text(migration_sql: str) -> None:
    statements = migration_sql.strip()
    if not statements.startswith("-- RetailMetrics Web"):
        raise ValueError("Migration header is missing or unexpected")
    if statements.count("BEGIN;") != 1 or statements.count("COMMIT;") != 1:
        raise ValueError("Migration must contain exactly one BEGIN and one COMMIT")
    if not statements.endswith("COMMIT;"):
        raise ValueError("Migration must end with COMMIT")


def main() -> int:
    args = parse_args()
    if not MIGRATION_FILE.is_file():
        print(f"ERROR: migration file not found: {MIGRATION_FILE}", file=sys.stderr)
        return 1
    if SESSION2_SNAPSHOT_FILE.exists():
        print(
            "ERROR: a pre-migration Session 2 snapshot already exists at "
            f"{SESSION2_SNAPSHOT_FILE}",
            file=sys.stderr,
        )
        print(
            "Refusing to overwrite deployment evidence or execute the migration. "
            "Verify the database state before taking any further action.",
            file=sys.stderr,
        )
        return 1

    migration_sql = MIGRATION_FILE.read_text(encoding="utf-8")
    try:
        validate_migration_text(migration_sql)
        settings = connection_settings()
    except (ValueError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    digest = hashlib.sha256(migration_sql.encode("utf-8")).hexdigest()
    print("RetailMetricsWeb migration runner")
    print(f"Target:    {public_connection_summary(settings)}")
    print(f"Migration: {MIGRATION_FILE}")
    print(f"SHA-256:   {digest}")
    print("The password is never displayed.")

    if not args.yes:
        try:
            confirmation = input(
                f"Type the database name '{settings['dbname']}' to continue: "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nMigration cancelled before connecting.")
            return 1
        if confirmation != settings["dbname"]:
            print("Migration cancelled: database name did not match.")
            return 1

    conn = None
    try:
        conn = psycopg2.connect(**settings)
        conn.set_session(isolation_level="REPEATABLE READ", readonly=True)
        fingerprint = capture_session2_fingerprint(conn)
        conn.rollback()
        save_session2_snapshot(fingerprint)
        print(f"Session 2 pre-migration snapshot: {SESSION2_SNAPSHOT_FILE}")

        # The SQL file owns its BEGIN/COMMIT transaction. Autocommit prevents
        # psycopg2 from wrapping that file in a second implicit transaction.
        conn.set_session(readonly=False, autocommit=True)

        # Deliberately submit the complete approved migration exactly once.
        with conn.cursor() as cur:
            cur.execute(migration_sql)

        print("Migration completed successfully.")
        print("Run the post-migration verifier next.")
        return 0
    except psycopg2.Error as exc:
        if conn is not None and not conn.closed:
            try:
                with conn.cursor() as cur:
                    cur.execute("ROLLBACK")
            except psycopg2.Error:
                pass
        print_postgresql_error(exc)
        print("Migration failed. No automatic retry was attempted.", file=sys.stderr)
        return 1
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print("Migration was not executed.", file=sys.stderr)
        return 1
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
