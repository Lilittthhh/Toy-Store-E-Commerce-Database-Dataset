from __future__ import annotations

import hashlib
import ipaddress
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from migration_support import APP_ROOT, capture_session2_fingerprint


MIGRATION_002_FILE = (
    APP_ROOT / "db" / "migrations" / "002_customer_portal_and_order_workflow.sql"
)
MIGRATION_002_SNAPSHOT_FILE = APP_ROOT / "db" / "customer_portal_pre_migration_snapshot.json"
STAGING_DATABASE = "retailmetrics_migration002_test"
MIGRATION_002_STAGING_SNAPSHOT_FILE = (
    APP_ROOT / "db" / "customer_portal_staging_pre_migration_snapshot.json"
)
REPOSITORY_ROOT = APP_ROOT.parent

ORIGINAL_TABLES = (
    "website_sessions",
    "website_pageviews",
    "products",
    "orders",
    "order_items",
    "order_item_refunds",
)
BUSINESS_TABLES = ("products", "orders", "order_items", "order_item_refunds")
CANONICAL_VIEWS = {
    "canonical_products": ("product_id", "created_at", "product_name"),
    "canonical_orders": (
        "order_id", "created_at", "website_session_id", "user_id",
        "primary_product_id", "items_purchased", "price_usd", "cogs_usd",
    ),
    "canonical_order_items": (
        "order_item_id", "created_at", "order_id", "product_id",
        "is_primary_item", "price_usd", "cogs_usd",
    ),
    "canonical_order_item_refunds": (
        "order_item_refund_id", "created_at", "order_item_id", "order_id",
        "refund_amount_usd",
    ),
}
EXPECTED_CANONICAL_COUNTS = {
    "website_sessions": 472_871,
    "website_pageviews": 1_188_124,
    "canonical_products": 4,
    "canonical_orders": 32_313,
    "canonical_order_items": 40_025,
    "canonical_order_item_refunds": 1_731,
}
NEW_TABLES = (
    "customer_accounts",
    "customer_profiles",
    "customer_addresses",
    "payment_methods",
    "product_catalog_details",
    "shopping_carts",
    "cart_items",
    "order_shipping_addresses",
    "order_payments",
    "refund_requests",
)
EVIDENCE_FILES = (
    "session1_parallel_compute/results/session_journey_metrics.parquet",
    "session1_parallel_compute/results/baseline_result.csv",
    "session2_event_streaming/results/stream_session_metrics.csv",
    "session2_event_streaming/results/reconciliation_report.json",
    "session2_event_streaming/results/consumer_summary.json",
)


def validate_migration_002_text(migration_sql: str) -> None:
    text = migration_sql.strip()
    if not text.startswith("-- RetailMetrics Web"):
        raise ValueError("Migration 002 header is missing or unexpected")
    if text.count("BEGIN;") != 1 or text.count("COMMIT;") != 1:
        raise ValueError("Migration 002 must contain exactly one BEGIN and one COMMIT")
    if not text.endswith("COMMIT;"):
        raise ValueError("Migration 002 must end with COMMIT")
    forbidden = ("TRUNCATE ", "DROP TABLE ", "DROP SCHEMA ")
    upper = text.upper()
    for phrase in forbidden:
        if phrase in upper:
            raise ValueError(f"Migration 002 contains prohibited SQL: {phrase.strip()}")


def is_loopback_host(host: str) -> bool:
    return host.strip().lower() in {"localhost", "127.0.0.1", "::1"}


def is_loopback_server_address(address: str) -> bool:
    if address == "local":
        return True
    try:
        return ipaddress.ip_interface(address).ip.is_loopback
    except ValueError:
        return False


def _relation_exists(cur, name: str, kinds: tuple[str, ...]) -> bool:
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = %s
              AND c.relkind = ANY(%s)
        )
        """,
        (name, list(kinds)),
    )
    return bool(cur.fetchone()[0])


def _view_columns(cur, name: str) -> tuple[str, ...]:
    cur.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
        """,
        (name,),
    )
    return tuple(row[0] for row in cur.fetchall())


def _count(cur, relation: str) -> int:
    # All relation names are constants owned by this module.
    cur.execute(f'SELECT COUNT(*) FROM public."{relation}"')
    return int(cur.fetchone()[0])


def capture_evidence_hashes() -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for relative in EVIDENCE_FILES:
        path = REPOSITORY_ROOT / relative
        result[relative] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    return result


def run_preflight(
    cur,
    configured_database: str,
    configured_host: str,
    required_database: str = "retailmetrics",
) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    facts: dict[str, Any] = {}

    cur.execute(
        """SELECT current_database(), current_setting('server_version_num')::integer,
                  COALESCE(inet_server_addr()::text, 'local'), inet_server_port(),
                  current_setting('listen_addresses')"""
    )
    database, version_num, server_address, server_port, listen_addresses = cur.fetchone()
    facts["database_identity"] = {
        "database": database,
        "server_version_num": int(version_num),
        "server_address": server_address,
        "server_port": server_port,
        "listen_addresses": listen_addresses,
    }
    if database != configured_database or database != required_database:
        errors.append(
            f"target database must be {required_database!r} (observed {database!r})"
        )
    if int(version_num) < 100000:
        errors.append("PostgreSQL 10 or newer is required")
    if not is_loopback_host(configured_host):
        errors.append(f"configured PGHOST is not loopback-only: {configured_host!r}")
    allowed_listeners = {"localhost", "127.0.0.1", "::1"}
    listeners = {part.strip().lower() for part in str(listen_addresses).split(",")}
    if not listeners or not listeners.issubset(allowed_listeners):
        errors.append(f"PostgreSQL listen_addresses is not loopback-only: {listen_addresses!r}")
    if not is_loopback_server_address(server_address):
        errors.append(f"connected PostgreSQL endpoint is not loopback: {server_address!r}")

    missing = [name for name in (*ORIGINAL_TABLES, "app_users") if not _relation_exists(cur, name, ("r", "p"))]
    if missing:
        errors.append(f"missing migration-001/source tables: {missing}")
        facts["missing_required_tables"] = missing
        return errors, facts

    migration_001_objects: dict[str, Any] = {}
    cur.execute(
        """SELECT to_regclass('public.retailmetrics_app_entity_id_seq') IS NOT NULL,
                  to_regclass('public.uq_orders_website_session_id') IS NOT NULL"""
    )
    sequence_exists, order_session_uq_exists = cur.fetchone()
    migration_001_objects["shared_sequence"] = bool(sequence_exists)
    migration_001_objects["unique_order_session_index"] = bool(order_session_uq_exists)
    if not sequence_exists:
        errors.append("migration-001 shared business-ID sequence is missing")
    if not order_session_uq_exists:
        errors.append("migration-001 unique orders.website_session_id index is missing")

    creator_fk_names = (
        "fk_products_created_by_app_user", "fk_orders_created_by_app_user",
        "fk_order_items_created_by_app_user", "fk_order_item_refunds_created_by_app_user",
    )
    cur.execute(
        """SELECT conname, confdeltype, convalidated FROM pg_constraint
           WHERE conname=ANY(%s) ORDER BY conname""",
        (list(creator_fk_names),),
    )
    creator_fks = {row[0]: {"delete": row[1], "validated": row[2]} for row in cur.fetchall()}
    migration_001_objects["creator_foreign_keys"] = creator_fks
    if set(creator_fks) != set(creator_fk_names) or any(
        value != {"delete": "n", "validated": True} for value in creator_fks.values()
    ):
        errors.append("migration-001 creator FKs are missing, invalid, or not ON DELETE SET NULL")

    pk_columns = {
        "products": "product_id", "orders": "order_id",
        "order_items": "order_item_id", "order_item_refunds": "order_item_refund_id",
    }
    pk_defaults: dict[str, str | None] = {}
    for table, column in pk_columns.items():
        cur.execute(
            """SELECT column_default FROM information_schema.columns
               WHERE table_schema='public' AND table_name=%s AND column_name=%s""",
            (table, column),
        )
        row = cur.fetchone()
        default = row[0] if row else None
        pk_defaults[table] = default
        if not default or "retailmetrics_app_entity_id_seq" not in default:
            errors.append(f"migration-001 shared sequence default is invalid on {table}.{column}")
    migration_001_objects["primary_key_defaults"] = pk_defaults
    facts["migration_001_objects"] = migration_001_objects

    expected_original_fks = {
        ("website_pageviews", "website_session_id", "website_sessions", "website_session_id"),
        ("orders", "website_session_id", "website_sessions", "website_session_id"),
        ("orders", "primary_product_id", "products", "product_id"),
        ("order_items", "order_id", "orders", "order_id"),
        ("order_items", "product_id", "products", "product_id"),
        ("order_item_refunds", "order_item_id", "order_items", "order_item_id"),
        ("order_item_refunds", "order_id", "orders", "order_id"),
    }
    cur.execute(
        """SELECT child.relname, child_col.attname, parent.relname, parent_col.attname
           FROM pg_constraint con
           JOIN pg_class child ON child.oid=con.conrelid
           JOIN pg_namespace n ON n.oid=child.relnamespace
           JOIN pg_class parent ON parent.oid=con.confrelid
           JOIN LATERAL generate_subscripts(con.conkey,1) p(position) ON TRUE
           JOIN pg_attribute child_col ON child_col.attrelid=child.oid
             AND child_col.attnum=con.conkey[p.position]
           JOIN pg_attribute parent_col ON parent_col.attrelid=parent.oid
             AND parent_col.attnum=con.confkey[p.position]
           WHERE n.nspname='public' AND con.contype='f' AND con.convalidated"""
    )
    observed_original_fks = {tuple(row) for row in cur.fetchall()}
    missing_original_fks = sorted(expected_original_fks - observed_original_fks)
    facts["missing_original_foreign_keys"] = [list(row) for row in missing_original_fks]
    if missing_original_fks:
        errors.append(f"original Toy Store foreign keys are missing: {missing_original_fks}")

    existing_new = [name for name in NEW_TABLES if _relation_exists(cur, name, ("r", "p"))]
    if existing_new:
        errors.append(f"migration-002 tables already exist: {existing_new}")
    cur.execute(
        """SELECT table_name FROM information_schema.columns
           WHERE table_schema = 'public' AND table_name = ANY(%s)
             AND column_name = 'record_origin' ORDER BY table_name""",
        (list(BUSINESS_TABLES),),
    )
    existing_origins = [row[0] for row in cur.fetchall()]
    if existing_origins:
        errors.append(f"migration-002 origin columns already exist: {existing_origins}")

    migration_001_columns: dict[str, list[str]] = {}
    for table in BUSINESS_TABLES:
        cur.execute(
            """SELECT column_name FROM information_schema.columns
               WHERE table_schema = 'public' AND table_name = %s
                 AND column_name IN ('created_by_app_user_id', 'row_version')
               ORDER BY column_name""",
            (table,),
        )
        columns = [row[0] for row in cur.fetchall()]
        migration_001_columns[table] = columns
        if columns != ["created_by_app_user_id", "row_version"]:
            errors.append(f"migration-001 columns invalid on {table}: {columns}")
    facts["migration_001_columns"] = migration_001_columns

    view_shapes: dict[str, list[str]] = {}
    for view, expected in CANONICAL_VIEWS.items():
        if not _relation_exists(cur, view, ("v",)):
            errors.append(f"missing canonical view: {view}")
            continue
        columns = _view_columns(cur, view)
        view_shapes[view] = list(columns)
        if columns != expected:
            errors.append(f"canonical view shape mismatch for {view}: {columns}")
        cur.execute("SELECT pg_get_viewdef(%s::regclass, TRUE)", (f"public.{view}",))
        definition = " ".join(cur.fetchone()[0].lower().split())
        if "created_by_app_user_id is null" not in definition:
            errors.append(f"migration-001 canonical filter is invalid for {view}")
    facts["canonical_view_columns"] = view_shapes

    counts: dict[str, int] = {}
    for relation, expected in EXPECTED_CANONICAL_COUNTS.items():
        if relation in view_shapes or relation in {"website_sessions", "website_pageviews"}:
            actual = _count(cur, relation)
            counts[relation] = actual
            if actual != expected:
                errors.append(f"canonical count mismatch for {relation}: expected {expected}, observed {actual}")
    facts["canonical_counts"] = counts

    business_counts = {table: _count(cur, table) for table in BUSINESS_TABLES if _relation_exists(cur, table, ("r", "p"))}
    facts["business_counts"] = business_counts

    application_counts: dict[str, int] = {}
    for table in BUSINESS_TABLES:
        cur.execute(f"SELECT COUNT(*) FROM public.{table} WHERE created_by_app_user_id IS NOT NULL")
        application_counts[table] = int(cur.fetchone()[0])
    facts["existing_application_counts"] = application_counts

    app_orders = application_counts["orders"]
    facts["existing_application_orders"] = app_orders
    if app_orders:
        errors.append("application-created orders lack an explicit lifecycle status and cannot be safely reclassified")

    cur.execute(
        """SELECT COUNT(*) FROM public.order_items oi
           JOIN public.orders o ON o.order_id = oi.order_id
           WHERE (oi.created_by_app_user_id IS NULL)
                 IS DISTINCT FROM (o.created_by_app_user_id IS NULL)"""
    )
    mismatched_items = int(cur.fetchone()[0])
    facts["origin_mismatched_order_items"] = mismatched_items
    if mismatched_items:
        errors.append(f"{mismatched_items} existing order items cannot inherit their parent order origin")

    cur.execute(
        """SELECT COUNT(*) FROM (
             SELECT p.created_by_app_user_id FROM public.products p
             LEFT JOIN public.app_users u ON u.app_user_id = p.created_by_app_user_id
             WHERE p.created_by_app_user_id IS NOT NULL AND u.app_user_id IS NULL
             UNION ALL
             SELECT o.created_by_app_user_id FROM public.orders o
             LEFT JOIN public.app_users u ON u.app_user_id = o.created_by_app_user_id
             WHERE o.created_by_app_user_id IS NOT NULL AND u.app_user_id IS NULL
             UNION ALL
             SELECT oi.created_by_app_user_id FROM public.order_items oi
             LEFT JOIN public.app_users u ON u.app_user_id = oi.created_by_app_user_id
             WHERE oi.created_by_app_user_id IS NOT NULL AND u.app_user_id IS NULL
             UNION ALL
             SELECT r.created_by_app_user_id FROM public.order_item_refunds r
             LEFT JOIN public.app_users u ON u.app_user_id = r.created_by_app_user_id
             WHERE r.created_by_app_user_id IS NOT NULL AND u.app_user_id IS NULL
           ) invalid_creator"""
    )
    invalid_creators = int(cur.fetchone()[0])
    facts["invalid_creator_relationships"] = invalid_creators
    if invalid_creators:
        errors.append(f"{invalid_creators} invalid creator relationships exist")

    cur.execute(
        """SELECT COUNT(*) FROM (
             SELECT row_version FROM public.products WHERE row_version < 1
             UNION ALL SELECT row_version FROM public.orders WHERE row_version < 1
             UNION ALL SELECT row_version FROM public.order_items WHERE row_version < 1
             UNION ALL SELECT row_version FROM public.order_item_refunds WHERE row_version < 1
           ) invalid_version"""
    )
    invalid_versions = int(cur.fetchone()[0])
    facts["invalid_row_versions"] = invalid_versions
    if invalid_versions:
        errors.append(f"{invalid_versions} invalid row_version values exist")

    cur.execute(
        """SELECT COUNT(*) FROM (
             SELECT wp.website_pageview_id FROM public.website_pageviews wp
             LEFT JOIN public.website_sessions ws ON ws.website_session_id = wp.website_session_id
             WHERE ws.website_session_id IS NULL
             UNION ALL
             SELECT o.order_id FROM public.orders o
             LEFT JOIN public.website_sessions ws ON ws.website_session_id = o.website_session_id
             LEFT JOIN public.products p ON p.product_id = o.primary_product_id
             WHERE ws.website_session_id IS NULL
                OR (o.primary_product_id IS NOT NULL AND p.product_id IS NULL)
             UNION ALL
             SELECT oi.order_item_id FROM public.order_items oi
             LEFT JOIN public.orders o ON o.order_id = oi.order_id
             LEFT JOIN public.products p ON p.product_id = oi.product_id
             WHERE o.order_id IS NULL OR p.product_id IS NULL
             UNION ALL
             SELECT r.order_item_refund_id FROM public.order_item_refunds r
             LEFT JOIN public.orders o ON o.order_id = r.order_id
             LEFT JOIN public.order_items oi ON oi.order_item_id = r.order_item_id
             WHERE o.order_id IS NULL OR oi.order_item_id IS NULL OR oi.order_id <> r.order_id
           ) orphan"""
    )
    orphans = int(cur.fetchone()[0])
    facts["incompatible_orphans"] = orphans
    if orphans:
        errors.append(f"{orphans} incompatible/orphan source relationships exist")

    return errors, facts


def build_snapshot(conn, facts: dict[str, Any], migration_digest: str) -> dict[str, Any]:
    return {
        "format_version": 1,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "migration_sha256": migration_digest,
        "preflight": facts,
        "session2_fingerprint": capture_session2_fingerprint(conn),
        "evidence_sha256": capture_evidence_hashes(),
    }


def save_snapshot(
    document: dict[str, Any], path: Path = MIGRATION_002_SNAPSHOT_FILE
) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def load_snapshot(path: Path = MIGRATION_002_SNAPSHOT_FILE) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("format_version") != 1:
        raise ValueError("migration-002 snapshot has an invalid format")
    return document
