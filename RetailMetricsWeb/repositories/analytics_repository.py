from __future__ import annotations

from decimal import Decimal
from typing import Any, Protocol

from psycopg2.extensions import TRANSACTION_STATUS_IDLE, connection


class AnalyticsRepository(Protocol):
    def dashboard(self, scope: str) -> dict[str, Any]: ...
    def workspace(self) -> dict[str, Any]: ...
    def list_historical_customers(self, search: str | None, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]: ...
    def historical_customer_detail(self, dataset_user_id: int) -> dict[str, Any] | None: ...
    def list_registered_customers(self, search: str | None, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]: ...


class PostgresAnalyticsRepository:
    """Presentation queries only. Every method explicitly starts a read-only transaction."""

    def __init__(self, conn: connection):
        self.conn = conn

    def _cursor(self):
        cur = self.conn.cursor()
        if self.conn.get_transaction_status() == TRANSACTION_STATUS_IDLE:
            cur.execute("SET TRANSACTION READ ONLY")
        return cur

    @staticmethod
    def _scope_clause(scope: str, alias: str = "o") -> str:
        if scope == "imported":
            return f"{alias}.record_origin = 'imported'"
        if scope == "application":
            return f"{alias}.record_origin <> 'imported'"
        return "TRUE"

    def dashboard(self, scope: str) -> dict[str, Any]:
        order_filter = self._scope_clause(scope)
        item_filter = self._scope_clause(scope, "oi")
        refund_filter = self._scope_clause(scope, "r")
        with self._cursor() as cur:
            cur.execute(f"""
                SELECT COUNT(*)::BIGINT, COALESCE(SUM(price_usd), 0)::NUMERIC(16,2),
                       COALESCE(SUM(cogs_usd), 0)::NUMERIC(16,2)
                FROM public.orders o WHERE {order_filter}
            """)
            order_count, gross_revenue, cogs = cur.fetchone()
            cur.execute(f"SELECT COALESCE(SUM(refund_amount_usd), 0)::NUMERIC(16,2) FROM public.order_item_refunds r WHERE {refund_filter}")
            refunds = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*)::BIGINT FROM public.website_sessions")
            sessions = int(cur.fetchone()[0]) if scope in {"imported", "combined"} else 0
            cur.execute(f"""
                SELECT TO_CHAR(DATE_TRUNC('month', o.created_at), 'YYYY-MM') AS period,
                       COUNT(*)::BIGINT AS orders,
                       COALESCE(SUM(o.price_usd), 0)::NUMERIC(16,2) AS revenue
                FROM public.orders o WHERE {order_filter}
                GROUP BY DATE_TRUNC('month', o.created_at) ORDER BY DATE_TRUNC('month', o.created_at)
            """)
            time_series = [{"period": r[0], "orders": int(r[1]), "revenue": r[2]} for r in cur.fetchall()]
            cur.execute(f"""
                SELECT p.product_id, p.product_name, COUNT(DISTINCT oi.order_id)::BIGINT,
                       COUNT(oi.order_item_id)::BIGINT, COALESCE(SUM(oi.price_usd),0)::NUMERIC(16,2) AS revenue,
                       COALESCE(SUM(oi.cogs_usd),0)::NUMERIC(16,2),
                       COALESCE(SUM(rr.refund_total),0)::NUMERIC(16,2)
                FROM public.products p
                LEFT JOIN public.order_items oi ON oi.product_id=p.product_id AND {item_filter}
                LEFT JOIN (
                    SELECT order_item_id, SUM(refund_amount_usd)::NUMERIC(16,2) refund_total
                    FROM public.order_item_refunds r WHERE {refund_filter} GROUP BY order_item_id
                ) rr ON rr.order_item_id=oi.order_item_id
                GROUP BY p.product_id,p.product_name ORDER BY revenue DESC, p.product_id
            """)
            products = [{"product_id": r[0], "product_name": r[1], "orders": int(r[2]), "units": int(r[3]),
                         "revenue": r[4], "cogs": r[5], "refunds": r[6], "net_revenue": r[4]-r[6]} for r in cur.fetchall()]
            traffic: list[dict[str, Any]] = []
            devices: list[dict[str, Any]] = []
            if scope in {"imported", "combined"}:
                cur.execute("""
                    SELECT COALESCE(s.utm_source,'Unattributed'), COUNT(DISTINCT s.website_session_id)::BIGINT,
                           COUNT(DISTINCT o.order_id)::BIGINT, COALESCE(SUM(o.price_usd),0)::NUMERIC(16,2)
                    FROM public.website_sessions s LEFT JOIN public.canonical_orders o USING (website_session_id)
                    GROUP BY COALESCE(s.utm_source,'Unattributed') ORDER BY 2 DESC
                """)
                traffic = [{"source": r[0], "sessions": int(r[1]), "orders": int(r[2]), "revenue": r[3],
                            "conversion_rate": (Decimal(r[2]) / Decimal(r[1]) * 100 if r[1] else Decimal(0))} for r in cur.fetchall()]
                cur.execute("SELECT COALESCE(device_type,'Unknown'), COUNT(*)::BIGINT FROM public.website_sessions GROUP BY 1 ORDER BY 2 DESC")
                devices = [{"device": r[0], "sessions": int(r[1])} for r in cur.fetchall()]
            cur.execute(f"""
                SELECT TO_CHAR(DATE_TRUNC('month', r.created_at), 'YYYY-MM'),
                       COUNT(*)::BIGINT, COALESCE(SUM(r.refund_amount_usd),0)::NUMERIC(16,2)
                FROM public.order_item_refunds r WHERE {refund_filter}
                GROUP BY DATE_TRUNC('month',r.created_at) ORDER BY DATE_TRUNC('month',r.created_at)
            """)
            refund_trend = [{"period": r[0], "refunds": int(r[1]), "amount": r[2]} for r in cur.fetchall()]
        gross_revenue = Decimal(gross_revenue)
        refunds = Decimal(refunds)
        cogs = Decimal(cogs)
        conversion = (Decimal(order_count) / Decimal(sessions) * 100) if scope == "imported" and sessions else None
        return {
            "scope": scope, "metrics": {"gross_revenue": gross_revenue, "net_revenue": gross_revenue-refunds,
            "gross_profit": gross_revenue-cogs, "cogs": cogs, "orders": int(order_count),
            "conversion_rate": conversion, "refund_amount": refunds, "sessions": sessions},
            "time_series": time_series, "products": products, "traffic_sources": traffic,
            "devices": devices, "refund_trend": refund_trend,
        }

    def workspace(self) -> dict[str, Any]:
        with self._cursor() as cur:
            cur.execute("""
                SELECT
                  (SELECT COUNT(*) FROM public.app_users WHERE is_active),
                  (SELECT COUNT(*) FROM public.customer_accounts WHERE is_active),
                  (SELECT COUNT(*) FROM public.app_users WHERE locked_until > NOW()) +
                    (SELECT COUNT(*) FROM public.customer_accounts WHERE locked_until > NOW()),
                  (SELECT COUNT(*) FROM public.product_catalog_details),
                  (SELECT COUNT(*) FROM public.refund_requests WHERE request_status='pending'),
                  (SELECT COUNT(*) FROM public.refund_requests WHERE request_status='approved'),
                  (SELECT COUNT(*) FROM public.customer_accounts WHERE created_at >= NOW()-INTERVAL '7 days'),
                  (SELECT COUNT(*) FROM public.orders WHERE record_origin='customer'
                    AND order_status='ready_shipped' AND updated_at >= NOW()-INTERVAL '7 days')
            """)
            row = cur.fetchone()
            cur.execute("SELECT order_status, COUNT(*)::BIGINT FROM public.orders WHERE record_origin='customer' GROUP BY order_status")
            statuses = {str(k): int(v) for k, v in cur.fetchall()}
            cur.execute("""
                SELECT o.order_id,o.customer_account_id,o.created_at,o.price_usd,o.order_status,p.payment_status
                FROM public.orders o LEFT JOIN public.order_payments p USING(order_id)
                WHERE o.record_origin='customer' AND o.order_status IN ('pending','processing')
                ORDER BY o.created_at LIMIT 8
            """)
            orders = [{"order_id": r[0], "customer_account_id": r[1], "created_at": r[2], "total": r[3], "status": r[4], "payment_status": r[5]} for r in cur.fetchall()]
            cur.execute("""
                SELECT rr.refund_request_id,rr.order_id,rr.requested_amount_usd,rr.request_status,rr.created_at,p.product_name
                FROM public.refund_requests rr JOIN public.order_items oi USING(order_item_id)
                JOIN public.products p USING(product_id)
                WHERE rr.request_status IN ('pending','approved') ORDER BY rr.created_at LIMIT 8
            """)
            requests = [{"request_id": r[0], "order_id": r[1], "amount": r[2], "status": r[3], "created_at": r[4], "product": r[5]} for r in cur.fetchall()]
        return {"active_staff": int(row[0]), "active_customers": int(row[1]), "locked_accounts": int(row[2]),
                "configured_products": int(row[3]), "pending_refunds": int(row[4]), "approved_refunds": int(row[5]),
                "recent_customers": int(row[6]), "recent_completed_orders": int(row[7]),
                "orders_by_status": statuses, "orders_needing_action": orders,
                "refunds_needing_action": requests}

    def list_historical_customers(self, search: str | None, limit: int, offset: int):
        params: list[Any] = []
        where = ""
        if search:
            try:
                value = int(search.strip().lstrip("#"))
                where = " WHERE dataset_user_id=%s"
                params.append(value)
            except ValueError:
                where = " WHERE FALSE"
        with self._cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM public.historical_customer_summary" + where, params)
            total = int(cur.fetchone()[0])
            cur.execute("""SELECT dataset_user_id,session_count,repeat_visitor,order_count,total_spent,
                                  refund_total,last_visit,latest_utm_source,latest_device_type
                           FROM public.historical_customer_summary""" + where +
                        " ORDER BY last_visit DESC,dataset_user_id LIMIT %s OFFSET %s", [*params, limit, offset])
            rows = cur.fetchall()
        keys = ("dataset_user_id","session_count","repeat_visitor","order_count","total_spent","refund_total","last_visit","latest_utm_source","latest_device_type")
        return [dict(zip(keys, row)) for row in rows], total

    def historical_customer_detail(self, dataset_user_id: int):
        with self._cursor() as cur:
            cur.execute("SELECT dataset_user_id,session_count,repeat_visitor,order_count,total_spent,refund_total,last_visit,latest_utm_source,latest_device_type FROM public.historical_customer_summary WHERE dataset_user_id=%s", (dataset_user_id,))
            row = cur.fetchone()
            if not row:
                return None
            keys = ("dataset_user_id","session_count","repeat_visitor","order_count","total_spent","refund_total","last_visit","latest_utm_source","latest_device_type")
            result = dict(zip(keys, row))
            cur.execute("SELECT order_id,created_at,items_purchased,price_usd FROM public.canonical_orders WHERE user_id=%s ORDER BY created_at DESC LIMIT 10", (dataset_user_id,))
            result["recent_orders"] = [{"order_id": r[0], "created_at": r[1], "items": r[2], "total": r[3]} for r in cur.fetchall()]
            cur.execute("SELECT website_session_id,created_at,utm_source,device_type,is_repeat_session FROM public.website_sessions WHERE user_id=%s ORDER BY created_at DESC LIMIT 10", (dataset_user_id,))
            result["recent_sessions"] = [{"session_id": r[0], "created_at": r[1], "source": r[2], "device": r[3], "repeat": bool(r[4])} for r in cur.fetchall()]
            cur.execute("""SELECT p.product_id,p.product_name,COUNT(*)::BIGINT,SUM(oi.price_usd)::NUMERIC(16,2)
                           FROM public.canonical_orders o JOIN public.canonical_order_items oi USING(order_id)
                           JOIN public.canonical_products p USING(product_id) WHERE o.user_id=%s
                           GROUP BY p.product_id,p.product_name ORDER BY 3 DESC""", (dataset_user_id,))
            result["product_purchases"] = [{"product_id": r[0], "product_name": r[1], "units": int(r[2]), "spent": r[3]} for r in cur.fetchall()]
        return result

    def list_registered_customers(self, search: str | None, limit: int, offset: int):
        params: list[Any] = []
        where = ""
        if search:
            pattern = f"%{search.strip()}%"
            where = " WHERE a.email ILIKE %s OR p.first_name ILIKE %s OR p.last_name ILIKE %s"
            params.extend((pattern, pattern, pattern))
        with self._cursor() as cur:
            base = " FROM public.customer_accounts a JOIN public.customer_profiles p USING(customer_account_id)"
            cur.execute("SELECT COUNT(*)" + base + where, params)
            total = int(cur.fetchone()[0])
            cur.execute("""SELECT a.customer_account_id,a.dataset_user_id,a.email,p.first_name,p.last_name,
                                  a.is_active,(a.locked_until>NOW()) AS is_locked,a.created_at,
                                  COUNT(o.order_id)::BIGINT,COALESCE(SUM(o.price_usd),0)::NUMERIC(16,2)
                           FROM public.customer_accounts a JOIN public.customer_profiles p USING(customer_account_id)
                           LEFT JOIN public.orders o ON o.customer_account_id=a.customer_account_id""" + where +
                        " GROUP BY a.customer_account_id,p.customer_account_id ORDER BY a.created_at DESC LIMIT %s OFFSET %s", [*params, limit, offset])
            rows = cur.fetchall()
        keys = ("customer_account_id","dataset_user_id","email","first_name","last_name","is_active","is_locked","created_at","order_count","total_spent")
        return [dict(zip(keys, row)) for row in rows], total
