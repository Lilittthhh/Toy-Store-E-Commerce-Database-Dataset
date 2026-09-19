from __future__ import annotations

import argparse
import sys
from typing import Any

import psycopg2

from migration_002_support import (
    BUSINESS_TABLES,
    CANONICAL_VIEWS,
    EXPECTED_CANONICAL_COUNTS,
    MIGRATION_002_SNAPSHOT_FILE,
    MIGRATION_002_STAGING_SNAPSHOT_FILE,
    NEW_TABLES,
    STAGING_DATABASE,
    capture_evidence_hashes,
    load_snapshot,
)
from migration_support import (
    capture_session2_fingerprint,
    connection_settings,
    print_postgresql_error,
    public_connection_summary,
)


EXPECTED_COLUMNS: dict[str, dict[str, tuple[str, str]]] = {
    "customer_accounts": {
        "customer_account_id": ("bigint", "NO"), "dataset_user_id": ("bigint", "YES"),
        "email": ("character varying", "NO"), "password_hash": ("text", "NO"),
        "is_active": ("boolean", "NO"), "failed_login_attempts": ("integer", "NO"),
        "locked_until": ("timestamp with time zone", "YES"), "last_login_at": ("timestamp with time zone", "YES"),
        "password_changed_at": ("timestamp with time zone", "NO"),
        "password_reset_token_hash": ("character", "YES"),
        "password_reset_expires_at": ("timestamp with time zone", "YES"),
        "token_version": ("integer", "NO"), "row_version": ("bigint", "NO"),
        "created_at": ("timestamp with time zone", "NO"), "updated_at": ("timestamp with time zone", "NO"),
    },
    "customer_profiles": {
        "customer_account_id": ("bigint", "NO"), "first_name": ("character varying", "NO"),
        "last_name": ("character varying", "NO"), "phone": ("character varying", "YES"),
        "row_version": ("bigint", "NO"), "created_at": ("timestamp with time zone", "NO"),
        "updated_at": ("timestamp with time zone", "NO"),
    },
    "customer_addresses": {
        "customer_address_id": ("bigint", "NO"), "customer_account_id": ("bigint", "NO"),
        "label": ("character varying", "NO"), "recipient_first_name": ("character varying", "NO"),
        "recipient_last_name": ("character varying", "NO"), "phone": ("character varying", "YES"),
        "address_line_1": ("character varying", "NO"), "address_line_2": ("character varying", "YES"),
        "city": ("character varying", "NO"), "province_region": ("character varying", "NO"),
        "postal_code": ("character varying", "NO"), "country_code": ("character", "NO"),
        "is_default": ("boolean", "NO"), "is_active": ("boolean", "NO"),
        "row_version": ("bigint", "NO"), "created_at": ("timestamp with time zone", "NO"),
        "updated_at": ("timestamp with time zone", "NO"),
    },
    "payment_methods": {
        "payment_method_id": ("bigint", "NO"), "customer_account_id": ("bigint", "NO"),
        "method_type": ("character varying", "NO"), "display_label": ("character varying", "NO"),
        "card_brand": ("character varying", "YES"), "card_last_four": ("character", "YES"),
        "is_default": ("boolean", "NO"), "is_active": ("boolean", "NO"),
        "row_version": ("bigint", "NO"), "created_at": ("timestamp with time zone", "NO"),
        "updated_at": ("timestamp with time zone", "NO"),
    },
    "product_catalog_details": {
        "product_id": ("bigint", "NO"), "description": ("text", "NO"),
        "current_price_usd": ("numeric", "NO"), "current_cogs_usd": ("numeric", "NO"),
        "image_url": ("text", "YES"), "is_available": ("boolean", "NO"),
        "updated_by_app_user_id": ("bigint", "NO"), "row_version": ("bigint", "NO"),
        "created_at": ("timestamp with time zone", "NO"), "updated_at": ("timestamp with time zone", "NO"),
    },
    "shopping_carts": {
        "shopping_cart_id": ("bigint", "NO"), "customer_account_id": ("bigint", "NO"),
        "cart_status": ("character varying", "NO"), "converted_order_id": ("bigint", "YES"),
        "row_version": ("bigint", "NO"), "created_at": ("timestamp with time zone", "NO"),
        "updated_at": ("timestamp with time zone", "NO"),
    },
    "cart_items": {
        "cart_item_id": ("bigint", "NO"), "shopping_cart_id": ("bigint", "NO"),
        "product_id": ("bigint", "NO"), "quantity": ("integer", "NO"),
        "unit_price_usd": ("numeric", "NO"), "row_version": ("bigint", "NO"),
        "created_at": ("timestamp with time zone", "NO"), "updated_at": ("timestamp with time zone", "NO"),
    },
    "order_shipping_addresses": {
        "order_id": ("bigint", "NO"), "customer_account_id": ("bigint", "NO"),
        "source_customer_address_id": ("bigint", "YES"),
        "recipient_first_name": ("character varying", "NO"), "recipient_last_name": ("character varying", "NO"),
        "phone": ("character varying", "YES"), "address_line_1": ("character varying", "NO"),
        "address_line_2": ("character varying", "YES"), "city": ("character varying", "NO"),
        "province_region": ("character varying", "NO"), "postal_code": ("character varying", "NO"),
        "country_code": ("character", "NO"), "row_version": ("bigint", "NO"),
        "created_at": ("timestamp with time zone", "NO"), "updated_at": ("timestamp with time zone", "NO"),
    },
    "order_payments": {
        "order_payment_id": ("bigint", "NO"), "order_id": ("bigint", "NO"),
        "customer_account_id": ("bigint", "NO"), "payment_method_id": ("bigint", "YES"),
        "method_type": ("character varying", "NO"), "payment_display_snapshot": ("character varying", "NO"),
        "payment_status": ("character varying", "NO"), "amount_usd": ("numeric", "NO"),
        "simulated_reference": ("character varying", "YES"), "processed_at": ("timestamp with time zone", "YES"),
        "row_version": ("bigint", "NO"), "created_at": ("timestamp with time zone", "NO"),
        "updated_at": ("timestamp with time zone", "NO"),
    },
    "refund_requests": {
        "refund_request_id": ("bigint", "NO"), "customer_account_id": ("bigint", "NO"),
        "order_id": ("bigint", "NO"), "order_item_id": ("bigint", "NO"),
        "reason": ("text", "NO"), "requested_amount_usd": ("numeric", "NO"),
        "request_status": ("character varying", "NO"), "resolution_note": ("text", "YES"),
        "reviewed_by_app_user_id": ("bigint", "YES"), "reviewed_at": ("timestamp with time zone", "YES"),
        "row_version": ("bigint", "NO"), "created_at": ("timestamp with time zone", "NO"),
        "updated_at": ("timestamp with time zone", "NO"),
    },
}

EXPECTED_CHECKS = {
    "ck_customer_accounts_dataset_user_id", "ck_customer_accounts_email_not_blank",
    "ck_customer_accounts_password_hash_not_blank", "ck_customer_accounts_failed_login_attempts",
    "ck_customer_accounts_token_version", "ck_customer_accounts_row_version",
    "ck_customer_accounts_reset_hash", "ck_customer_accounts_reset_pair",
    "ck_customer_profiles_first_name", "ck_customer_profiles_last_name",
    "ck_customer_profiles_phone", "ck_customer_profiles_row_version",
    "ck_customer_addresses_label", "ck_customer_addresses_recipient_first",
    "ck_customer_addresses_recipient_last", "ck_customer_addresses_phone",
    "ck_customer_addresses_line_1", "ck_customer_addresses_line_2",
    "ck_customer_addresses_city", "ck_customer_addresses_province",
    "ck_customer_addresses_postal", "ck_customer_addresses_country",
    "ck_customer_addresses_row_version", "ck_payment_methods_type",
    "ck_payment_methods_label", "ck_payment_methods_safe_card_metadata",
    "ck_payment_methods_row_version", "ck_product_catalog_details_price",
    "ck_product_catalog_details_cogs", "ck_product_catalog_details_image",
    "ck_product_catalog_details_row_version", "ck_products_record_origin",
    "ck_products_origin_context", "ck_orders_record_origin", "ck_orders_status",
    "ck_orders_origin_context", "ck_order_items_record_origin",
    "ck_order_items_origin_context", "ck_order_shipping_recipient_first",
    "ck_order_shipping_recipient_last", "ck_order_shipping_phone",
    "ck_order_shipping_line_1", "ck_order_shipping_line_2", "ck_order_shipping_city",
    "ck_order_shipping_province", "ck_order_shipping_postal", "ck_order_shipping_country",
    "ck_order_shipping_row_version", "ck_order_payments_method_type",
    "ck_order_payments_display", "ck_order_payments_status", "ck_order_payments_amount",
    "ck_order_payments_reference", "ck_order_payments_row_version",
    "ck_refund_requests_reason", "ck_refund_requests_amount", "ck_refund_requests_status",
    "ck_refund_requests_resolution", "ck_refund_requests_review_state",
    "ck_refund_requests_row_version", "ck_order_item_refunds_record_origin",
    "ck_order_item_refunds_origin_context", "ck_shopping_carts_status",
    "ck_shopping_carts_conversion", "ck_shopping_carts_row_version",
    "ck_cart_items_quantity", "ck_cart_items_unit_price", "ck_cart_items_row_version",
}

EXPECTED_UNIQUES = {
    "uq_customer_addresses_id_account", "uq_payment_methods_id_account",
    "uq_orders_id_origin", "uq_orders_id_customer", "uq_order_items_id_order",
    "order_payments_order_id_key", "uq_refund_requests_id_order_item",
    "shopping_carts_converted_order_id_key", "uq_cart_items_cart_product",
}

EXPECTED_INDEXES = {
    "uq_customer_accounts_email_lower", "uq_customer_accounts_dataset_user_id",
    "uq_customer_addresses_active_default", "uq_payment_methods_active_default",
    "uq_shopping_carts_active_customer", "uq_refund_requests_pending_customer_item",
    "idx_products_record_origin", "idx_orders_record_origin", "idx_orders_customer_status",
    "idx_order_items_record_origin", "idx_order_item_refunds_record_origin",
}

EXPECTED_TYPE_LIMITS = {
    ("customer_accounts", "email"): (254, None, None),
    ("customer_accounts", "password_reset_token_hash"): (64, None, None),
    ("customer_addresses", "country_code"): (2, None, None),
    ("payment_methods", "card_last_four"): (4, None, None),
    ("product_catalog_details", "current_price_usd"): (None, 12, 2),
    ("product_catalog_details", "current_cogs_usd"): (None, 12, 2),
    ("cart_items", "unit_price_usd"): (None, 12, 2),
    ("order_payments", "amount_usd"): (None, 12, 2),
    ("refund_requests", "requested_amount_usd"): (None, 12, 2),
}

EXPECTED_FK_DELETE = {
    "fk_customer_profiles_account": "r", "fk_customer_addresses_account": "r",
    "fk_payment_methods_account": "r", "fk_product_catalog_details_product": "r",
    "fk_product_catalog_details_updated_by": "r", "fk_orders_customer_account": "r",
    "fk_order_items_order_origin": "r", "fk_order_shipping_order_customer": "r",
    "fk_order_shipping_source_address": "r", "fk_order_payments_order_customer": "r",
    "fk_order_payments_method_customer": "r", "fk_refund_requests_order_customer": "r",
    "fk_refund_requests_order_item": "r", "fk_refund_requests_reviewer": "r",
    "fk_order_item_refunds_request_context": "r", "fk_shopping_carts_account": "r",
    "fk_shopping_carts_converted_order": "r", "fk_cart_items_cart": "c",
    "fk_cart_items_product": "r", "fk_products_created_by_app_user": "r",
    "fk_orders_created_by_app_user": "r", "fk_order_items_created_by_app_user": "r",
    "fk_order_item_refunds_created_by_app_user": "r",
}


class Verification:
    def __init__(self) -> None:
        self.failures: list[str] = []

    def check(self, label: str, condition: bool, detail: str = "") -> None:
        if condition:
            print(f"PASS: {label}")
        else:
            message = f"FAIL: {label}" + (f" -- {detail}" if detail else "")
            print(message)
            self.failures.append(message)


def view_uses_imported_origin(definition: str) -> bool:
    normalized = " ".join(definition.lower().replace("::text", "").split())
    return "record_origin = 'imported'" in normalized


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the cumulative migration-002 schema.")
    parser.add_argument(
        "--staging",
        action="store_true",
        help=f"Verify only the isolated {STAGING_DATABASE} database and staging snapshot.",
    )
    return parser.parse_args()


def relation_exists(cur, name: str, kind: str) -> bool:
    cur.execute(
        """SELECT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
           WHERE n.nspname='public' AND c.relname=%s AND c.relkind=%s)""",
        (name, kind),
    )
    return bool(cur.fetchone()[0])


def verify_columns(cur, check: Verification) -> None:
    for table, expected in EXPECTED_COLUMNS.items():
        cur.execute(
            """SELECT column_name, data_type, is_nullable FROM information_schema.columns
               WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position""",
            (table,),
        )
        observed = {row[0]: (row[1], row[2]) for row in cur.fetchall()}
        check.check(f"{table} columns/types/nullability", observed == expected, f"observed={observed}")

    altered = {
        "products": {"record_origin": ("character varying", "NO")},
        "orders": {
            "record_origin": ("character varying", "NO"), "customer_account_id": ("bigint", "YES"),
            "order_status": ("character varying", "YES"), "updated_at": ("timestamp with time zone", "NO"),
            "website_session_id": ("bigint", "YES"), "user_id": ("bigint", "YES"),
        },
        "order_items": {"record_origin": ("character varying", "NO")},
        "order_item_refunds": {
            "record_origin": ("character varying", "NO"), "refund_request_id": ("bigint", "YES")
        },
    }
    for table, expected in altered.items():
        cur.execute(
            """SELECT column_name, data_type, is_nullable FROM information_schema.columns
               WHERE table_schema='public' AND table_name=%s AND column_name=ANY(%s)""",
            (table, list(expected)),
        )
        observed = {row[0]: (row[1], row[2]) for row in cur.fetchall()}
        check.check(f"{table} migration-002 columns", observed == expected, f"observed={observed}")

    cur.execute(
        """SELECT table_name, column_name, character_maximum_length,
                  numeric_precision, numeric_scale
           FROM information_schema.columns
           WHERE table_schema='public'"""
    )
    observed_limits = {(row[0], row[1]): (row[2], row[3], row[4]) for row in cur.fetchall()}
    wrong_limits = {
        key: observed_limits.get(key) for key, expected in EXPECTED_TYPE_LIMITS.items()
        if observed_limits.get(key) != expected
    }
    check.check("important character and monetary type limits are exact", not wrong_limits,
                f"wrong={wrong_limits}")


def verify_constraints_and_indexes(cur, check: Verification) -> None:
    cur.execute(
        """SELECT conname, contype, confdeltype, convalidated
           FROM pg_constraint con JOIN pg_namespace n ON n.oid=con.connamespace
           WHERE n.nspname='public'"""
    )
    rows = cur.fetchall()
    constraints = {row[0]: row for row in rows}
    missing = sorted(EXPECTED_CHECKS - constraints.keys())
    invalid = sorted(name for name in EXPECTED_CHECKS if name in constraints and not constraints[name][3])
    wrong_type = sorted(name for name in EXPECTED_CHECKS if name in constraints and constraints[name][1] != "c")
    check.check("all migration-002 CHECK constraints exist and are validated",
                not missing and not invalid and not wrong_type,
                f"missing={missing}, invalid={invalid}")

    bad_uniques = {
        name: constraints.get(name) for name in EXPECTED_UNIQUES
        if name not in constraints or constraints[name][1] != "u" or not constraints[name][3]
    }
    check.check("all migration-002 UNIQUE constraints exist and are valid", not bad_uniques,
                f"wrong={bad_uniques}")

    wrong_delete = {
        name: constraints.get(name)
        for name, action in EXPECTED_FK_DELETE.items()
        if name not in constraints or constraints[name][1] != "f"
        or constraints[name][2] != action or not constraints[name][3]
    }
    check.check("foreign keys have approved ON DELETE behavior", not wrong_delete, f"wrong={wrong_delete}")

    cur.execute("SELECT indexname FROM pg_indexes WHERE schemaname='public'")
    indexes = {row[0] for row in cur.fetchall()}
    check.check("required unique/supporting indexes exist", EXPECTED_INDEXES <= indexes,
                f"missing={sorted(EXPECTED_INDEXES - indexes)}")

    cur.execute(
        """SELECT c.relname, con.conname FROM pg_constraint con
           JOIN pg_class c ON c.oid=con.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace
           WHERE n.nspname='public' AND con.contype='p' AND c.relname=ANY(%s)""",
        (list(NEW_TABLES),),
    )
    pk_tables = {row[0] for row in cur.fetchall()}
    check.check("every new table has a primary key", pk_tables == set(NEW_TABLES),
                f"missing={sorted(set(NEW_TABLES)-pk_tables)}")

    identity_columns = {
        "customer_accounts": "customer_account_id",
        "customer_addresses": "customer_address_id",
        "payment_methods": "payment_method_id",
        "shopping_carts": "shopping_cart_id",
        "cart_items": "cart_item_id",
        "order_payments": "order_payment_id",
        "refund_requests": "refund_request_id",
    }
    cur.execute(
        """SELECT table_name, column_name FROM information_schema.columns
           WHERE table_schema='public' AND is_identity='YES'"""
    )
    identities = {row[0]: row[1] for row in cur.fetchall()}
    check.check("new surrogate primary keys are generated identities",
                all(identities.get(table) == column for table, column in identity_columns.items()),
                f"observed={identities}")

    cur.execute(
        """SELECT trigger_name, event_object_table FROM information_schema.triggers
           WHERE trigger_schema='public' AND trigger_name=ANY(%s)""",
        (["trg_products_record_origin", "trg_orders_record_origin",
          "trg_order_items_record_origin", "trg_order_item_refunds_record_origin"],),
    )
    triggers = {row[0]: row[1] for row in cur.fetchall()}
    expected_triggers = {
        "trg_products_record_origin": "products", "trg_orders_record_origin": "orders",
        "trg_order_items_record_origin": "order_items",
        "trg_order_item_refunds_record_origin": "order_item_refunds",
    }
    check.check("legacy insert compatibility triggers exist", triggers == expected_triggers,
                f"observed={triggers}")


def verify_original_relationships(cur, check: Verification) -> None:
    expected_fks = {
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
    observed = {tuple(row) for row in cur.fetchall()}
    check.check("all original Toy Store foreign keys remain intact", expected_fks <= observed,
                f"missing={sorted(expected_fks-observed)}")

    cur.execute(
        """SELECT c.relname FROM pg_constraint con JOIN pg_class c ON c.oid=con.conrelid
           JOIN pg_namespace n ON n.oid=c.relnamespace
           WHERE n.nspname='public' AND con.contype='p' AND c.relname=ANY(%s)""",
        (["website_sessions", "website_pageviews", "products", "orders", "order_items", "order_item_refunds"],),
    )
    pk_tables = {row[0] for row in cur.fetchall()}
    expected_pk_tables = {"website_sessions", "website_pageviews", "products", "orders", "order_items", "order_item_refunds"}
    check.check("all original Toy Store primary keys remain intact", pk_tables == expected_pk_tables,
                f"missing={sorted(expected_pk_tables-pk_tables)}")


def verify_origin_rules(cur, check: Verification) -> None:
    queries = {
        "products satisfy origin/creator rules": """SELECT COUNT(*) FROM public.products WHERE
            NOT ((record_origin='imported' AND created_by_app_user_id IS NULL) OR
                 (record_origin='staff' AND created_by_app_user_id IS NOT NULL))""",
        "orders satisfy origin/context/status rules": """SELECT COUNT(*) FROM public.orders WHERE NOT (
            (record_origin='imported' AND created_by_app_user_id IS NULL AND customer_account_id IS NULL
             AND website_session_id IS NOT NULL AND user_id IS NOT NULL AND order_status IS NULL) OR
            (record_origin='staff' AND created_by_app_user_id IS NOT NULL AND customer_account_id IS NULL
             AND website_session_id IS NOT NULL AND user_id IS NOT NULL AND order_status IS NOT NULL) OR
            (record_origin='customer' AND customer_account_id IS NOT NULL
             AND website_session_id IS NULL AND user_id IS NULL AND order_status IS NOT NULL))""",
        "order items match parent order origin": """SELECT COUNT(*) FROM public.order_items oi
            JOIN public.orders o ON o.order_id=oi.order_id WHERE oi.record_origin<>o.record_origin""",
        "refunds satisfy origin/actor/request rules": """SELECT COUNT(*) FROM public.order_item_refunds WHERE NOT (
            (record_origin='imported' AND created_by_app_user_id IS NULL AND refund_request_id IS NULL) OR
            (record_origin='staff' AND created_by_app_user_id IS NOT NULL AND refund_request_id IS NULL) OR
            (record_origin='customer' AND created_by_app_user_id IS NOT NULL AND refund_request_id IS NOT NULL))""",
        "customer refunds match request order/item": """SELECT COUNT(*) FROM public.order_item_refunds r
            JOIN public.refund_requests q ON q.refund_request_id=r.refund_request_id
            WHERE r.order_id<>q.order_id OR r.order_item_id<>q.order_item_id""",
    }
    for label, query in queries.items():
        cur.execute(query)
        violations = int(cur.fetchone()[0])
        check.check(label, violations == 0, f"violations={violations}")


def verify_canonical_boundary(cur, check: Verification, snapshot: dict[str, Any]) -> None:
    snapshot_counts = snapshot["preflight"]["canonical_counts"]
    for view, columns in CANONICAL_VIEWS.items():
        cur.execute(
            """SELECT column_name FROM information_schema.columns
               WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position""",
            (view,),
        )
        observed_columns = tuple(row[0] for row in cur.fetchall())
        cur.execute("SELECT pg_get_viewdef(%s::regclass, TRUE)", (f"public.{view}",))
        definition = cur.fetchone()[0]
        cur.execute(f'SELECT COUNT(*) FROM public."{view}"')
        count = int(cur.fetchone()[0])
        expected_count = EXPECTED_CANONICAL_COUNTS[view]
        check.check(f"{view} keeps exact columns and imported-only predicate",
                    observed_columns == columns and view_uses_imported_origin(definition),
                    f"columns={observed_columns}")
        check.check(f"{view} count unchanged", count == expected_count == snapshot_counts.get(view),
                    f"expected={expected_count}, snapshot={snapshot_counts.get(view)}, actual={count}")

    for table, view in zip(BUSINESS_TABLES, CANONICAL_VIEWS):
        cur.execute(f"SELECT COUNT(*) FROM public.{table} WHERE record_origin='imported'")
        imported = int(cur.fetchone()[0])
        cur.execute(f'SELECT COUNT(*) FROM public."{view}"')
        view_count = int(cur.fetchone()[0])
        check.check(f"{view} includes all and only imported {table} rows", imported == view_count,
                    f"imported={imported}, view={view_count}")


def verify_historical_summary(cur, check: Verification) -> None:
    expected_columns = (
        "dataset_user_id", "session_count", "repeat_visitor", "order_count",
        "total_spent", "refund_total", "last_visit", "latest_utm_source", "latest_device_type",
    )
    cur.execute("""SELECT column_name FROM information_schema.columns WHERE table_schema='public'
                   AND table_name='historical_customer_summary' ORDER BY ordinal_position""")
    columns = tuple(row[0] for row in cur.fetchall())
    cur.execute("SELECT pg_get_viewdef('public.historical_customer_summary'::regclass, TRUE)")
    definition = " ".join(cur.fetchone()[0].lower().split())
    safe_definition = (
        "canonical_orders" in definition and "canonical_order_item_refunds" in definition
        and "customer_accounts" not in definition and "customer_profiles" not in definition
    )
    check.check("historical_customer_summary is deidentified and canonical-only",
                columns == expected_columns and safe_definition, f"columns={columns}")

    cur.execute(
        """SELECT COUNT(*), COUNT(DISTINCT dataset_user_id), COALESCE(SUM(session_count),0),
                  COALESCE(SUM(order_count),0), COALESCE(SUM(total_spent),0),
                  COALESCE(SUM(refund_total),0)
           FROM public.historical_customer_summary"""
    )
    row_count, distinct_users, sessions, orders, spent, refunds = cur.fetchone()
    cur.execute("SELECT COUNT(*) FROM public.website_sessions")
    expected_sessions = int(cur.fetchone()[0])
    cur.execute("SELECT COUNT(*), COALESCE(SUM(price_usd),0) FROM public.canonical_orders")
    expected_orders, expected_spent = cur.fetchone()
    cur.execute("SELECT COALESCE(SUM(refund_amount_usd),0) FROM public.canonical_order_item_refunds")
    expected_refunds = cur.fetchone()[0]
    check.check("historical summary has one row per dataset user", row_count == distinct_users)
    check.check("historical summary aggregates without row multiplication",
                int(sessions) == expected_sessions and int(orders) == int(expected_orders)
                and spent == expected_spent and refunds == expected_refunds,
                f"sessions={sessions}, orders={orders}, spent={spent}, refunds={refunds}")


def verify_snapshot_safety(conn, check: Verification, snapshot: dict[str, Any]) -> None:
    after_session2 = capture_session2_fingerprint(conn)
    check.check("Session 2 support-table fingerprint unchanged",
                after_session2 == snapshot["session2_fingerprint"])
    after_hashes = capture_evidence_hashes()
    check.check("known Session 1/2 evidence hashes unchanged",
                after_hashes == snapshot["evidence_sha256"])


def main() -> int:
    args = parse_args()
    snapshot_file = (
        MIGRATION_002_STAGING_SNAPSHOT_FILE if args.staging else MIGRATION_002_SNAPSHOT_FILE
    )
    expected_database = STAGING_DATABASE if args.staging else "retailmetrics"
    if not snapshot_file.is_file():
        print(f"ERROR: pre-migration snapshot is missing: {snapshot_file}", file=sys.stderr)
        return 2
    try:
        snapshot = load_snapshot(snapshot_file)
        settings = connection_settings()
    except (OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if settings["dbname"] != expected_database:
        print(
            f"ERROR: {'staging' if args.staging else 'production'} verification requires "
            f"PGDATABASE={expected_database}; observed {settings['dbname']!r}.",
            file=sys.stderr,
        )
        return 2

    print("RetailMetricsWeb migration-002 verification")
    print(f"Target: {public_connection_summary(settings)}")
    print("Verification transaction: READ ONLY")
    check = Verification()
    conn = None
    try:
        conn = psycopg2.connect(**settings)
        conn.set_session(isolation_level="REPEATABLE READ", readonly=True, autocommit=False)
        with conn.cursor() as cur:
            cur.execute("SELECT current_database()")
            check.check("connected to the explicitly selected database",
                        cur.fetchone()[0] == expected_database)
            for table in NEW_TABLES:
                check.check(f"public.{table} exists", relation_exists(cur, table, "r"))
            verify_columns(cur, check)
            verify_constraints_and_indexes(cur, check)
            verify_original_relationships(cur, check)
            verify_origin_rules(cur, check)
            verify_canonical_boundary(cur, check, snapshot)
            check.check("public.historical_customer_summary exists",
                        relation_exists(cur, "historical_customer_summary", "v"))
            verify_historical_summary(cur, check)
            cur.execute("SELECT to_regclass('public.uq_orders_website_session_id') IS NOT NULL")
            check.check("one-order-per-non-null-website-session index remains", bool(cur.fetchone()[0]))
        verify_snapshot_safety(conn, check, snapshot)
        conn.rollback()
    except psycopg2.Error as exc:
        if conn is not None and not conn.closed:
            conn.rollback()
        print_postgresql_error(exc)
        return 2
    except (OSError, ValueError, KeyError, TypeError) as exc:
        if conn is not None and not conn.closed:
            conn.rollback()
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    finally:
        if conn is not None:
            conn.close()

    if check.failures:
        print(f"\nOVERALL: FAIL ({len(check.failures)} failed checks)")
        return 1
    print("\nOVERALL: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
