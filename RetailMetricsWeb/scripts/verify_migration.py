from __future__ import annotations

import sys

import psycopg2

from migration_support import (
    SESSION2_SNAPSHOT_FILE,
    capture_session2_fingerprint,
    connection_settings,
    load_session2_snapshot,
    print_postgresql_error,
    public_connection_summary,
)


BUSINESS_TABLES = (
    "products",
    "orders",
    "order_items",
    "order_item_refunds",
)

CREATOR_FOREIGN_KEYS = {
    "fk_products_created_by_app_user": "products",
    "fk_orders_created_by_app_user": "orders",
    "fk_order_items_created_by_app_user": "order_items",
    "fk_order_item_refunds_created_by_app_user": "order_item_refunds",
}

PRIMARY_KEY_DEFAULTS = {
    "products": "product_id",
    "orders": "order_id",
    "order_items": "order_item_id",
    "order_item_refunds": "order_item_refund_id",
}

CANONICAL_VIEWS = {
    "canonical_products": (
        "product_id",
        "created_at",
        "product_name",
    ),
    "canonical_orders": (
        "order_id",
        "created_at",
        "website_session_id",
        "user_id",
        "primary_product_id",
        "items_purchased",
        "price_usd",
        "cogs_usd",
    ),
    "canonical_order_items": (
        "order_item_id",
        "created_at",
        "order_id",
        "product_id",
        "is_primary_item",
        "price_usd",
        "cogs_usd",
    ),
    "canonical_order_item_refunds": (
        "order_item_refund_id",
        "created_at",
        "order_item_id",
        "order_id",
        "refund_amount_usd",
    ),
}

CANONICAL_COUNTS = {
    "canonical_products": 4,
    "canonical_orders": 32_313,
    "canonical_order_items": 40_025,
    "canonical_order_item_refunds": 1_731,
}

ORIGINAL_PRIMARY_KEYS = {
    ("website_sessions", "website_session_id"),
    ("website_pageviews", "website_pageview_id"),
    ("products", "product_id"),
    ("orders", "order_id"),
    ("order_items", "order_item_id"),
    ("order_item_refunds", "order_item_refund_id"),
}

ORIGINAL_FOREIGN_KEYS = {
    ("website_pageviews", "website_session_id", "website_sessions", "website_session_id"),
    ("orders", "website_session_id", "website_sessions", "website_session_id"),
    ("orders", "primary_product_id", "products", "product_id"),
    ("order_items", "order_id", "orders", "order_id"),
    ("order_items", "product_id", "products", "product_id"),
    ("order_item_refunds", "order_item_id", "order_items", "order_item_id"),
    ("order_item_refunds", "order_id", "orders", "order_id"),
}


class Verification:
    def __init__(self) -> None:
        self.failures: list[str] = []

    def check(self, label: str, condition: bool, detail: str = "") -> None:
        if condition:
            print(f"PASS: {label}")
            return
        message = f"FAIL: {label}"
        if detail:
            message += f" -- {detail}"
        print(message)
        self.failures.append(message)


def relation_exists(cur, relation_name: str, relkind: str) -> bool:
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relname = %s
              AND c.relkind = %s
        )
        """,
        (relation_name, relkind),
    )
    return bool(cur.fetchone()[0])


def verify_app_users(cur, verification: Verification) -> None:
    verification.check(
        "public.app_users exists",
        relation_exists(cur, "app_users", "r"),
    )


def verify_business_columns(cur, verification: Verification) -> None:
    for table_name in BUSINESS_TABLES:
        cur.execute(
            """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
              AND column_name IN ('created_by_app_user_id', 'row_version')
            """,
            (table_name,),
        )
        columns = {row[0]: row[1:] for row in cur.fetchall()}
        creator = columns.get("created_by_app_user_id")
        version = columns.get("row_version")
        version_default = "" if version is None or version[2] is None else (
            version[2].replace(" ", "").strip("()")
        )
        valid = (
            creator is not None
            and creator[0] == "bigint"
            and creator[1] == "YES"
            and version is not None
            and version[0] == "bigint"
            and version[1] == "NO"
            and version_default in {"1", "1::bigint", "'1'::bigint"}
        )
        verification.check(
            f"public.{table_name} has valid creator and row-version columns",
            valid,
            f"observed={columns}",
        )


def verify_creator_foreign_keys(cur, verification: Verification) -> None:
    cur.execute(
        """
        SELECT
            con.conname,
            child.relname,
            parent.relname,
            child_col.attname,
            parent_col.attname,
            con.confdeltype,
            con.convalidated
        FROM pg_constraint con
        JOIN pg_class child ON child.oid = con.conrelid
        JOIN pg_namespace child_ns ON child_ns.oid = child.relnamespace
        JOIN pg_class parent ON parent.oid = con.confrelid
        JOIN pg_namespace parent_ns ON parent_ns.oid = parent.relnamespace
        JOIN LATERAL generate_subscripts(con.conkey, 1)
          AS key_position(position) ON TRUE
        JOIN pg_attribute child_col
          ON child_col.attrelid = child.oid
         AND child_col.attnum = con.conkey[key_position.position]
        JOIN pg_attribute parent_col
          ON parent_col.attrelid = parent.oid
         AND parent_col.attnum = con.confkey[key_position.position]
        WHERE child_ns.nspname = 'public'
          AND parent_ns.nspname = 'public'
          AND con.contype = 'f'
          AND con.conname = ANY(%s)
        """,
        (list(CREATOR_FOREIGN_KEYS),),
    )
    observed = {row[0]: row[1:] for row in cur.fetchall()}
    for constraint_name, table_name in CREATOR_FOREIGN_KEYS.items():
        expected = (
            table_name,
            "app_users",
            "created_by_app_user_id",
            "app_user_id",
            "n",
            True,
        )
        verification.check(
            f"{constraint_name} is valid and uses ON DELETE SET NULL",
            observed.get(constraint_name) == expected,
            f"observed={observed.get(constraint_name)}",
        )


def verify_unique_order_session_index(cur, verification: Verification) -> None:
    cur.execute(
        """
        SELECT
            idx.relname,
            tbl.relname,
            i.indisunique,
            i.indisvalid,
            pg_get_indexdef(i.indexrelid)
        FROM pg_index i
        JOIN pg_class idx ON idx.oid = i.indexrelid
        JOIN pg_class tbl ON tbl.oid = i.indrelid
        JOIN pg_namespace n ON n.oid = tbl.relnamespace
        WHERE n.nspname = 'public'
          AND idx.relname = 'uq_orders_website_session_id'
        """
    )
    row = cur.fetchone()
    valid = bool(
        row
        and row[1] == "orders"
        and row[2] is True
        and row[3] is True
        and "(website_session_id)" in row[4].replace(" ", "")
    )
    verification.check(
        "uq_orders_website_session_id is a valid unique orders index",
        valid,
        f"observed={row}",
    )


def verify_shared_sequence_and_defaults(cur, verification: Verification) -> None:
    sequence_exists = relation_exists(
        cur, "retailmetrics_app_entity_id_seq", "S"
    )
    verification.check(
        "public.retailmetrics_app_entity_id_seq exists",
        sequence_exists,
    )

    if sequence_exists:
        cur.execute(
            """
            SELECT GREATEST(
                COALESCE((SELECT MAX(product_id) FROM public.products), 0),
                COALESCE((SELECT MAX(order_id) FROM public.orders), 0),
                COALESCE((SELECT MAX(order_item_id) FROM public.order_items), 0),
                COALESCE((
                    SELECT MAX(order_item_refund_id)
                    FROM public.order_item_refunds
                ), 0)
            )
            """
        )
        maximum_business_id = int(cur.fetchone()[0])
        cur.execute(
            """
            SELECT last_value, is_called
            FROM public.retailmetrics_app_entity_id_seq
            """
        )
        last_value, is_called = cur.fetchone()
        next_sequence_value = int(last_value) + (1 if is_called else 0)
        verification.check(
            "shared sequence next value is above every current business ID",
            next_sequence_value > maximum_business_id,
            (
                f"next={next_sequence_value}, "
                f"maximum_business_id={maximum_business_id}"
            ),
        )

    for table_name, column_name in PRIMARY_KEY_DEFAULTS.items():
        cur.execute(
            """
            SELECT pg_get_expr(defaults.adbin, defaults.adrelid)
            FROM pg_attrdef defaults
            JOIN pg_class table_rel ON table_rel.oid = defaults.adrelid
            JOIN pg_namespace n ON n.oid = table_rel.relnamespace
            JOIN pg_attribute column_attr
              ON column_attr.attrelid = table_rel.oid
             AND column_attr.attnum = defaults.adnum
            WHERE n.nspname = 'public'
              AND table_rel.relname = %s
              AND column_attr.attname = %s
            """,
            (table_name, column_name),
        )
        row = cur.fetchone()
        expression = row[0] if row else ""
        valid = (
            "nextval(" in expression
            and "retailmetrics_app_entity_id_seq" in expression
        )
        verification.check(
            f"public.{table_name}.{column_name} uses the shared sequence",
            valid,
            f"default={expression or None}",
        )


def verify_canonical_views(cur, verification: Verification) -> None:
    for view_name, expected_columns in CANONICAL_VIEWS.items():
        exists = relation_exists(cur, view_name, "v")
        if not exists:
            verification.check(
                f"public.{view_name} exists",
                False,
                "view is missing",
            )
            continue

        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
            """,
            (view_name,),
        )
        columns = tuple(row[0] for row in cur.fetchall())

        cur.execute(
            """
            SELECT is_updatable
            FROM information_schema.views
            WHERE table_schema = 'public' AND table_name = %s
            """,
            (view_name,),
        )
        view_row = cur.fetchone()

        cur.execute(
            """
            SELECT pg_get_viewdef(%s::regclass, TRUE)
            """,
            (f"public.{view_name}",),
        )
        definition = " ".join(cur.fetchone()[0].lower().split())
        valid = (
            relation_exists(cur, view_name, "v")
            and columns == expected_columns
            and view_row is not None
            and view_row[0] == "NO"
            and "created_by_app_user_id is null" in definition
        )
        verification.check(
            f"public.{view_name} is read-only, filtered, and has the CSV shape",
            valid,
            f"columns={columns}, is_updatable={view_row}",
        )


def verify_canonical_counts(cur, verification: Verification) -> None:
    for view_name, expected_count in CANONICAL_COUNTS.items():
        if not relation_exists(cur, view_name, "v"):
            verification.check(
                f"public.{view_name} contains {expected_count:,} imported rows",
                False,
                "view is missing",
            )
            continue
        cur.execute(f'SELECT COUNT(*) FROM public."{view_name}"')
        actual_count = int(cur.fetchone()[0])
        verification.check(
            f"public.{view_name} contains {expected_count:,} imported rows",
            actual_count == expected_count,
            f"actual={actual_count:,}",
        )


def verify_original_relationships(cur, verification: Verification) -> None:
    cur.execute(
        """
        SELECT
            child.relname,
            child_col.attname,
            parent.relname,
            parent_col.attname
        FROM pg_constraint con
        JOIN pg_class child ON child.oid = con.conrelid
        JOIN pg_namespace n ON n.oid = child.relnamespace
        JOIN pg_class parent ON parent.oid = con.confrelid
        JOIN pg_namespace parent_ns ON parent_ns.oid = parent.relnamespace
        JOIN LATERAL generate_subscripts(con.conkey, 1)
          AS key_position(position) ON TRUE
        JOIN pg_attribute child_col
          ON child_col.attrelid = child.oid
         AND child_col.attnum = con.conkey[key_position.position]
        JOIN pg_attribute parent_col
          ON parent_col.attrelid = parent.oid
         AND parent_col.attnum = con.confkey[key_position.position]
        WHERE n.nspname = 'public'
          AND parent_ns.nspname = 'public'
          AND con.contype = 'f'
          AND con.convalidated
          AND child.relname = ANY(%s)
        """,
        (
            [
                "website_pageviews",
                "orders",
                "order_items",
                "order_item_refunds",
            ],
        ),
    )
    observed_foreign_keys = {tuple(row) for row in cur.fetchall()}
    missing_foreign_keys = ORIGINAL_FOREIGN_KEYS - observed_foreign_keys
    verification.check(
        "all original Toy Store foreign-key relationships remain intact",
        not missing_foreign_keys,
        f"missing={sorted(missing_foreign_keys)}",
    )

    cur.execute(
        """
        SELECT table_rel.relname, column_attr.attname
        FROM pg_constraint con
        JOIN pg_class table_rel ON table_rel.oid = con.conrelid
        JOIN pg_namespace n ON n.oid = table_rel.relnamespace
        JOIN LATERAL unnest(con.conkey) AS key_column(attnum) ON TRUE
        JOIN pg_attribute column_attr
          ON column_attr.attrelid = table_rel.oid
         AND column_attr.attnum = key_column.attnum
        WHERE n.nspname = 'public'
          AND con.contype = 'p'
          AND table_rel.relname = ANY(%s)
        """,
        ([table for table, _ in ORIGINAL_PRIMARY_KEYS],),
    )
    observed_primary_keys = {tuple(row) for row in cur.fetchall()}
    missing_primary_keys = ORIGINAL_PRIMARY_KEYS - observed_primary_keys
    verification.check(
        "all six original Toy Store primary keys remain intact",
        not missing_primary_keys,
        f"missing={sorted(missing_primary_keys)}",
    )


def verify_session2_unchanged(conn, verification: Verification) -> None:
    if not SESSION2_SNAPSHOT_FILE.is_file():
        verification.check(
            "Session 2 pre-migration snapshot is available",
            False,
            f"missing={SESSION2_SNAPSHOT_FILE}",
        )
        return

    document = load_session2_snapshot()
    before = document["fingerprint"]
    after = capture_session2_fingerprint(conn)
    changed_components = sorted(
        key
        for key in set(before) | set(after)
        if before.get(key) != after.get(key)
    )
    verification.check(
        "Session 2 support tables, definitions, indexes, constraints, and row counts are unchanged",
        before == after,
        (
            f"changed components={changed_components}"
            if changed_components
            else ""
        ),
    )


def main() -> int:
    settings = connection_settings()
    print("RetailMetricsWeb post-migration verification")
    print(f"Target: {public_connection_summary(settings)}")
    print("Verification transaction: READ ONLY")

    verification = Verification()
    conn = None
    try:
        conn = psycopg2.connect(**settings)
        conn.set_session(readonly=True, autocommit=False)
        with conn.cursor() as cur:
            verify_app_users(cur, verification)
            verify_business_columns(cur, verification)
            verify_creator_foreign_keys(cur, verification)
            verify_unique_order_session_index(cur, verification)
            verify_shared_sequence_and_defaults(cur, verification)
            verify_canonical_views(cur, verification)
            verify_canonical_counts(cur, verification)
            verify_original_relationships(cur, verification)
        verify_session2_unchanged(conn, verification)
        conn.rollback()
    except psycopg2.Error as exc:
        if conn is not None and not conn.closed:
            conn.rollback()
        print_postgresql_error(exc)
        return 2
    except (OSError, ValueError, KeyError) as exc:
        if conn is not None and not conn.closed:
            conn.rollback()
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    finally:
        if conn is not None:
            conn.close()

    if verification.failures:
        print(f"\nOVERALL: FAIL ({len(verification.failures)} failed checks)")
        return 1

    print("\nOVERALL: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
