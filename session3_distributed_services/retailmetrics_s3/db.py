from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from typing import Any, Iterator, Sequence

import psycopg2
from psycopg2.extensions import connection as PgConnection

from .config import Settings
from .models import datetime_to_iso, decimal_to_cents


READ_PREFIXES = ("SELECT", "WITH", "SHOW", "EXPLAIN")


def _assert_select(sql: str) -> None:
    statement = sql.lstrip().upper()
    if not statement.startswith(READ_PREFIXES):
        raise ValueError("Session 3 repository permits read-only SQL only")


@contextmanager
def read_only_connection(cfg: Settings) -> Iterator[PgConnection]:
    conn = psycopg2.connect(
        host=cfg.pg_host,
        port=cfg.pg_port,
        dbname=cfg.pg_database,
        user=cfg.pg_user,
        password=cfg.pg_password,
        application_name="retailmetrics_session3_readonly",
    )
    conn.set_session(readonly=True, autocommit=False, isolation_level="REPEATABLE READ")
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW transaction_read_only")
            if cur.fetchone()[0] != "on":
                raise RuntimeError("PostgreSQL connection is not read-only")
        yield conn
    finally:
        conn.rollback()
        conn.close()


class CanonicalRepository:
    def __init__(self, cfg: Settings):
        self.cfg = cfg

    def _all(self, sql: str, params: Sequence[Any] = ()) -> list[tuple[Any, ...]]:
        _assert_select(sql)
        with read_only_connection(self.cfg) as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())

    def source_counts(self) -> dict[str, int]:
        rows = self._all(
            """
            SELECT 'website_sessions', COUNT(*) FROM public.website_sessions
            UNION ALL SELECT 'website_pageviews', COUNT(*) FROM public.website_pageviews
            UNION ALL SELECT 'products', COUNT(*) FROM public.canonical_products
            UNION ALL SELECT 'orders', COUNT(*) FROM public.canonical_orders
            UNION ALL SELECT 'order_items', COUNT(*) FROM public.canonical_order_items
            UNION ALL SELECT 'order_item_refunds', COUNT(*) FROM public.canonical_order_item_refunds
            """
        )
        return {str(name): int(count) for name, count in rows}

    def safety_fingerprint(self) -> dict[str, int]:
        tables = (
            "app_users", "products", "orders", "order_items", "order_item_refunds",
            "retailmetrics_event_log", "retailmetrics_consumer_offsets",
            "retailmetrics_consumer_partition_offsets", "retailmetrics_conversion_audit",
            "retailmetrics_refund_projection", "retailmetrics_session_projection",
            "retailmetrics_failure_audit", "retailmetrics_stream_runs",
        )
        result: dict[str, int] = {}
        with read_only_connection(self.cfg) as conn, conn.cursor() as cur:
            for table in tables:
                cur.execute("SELECT to_regclass(%s)", (f"public.{table}",))
                if cur.fetchone()[0] is None:
                    result[table] = -1
                    continue
                cur.execute(f'SELECT COUNT(*) FROM public."{table}"')
                result[table] = int(cur.fetchone()[0])
        result.update({f"canonical_{k}": v for k, v in self.source_counts().items()})
        return result

    def products(self) -> list[dict[str, Any]]:
        rows = self._all(
            "SELECT product_id, created_at, product_name FROM public.canonical_products ORDER BY product_id"
        )
        return [
            {"product_id": int(i), "created_at": datetime_to_iso(t), "product_name": n}
            for i, t, n in rows
        ]

    def orders(self, limit: int = 5000) -> list[dict[str, Any]]:
        rows = self._all(
            """
            SELECT order_id, created_at, website_session_id, user_id,
                   primary_product_id, items_purchased, price_usd, cogs_usd
            FROM public.canonical_orders
            ORDER BY order_id
            LIMIT %s
            """,
            (limit,),
        )
        return [
            {
                "order_id": int(r[0]), "created_at": datetime_to_iso(r[1]),
                "website_session_id": int(r[2]), "user_id": int(r[3]),
                "primary_product_id": None if r[4] is None else int(r[4]),
                "items_purchased": int(r[5]),
                "price_cents": decimal_to_cents(r[6]),
                "cogs_cents": decimal_to_cents(r[7]),
            }
            for r in rows
        ]

    def order_items(self, limit: int = 5000) -> list[dict[str, Any]]:
        rows = self._all(
            """
            SELECT order_item_id, created_at, order_id, product_id,
                   is_primary_item, price_usd, cogs_usd
            FROM public.canonical_order_items ORDER BY order_item_id LIMIT %s
            """,
            (limit,),
        )
        return [
            {
                "order_item_id": int(r[0]), "created_at": datetime_to_iso(r[1]),
                "order_id": int(r[2]), "product_id": int(r[3]),
                "is_primary_item": None if r[4] is None else int(r[4]),
                "price_cents": decimal_to_cents(r[5]),
                "cogs_cents": decimal_to_cents(r[6]),
            }
            for r in rows
        ]

    def refunds(self) -> list[dict[str, Any]]:
        rows = self._all(
            """
            SELECT order_item_refund_id, created_at, order_item_id, order_id,
                   refund_amount_usd
            FROM public.canonical_order_item_refunds ORDER BY order_item_refund_id
            """
        )
        return [
            {
                "refund_id": int(r[0]), "created_at": datetime_to_iso(r[1]),
                "order_item_id": int(r[2]), "order_id": int(r[3]),
                "refund_amount_cents": decimal_to_cents(r[4]),
            }
            for r in rows
        ]

    def sessions(self, limit: int = 5000) -> list[dict[str, Any]]:
        rows = self._all(
            """
            SELECT website_session_id, created_at, user_id, is_repeat_session,
                   utm_source, utm_campaign, utm_content, device_type, http_referer
            FROM public.website_sessions ORDER BY website_session_id LIMIT %s
            """,
            (limit,),
        )
        keys = (
            "website_session_id", "created_at", "user_id", "is_repeat_session",
            "utm_source", "utm_campaign", "utm_content", "device_type", "http_referer",
        )
        result = []
        for row in rows:
            item = dict(zip(keys, row))
            item["website_session_id"] = int(item["website_session_id"])
            item["user_id"] = int(item["user_id"])
            item["created_at"] = datetime_to_iso(item["created_at"])
            if item["is_repeat_session"] is not None:
                item["is_repeat_session"] = int(item["is_repeat_session"])
            result.append(item)
        return result

    def session_metrics(self) -> list[dict[str, Any]]:
        rows = self._all(
            """
            WITH p AS (
                SELECT website_session_id,
                       COUNT(*) AS pageview_count,
                       EXTRACT(EPOCH FROM (MAX(created_at) - MIN(created_at))) AS duration
                FROM public.website_pageviews
                GROUP BY website_session_id
            )
            SELECT p.website_session_id, p.pageview_count, p.duration,
                   CASE WHEN o.order_id IS NULL THEN 0 ELSE 1 END AS converted,
                   COALESCE(o.price_usd, 0),
                   COALESCE(o.price_usd - o.cogs_usd, 0)
            FROM p
            LEFT JOIN public.canonical_orders o USING (website_session_id)
            ORDER BY p.website_session_id
            """
        )
        return [
            {
                "website_session_id": int(r[0]),
                "pageview_count": int(r[1]),
                "session_duration_seconds": float(r[2] or 0),
                "converted": bool(r[3]),
                "order_revenue_cents": decimal_to_cents(r[4]),
                "gross_profit_cents": decimal_to_cents(r[5]),
            }
            for r in rows
        ]

    def sales_summary(self) -> dict[str, Any]:
        row = self._all(
            """
            SELECT
              (SELECT COUNT(*) FROM public.website_sessions),
              (SELECT COUNT(*) FROM public.canonical_orders),
              (SELECT COUNT(*) FROM public.canonical_orders),
              (SELECT COALESCE(SUM(price_usd), 0) FROM public.canonical_orders),
              (SELECT COALESCE(SUM(price_usd - cogs_usd), 0) FROM public.canonical_orders),
              (SELECT COALESCE(SUM(refund_amount_usd), 0)
                 FROM public.canonical_order_item_refunds)
            """
        )[0]
        sessions, orders, conversions = map(int, row[:3])
        return {
            "session_count": sessions,
            "order_count": orders,
            "conversion_count": conversions,
            "revenue_cents": decimal_to_cents(row[3]),
            "gross_profit_cents": decimal_to_cents(row[4]),
            "refund_cents": decimal_to_cents(row[5]),
            "conversion_rate": conversions / sessions if sessions else 0.0,
        }

    def product_performance(self) -> list[dict[str, Any]]:
        rows = self._all(
            """
            WITH item_totals AS (
              SELECT product_id, COUNT(DISTINCT order_id) AS order_count,
                     COUNT(*) AS units, SUM(price_usd) AS revenue,
                     SUM(cogs_usd) AS cogs
              FROM public.canonical_order_items GROUP BY product_id
            ), refund_totals AS (
              SELECT i.product_id, SUM(r.refund_amount_usd) AS refunds
              FROM public.canonical_order_item_refunds r
              JOIN public.canonical_order_items i USING (order_item_id)
              GROUP BY i.product_id
            )
            SELECT p.product_id, p.product_name,
                   COALESCE(i.order_count, 0), COALESCE(i.units, 0),
                   COALESCE(i.revenue, 0), COALESCE(i.cogs, 0),
                   COALESCE(r.refunds, 0)
            FROM public.canonical_products p
            LEFT JOIN item_totals i USING (product_id)
            LEFT JOIN refund_totals r USING (product_id)
            ORDER BY p.product_id
            """
        )
        result = []
        for row in rows:
            revenue = decimal_to_cents(row[4])
            refunds = decimal_to_cents(row[6])
            result.append({
                "product_id": int(row[0]), "product_name": row[1],
                "order_count": int(row[2]), "units": int(row[3]),
                "revenue_cents": revenue, "cogs_cents": decimal_to_cents(row[5]),
                "refund_cents": refunds, "net_revenue_cents": revenue - refunds,
            })
        return result
