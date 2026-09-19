from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from psycopg2 import sql
from psycopg2.extras import RealDictCursor


@dataclass(frozen=True)
class EntityConfig:
    table: str
    pk: str
    write_columns: tuple[str, ...]
    create_constants: tuple[tuple[str, Any], ...] = ()


ENTITIES = {
    "products": EntityConfig(
        "products",
        "product_id",
        ("created_at", "product_name"),
        (("record_origin", "staff"),),
    ),
    "orders": EntityConfig(
        "orders",
        "order_id",
        (
            "created_at",
            "website_session_id",
            "user_id",
            "primary_product_id",
            "items_purchased",
            "price_usd",
            "cogs_usd",
        ),
        (("record_origin", "staff"), ("order_status", "ready_shipped")),
    ),
    "order_items": EntityConfig(
        "order_items",
        "order_item_id",
        (
            "created_at",
            "order_id",
            "product_id",
            "is_primary_item",
            "price_usd",
            "cogs_usd",
        ),
        (("record_origin", "staff"),),
    ),
    "order_item_refunds": EntityConfig(
        "order_item_refunds",
        "order_item_refund_id",
        ("created_at", "order_item_id", "order_id", "refund_amount_usd"),
        (("record_origin", "staff"), ("refund_request_id", None)),
    ),
}


class BusinessRepository:
    def __init__(self, conn):
        self.conn = conn

    def _fetchone(self, query, params=()) -> dict[str, Any] | None:
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            row = cur.fetchone()
        return dict(row) if row else None

    def relation_exists(self, table: str, pk: str, value: int) -> bool:
        query = sql.SQL("SELECT EXISTS (SELECT 1 FROM public.{} WHERE {} = %s)").format(
            sql.Identifier(table), sql.Identifier(pk)
        )
        with self.conn.cursor() as cur:
            cur.execute(query, (value,))
            return bool(cur.fetchone()[0])

    def order_for_session_exists(self, session_id: int, exclude_id: int | None = None) -> bool:
        query = "SELECT EXISTS (SELECT 1 FROM public.orders WHERE website_session_id = %s"
        params: list[Any] = [session_id]
        if exclude_id is not None:
            query += " AND order_id <> %s"
            params.append(exclude_id)
        query += ")"
        with self.conn.cursor() as cur:
            cur.execute(query, params)
            return bool(cur.fetchone()[0])

    def get_session_user_id(self, session_id: int) -> int | None:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT user_id FROM public.website_sessions WHERE website_session_id = %s",
                (session_id,),
            )
            row = cur.fetchone()
        return int(row[0]) if row else None

    def get_order_record_origin(self, order_id: int) -> str | None:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT record_origin FROM public.orders WHERE order_id = %s",
                (order_id,),
            )
            row = cur.fetchone()
        return str(row[0]) if row else None

    def get_order_item_for_refund(self, order_item_id: int, lock: bool = False):
        suffix = " FOR UPDATE" if lock else ""
        return self._fetchone(
            """
            SELECT order_item_id, order_id, price_usd
            FROM public.order_items
            WHERE order_item_id = %s
            """ + suffix,
            (order_item_id,),
        )

    def refunded_total(self, order_item_id: int, exclude_refund_id: int | None = None):
        query = """
            SELECT COALESCE(SUM(refund_amount_usd), 0)
            FROM public.order_item_refunds
            WHERE order_item_id = %s
        """
        params: list[Any] = [order_item_id]
        if exclude_refund_id is not None:
            query += " AND order_item_refund_id <> %s"
            params.append(exclude_refund_id)
        with self.conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone()[0]

    def get(self, entity: str, entity_id: int) -> dict[str, Any] | None:
        config = ENTITIES[entity]
        query = sql.SQL(
            "SELECT *, CASE record_origin WHEN 'imported' THEN 'imported' "
            "WHEN 'customer' THEN 'customer' ELSE 'web' END AS origin "
            "FROM public.{} WHERE {} = %s"
        ).format(sql.Identifier(config.table), sql.Identifier(config.pk))
        return self._fetchone(query, (entity_id,))

    def list_mutable(
        self,
        entity: str,
        clauses: list[str],
        params: list[Any],
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        config = ENTITIES[entity]
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                sql.SQL("SELECT COUNT(*) FROM public.{}" + where).format(
                    sql.Identifier(config.table)
                ),
                params,
            )
            total = int(cur.fetchone()["count"])
            cur.execute(
                sql.SQL(
                    "SELECT *, CASE record_origin WHEN 'imported' THEN 'imported' "
                    "WHEN 'customer' THEN 'customer' ELSE 'web' END AS origin FROM public.{}"
                    + where
                    + " ORDER BY {} DESC LIMIT %s OFFSET %s"
                ).format(sql.Identifier(config.table), sql.Identifier(config.pk)),
                [*params, limit, offset],
            )
            return [dict(row) for row in cur.fetchall()], total

    def list_readonly(
        self,
        table: str,
        pk: str,
        clauses: list[str],
        params: list[Any],
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                sql.SQL("SELECT COUNT(*) FROM public.{}" + where).format(
                    sql.Identifier(table)
                ),
                params,
            )
            total = int(cur.fetchone()["count"])
            cur.execute(
                sql.SQL("SELECT * FROM public.{}" + where + " ORDER BY {} DESC LIMIT %s OFFSET %s").format(
                    sql.Identifier(table), sql.Identifier(pk)
                ),
                [*params, limit, offset],
            )
            return [dict(row) for row in cur.fetchall()], total

    def get_readonly(self, table: str, pk: str, entity_id: int):
        query = sql.SQL("SELECT * FROM public.{} WHERE {} = %s").format(
            sql.Identifier(table), sql.Identifier(pk)
        )
        return self._fetchone(query, (entity_id,))

    def create(self, entity: str, data: dict[str, Any], creator_id: int):
        config = ENTITIES[entity]
        constant_columns = tuple(column for column, _ in config.create_constants)
        columns = (
            *config.write_columns,
            "created_by_app_user_id",
            *constant_columns,
        )
        query = sql.SQL("INSERT INTO public.{} ({}) VALUES ({}) RETURNING *").format(
            sql.Identifier(config.table),
            sql.SQL(", ").join(map(sql.Identifier, columns)),
            sql.SQL(", ").join([sql.Placeholder()] * len(columns)),
        )
        params = (
            [data[column] for column in config.write_columns]
            + [creator_id]
            + [value for _, value in config.create_constants]
        )
        row = self._fetchone(query, params)
        assert row is not None
        row["origin"] = "web"
        return row

    def update(self, entity: str, entity_id: int, data: dict[str, Any], row_version: int):
        config = ENTITIES[entity]
        assignments = [
            sql.SQL("{} = {}").format(sql.Identifier(column), sql.Placeholder())
            for column in config.write_columns
        ]
        assignments.append(sql.SQL("row_version = row_version + 1"))
        query = sql.SQL(
            "UPDATE public.{} SET {} WHERE {} = %s "
            "AND record_origin = 'staff' AND created_by_app_user_id IS NOT NULL "
            "AND row_version = %s RETURNING *"
        ).format(
            sql.Identifier(config.table),
            sql.SQL(", ").join(assignments),
            sql.Identifier(config.pk),
        )
        params = [data[column] for column in config.write_columns]
        row = self._fetchone(query, [*params, entity_id, row_version])
        if row:
            row["origin"] = "web"
        return row

    def delete(self, entity: str, entity_id: int, row_version: int) -> bool:
        config = ENTITIES[entity]
        query = sql.SQL(
            "DELETE FROM public.{} WHERE {} = %s "
            "AND record_origin = 'staff' AND created_by_app_user_id IS NOT NULL "
            "AND row_version = %s RETURNING {}"
        ).format(
            sql.Identifier(config.table),
            sql.Identifier(config.pk),
            sql.Identifier(config.pk),
        )
        return self._fetchone(query, (entity_id, row_version)) is not None
