from __future__ import annotations

import re
import sys
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = APP_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from migration_002_support import (  # noqa: E402
    CANONICAL_VIEWS,
    EXPECTED_CANONICAL_COUNTS,
    MIGRATION_002_FILE,
    MIGRATION_002_SNAPSHOT_FILE,
    MIGRATION_002_STAGING_SNAPSHOT_FILE,
    NEW_TABLES,
    STAGING_DATABASE,
    is_loopback_host,
    is_loopback_server_address,
    validate_migration_002_text,
)
import verify_migration_002  # noqa: E402


def migration_sql() -> str:
    return MIGRATION_002_FILE.read_text(encoding="utf-8")


def test_migration_is_single_transaction_and_avoids_destructive_ddl() -> None:
    sql = migration_sql()
    validate_migration_002_text(sql)
    upper = sql.upper()
    assert "TRUNCATE " not in upper
    assert "DROP TABLE " not in upper
    assert "DROP SCHEMA " not in upper
    assert "DELETE FROM PUBLIC." not in upper


def test_customer_identity_is_separate_and_order_items_do_not_duplicate_owner() -> None:
    sql = migration_sql()
    assert "ALTER TABLE public.order_items ADD COLUMN customer_account_id" not in sql
    assert not re.search(
        r"ALTER TABLE public\.order_items\s+ADD COLUMN record_origin[^;]*customer_account_id",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert "dataset_user_id BIGINT" in sql
    assert "REFERENCES public.website_sessions(user_id)" not in sql
    assert "REFERENCES public.app_users(app_user_id)" in sql


def test_record_origin_checks_and_parent_origin_fk_are_present() -> None:
    sql = migration_sql()
    for name in (
        "ck_products_origin_context",
        "ck_orders_origin_context",
        "ck_order_items_origin_context",
        "ck_order_item_refunds_origin_context",
        "fk_order_items_order_origin",
        "fk_order_item_refunds_request_context",
    ):
        assert name in sql
    assert "FOREIGN KEY (order_id, record_origin)" in sql
    assert "REFERENCES public.orders(order_id, record_origin)" in sql
    assert "TG_TABLE_NAME = 'orders'" in sql
    assert "IF NEW.customer_account_id IS NOT NULL" in sql
    assert "SELECT o.record_origin INTO parent_origin" in sql
    assert "TG_TABLE_NAME = 'order_item_refunds'" in sql
    assert "IF NEW.refund_request_id IS NOT NULL" in sql


def test_payment_schema_contains_only_approved_safe_metadata() -> None:
    sql = migration_sql().lower()
    for forbidden in ("cvv", "full_card", "card_number", "gcash_number", "paypal_email", "otp", "gateway_token"):
        assert forbidden not in sql
    for allowed in ("card_brand", "card_last_four", "payment_display_snapshot", "simulated_reference"):
        assert allowed in sql


def test_canonical_views_keep_names_columns_and_new_imported_filter() -> None:
    sql = migration_sql()
    for view, columns in CANONICAL_VIEWS.items():
        pattern = re.compile(
            rf"CREATE OR REPLACE VIEW public\.{view} AS\s+SELECT\s+(.*?)\s+FROM public\.[a-z_]+\s+WHERE record_origin = 'imported'\s+OFFSET 0;",
            re.IGNORECASE | re.DOTALL,
        )
        match = pattern.search(sql)
        assert match, view
        observed = tuple(part.strip() for part in match.group(1).replace("\n", " ").split(","))
        assert observed == columns


def test_all_approved_tables_and_verifier_contract_are_declared() -> None:
    sql = migration_sql()
    for table in NEW_TABLES:
        assert f"CREATE TABLE public.{table}" in sql
        assert table in verify_migration_002.EXPECTED_COLUMNS
    assert EXPECTED_CANONICAL_COUNTS["canonical_orders"] == 32_313
    assert MIGRATION_002_SNAPSHOT_FILE.name != "session2_pre_migration_snapshot.json"
    assert MIGRATION_002_STAGING_SNAPSHOT_FILE != MIGRATION_002_SNAPSHOT_FILE
    assert STAGING_DATABASE == "retailmetrics_migration002_test"


def test_only_loopback_database_hosts_are_accepted() -> None:
    for host in ("localhost", "127.0.0.1", "::1", " LOCALHOST "):
        assert is_loopback_host(host)
    for host in ("0.0.0.0", "192.168.1.10", "db.example.test"):
        assert not is_loopback_host(host)
    for address in ("local", "127.0.0.1", "127.0.0.1/32", "::1", "::1/128"):
        assert is_loopback_server_address(address)
    for address in ("0.0.0.0", "192.168.1.10/24", "not-an-address"):
        assert not is_loopback_server_address(address)


def test_design_and_erd_cover_every_required_entity() -> None:
    design = (APP_ROOT / "docs" / "ERD_SPEC.md").read_text(encoding="utf-8")
    dot = (APP_ROOT / "docs" / "erd" / "retailmetrics_erd.dot").read_text(encoding="utf-8")
    required = (
        "app_users", "customer_accounts", "customer_profiles", "customer_addresses",
        "payment_methods", "product_catalog_details", "shopping_carts", "cart_items",
        "website_sessions", "website_pageviews", "products", "orders", "order_items",
        "order_item_refunds", "order_shipping_addresses", "order_payments", "refund_requests",
    )
    for entity in required:
        assert entity in design
        assert entity in dot
    assert "WebsiteSession 1 -> 0..1 Order" in design
    assert "no\n`customer_account_id`" in design


def test_dedicated_launchers_do_not_repurpose_migration_001() -> None:
    runner = (APP_ROOT / "RUN_CUSTOMER_PORTAL_MIGRATION.bat").read_text(encoding="utf-8")
    verifier = (APP_ROOT / "VERIFY_CUSTOMER_PORTAL_MIGRATION.bat").read_text(encoding="utf-8")
    assert "run_migration_002.py" in runner
    assert "verify_migration_002.py" in verifier
    assert "run_migration.py" not in runner
    assert "verify_migration.py" not in verifier


def test_verifier_accepts_postgresql_rendered_origin_casts() -> None:
    assert verify_migration_002.view_uses_imported_origin(
        "WHERE record_origin::text = 'imported'::text OFFSET 0"
    )
    assert not verify_migration_002.view_uses_imported_origin(
        "WHERE created_by_app_user_id IS NULL OFFSET 0"
    )
