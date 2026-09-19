# Migration 002 Deployment Runbook

## Current status

Migration 002 was applied successfully to the live local `retailmetrics`
database on 2026-09-11 after its production preflight passed. The cumulative
migration-002 verifier reported `OVERALL: PASS`, and the cleanup-safe backend
suite passed with the canonical baseline unchanged and no temporary business or
customer-portal rows remaining.

The pre-deployment custom-format backup is:
`backups/retailmetrics_pre_migration002_live_20260911_131056.backup`
(58,325,121 bytes; SHA-256
`3F188DF688A9FD85C5D3F5DD5B46F0A3240B72F458471753CA8984C7A94C1EA4`).
Its `pg_restore --list` validation passed. The ignored production snapshot is
`db/customer_portal_pre_migration_snapshot.json`.

## Intended deployment order

1. Stop FastAPI and Streamlit so no business writes can race the preflight.
2. Confirm `RetailMetricsWeb/.env` targets the local `retailmetrics` database.
3. Preserve the existing migration-001 snapshot; migration 002 uses the separate
   ignored file `db/customer_portal_pre_migration_snapshot.json`.
4. Run `RUN_CUSTOMER_PORTAL_MIGRATION.bat` once. The runner performs read-only
   preflight first, writes a fresh fingerprint only after PASS, then submits the
   complete SQL file exactly once.
5. Run `VERIFY_CUSTOMER_PORTAL_MIGRATION.bat`. The verifier is read-only.
6. Restart the current app only after `OVERALL: PASS`.

`VERIFY_WEB_MIGRATION.bat` remains the migration-001 point-in-time verifier. It
expects the old creator-FK deletion action and old canonical predicate, so it is
not the correct verifier after migration 002. Do not alter its original snapshot;
use the dedicated migration-002 verifier for the cumulative schema.

The command-line equivalents from `RetailMetricsWeb/` are:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_migration_002.py
.\.venv\Scripts\python.exe .\scripts\verify_migration_002.py
```

The optional runner `--yes` flag skips only the typed database-name prompt; it
does not skip preflight.

## Isolated staging validation

Staging mode is deliberately limited to the database name
`retailmetrics_migration002_test` and uses a separate ignored snapshot. From
`RetailMetricsWeb/`, set only the process-level database override and run:

```powershell
$env:PGDATABASE = "retailmetrics_migration002_test"
.\.venv\Scripts\python.exe .\scripts\run_migration_002.py --staging
.\.venv\Scripts\python.exe .\scripts\verify_migration_002.py --staging
```

Production mode still accepts only `retailmetrics`; staging mode cannot be used
to authorize an arbitrary database name.

## Recoverable backup required before production

Create a fresh PostgreSQL custom-format backup immediately before the live
migration, while writes are stopped. PostgreSQL credentials must come from the
environment, `.pgpass`, or pgAdmin's saved connection and must never be placed
in the command or backup filename.

```powershell
& "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe" `
  --host=$env:PGHOST --port=$env:PGPORT --username=$env:PGUSER `
  --dbname=retailmetrics --format=custom --no-owner --no-privileges `
  --file="D:\secure-backups\retailmetrics_pre_migration002.backup"

& "C:\Program Files\PostgreSQL\18\bin\pg_restore.exe" `
  --list "D:\secure-backups\retailmetrics_pre_migration002.backup"
```

Store the backup outside Git and preferably outside the working tree. Validate
it with `pg_restore --list` and, ideally, a restore into a newly created test
database. Never test recovery by restoring over `retailmetrics`.

In pgAdmin: right-click `retailmetrics` → **Backup**, select **Custom** format,
choose a protected destination, and disable ownership/privilege restoration if
the backup will be tested under another local owner. Confirm the process log
reports success. Use **Restore** only with a newly created isolated database.

## Fail-fast and recovery behavior

The runner refuses a non-loopback database, the wrong database name, missing or
partial migration-001 state, altered canonical counts/shapes, incompatible
existing application rows, invalid relationships, or an existing migration-002
snapshot/schema marker. The SQL repeats critical classification checks inside
its transaction. Any PostgreSQL error aborts and rolls back all migration DDL/DML.
There is no automatic retry.

If SQL execution fails after the snapshot was written, do not delete the marker
and retry blindly. Review the exact PostgreSQL error and database state first.

## Session 1 loader compatibility boundary

The Session 1 CSV importer uses explicit COPY column lists, so omitted
`record_origin` is safely classified as `imported` by migration-002 compatibility
triggers. Canonical query names and column shapes remain unchanged.

However, the authoritative Session 1 loader also performs `TRUNCATE ... CASCADE`.
After real customer/cart/order workflow data exists, rerunning that destructive
loader could cascade into portal tables that reference the six source tables.
Treat the imported baseline as established and do not rerun the full Session 1
loader against the operational database after portal data is created. If a
future baseline refresh is required, design a separate staged refresh process
with backup/reconciliation; do not use the original truncate workflow.

## No seeded portal data

Migration 002 creates no customer, profile, address, payment, cart, order,
refund-request, catalog-detail, password, price, or demo row. Product storefront
prices and availability remain intentionally empty until a later authorized
application workflow populates `product_catalog_details`.
