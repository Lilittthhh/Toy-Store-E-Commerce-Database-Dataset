"""Apply additive notification migration once, only after a verified fresh backup."""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

import psycopg2

from migration_support import APP_ROOT, connection_settings, print_postgresql_error, public_connection_summary


MIGRATION = APP_ROOT / "db" / "migrations" / "003_notification_outbox.sql"
RESTORE = Path("C:/Program Files/PostgreSQL/18/bin/pg_restore.exe")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup", type=Path, required=True, help="Fresh custom-format pre-Migration-003 backup")
    parser.add_argument("--yes", action="store_true", help="Skip interactive database-name confirmation")
    args = parser.parse_args()
    backup = args.backup.resolve()
    if not backup.is_file() or backup.parent != (APP_ROOT / "backups").resolve() or not backup.name.startswith("retailmetrics_pre_migration003_"):
        print("ERROR: supply a fresh backup within RetailMetricsWeb/backups", file=sys.stderr)
        return 1
    if not RESTORE.is_file() or subprocess.run([str(RESTORE), "--list", str(backup)], capture_output=True).returncode:
        print("ERROR: pg_restore --list failed for the backup", file=sys.stderr)
        return 1
    settings = connection_settings()
    if settings["dbname"] != "retailmetrics" or settings["host"] not in {"localhost", "127.0.0.1"}:
        print("ERROR: migration 003 requires localhost retailmetrics", file=sys.stderr)
        return 1
    source = MIGRATION.read_text(encoding="utf-8")
    print(f"Target: {public_connection_summary(settings)}")
    print(f"Migration SHA-256: {hashlib.sha256(source.encode()).hexdigest()}")
    print(f"Backup: {backup.name}; bytes={backup.stat().st_size}; SHA-256={hashlib.sha256(backup.read_bytes()).hexdigest()}")
    if not args.yes and input("Type retailmetrics to apply migration 003: ").strip() != "retailmetrics":
        print("Cancelled before connecting")
        return 1
    conn = None
    try:
        conn = psycopg2.connect(**settings)
        conn.set_session(readonly=True, autocommit=False)
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.notification_outbox')")
            if cur.fetchone()[0] is not None:
                print("ERROR: notification_outbox already exists; refusing rerun", file=sys.stderr)
                return 1
            cur.execute("SELECT to_regclass('public.customer_accounts'),to_regclass('public.refund_requests')")
            if any(item is None for item in cur.fetchone()):
                print("ERROR: Migration 002 objects are missing", file=sys.stderr)
                return 1
        conn.rollback()
        conn.set_session(readonly=False, autocommit=True)
        with conn.cursor() as cur:
            cur.execute(source)  # SQL owns its BEGIN/COMMIT; exactly one submission.
        print("Migration 003 applied successfully. Run verify_migration_003.py.")
        return 0
    except psycopg2.Error as exc:
        print_postgresql_error(exc)
        return 1
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
