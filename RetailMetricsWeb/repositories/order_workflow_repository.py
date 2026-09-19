from __future__ import annotations

from typing import Protocol

from psycopg2.extras import RealDictCursor


class OrderWorkflowNotFound(ValueError):
    pass


class OrderWorkflowConflict(ValueError):
    pass


class OrderWorkflowRepository(Protocol):
    def list_customer_orders(self, status_filter: str | None, limit: int, offset: int) -> tuple[list[dict], int]: ...
    def transition(self, order_id: int, row_version: int, action: str) -> tuple[dict, str]: ...


class PostgresOrderWorkflowRepository:
    def __init__(self, conn):
        self.conn = conn

    @staticmethod
    def _projection() -> str:
        return """SELECT o.order_id,o.customer_account_id,o.created_at,
                         o.price_usd AS total_usd,op.payment_status,o.order_status,
                         o.record_origin AS origin,o.row_version,
                         o.delivered_at,o.delivered_confirmed_by_customer
                  FROM public.orders o
                  JOIN public.order_payments op ON op.order_id=o.order_id"""

    def list_customer_orders(self, status_filter: str | None, limit: int, offset: int) -> tuple[list[dict], int]:
        where = "o.record_origin='customer'"
        params: list = []
        if status_filter:
            where += " AND o.order_status=%s"
            params.append(status_filter)
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(f"SELECT COUNT(*) FROM public.orders o WHERE {where}", params)
            total = int(cur.fetchone()["count"])
            cur.execute(
                self._projection() + f" WHERE {where} ORDER BY o.order_id DESC LIMIT %s OFFSET %s",
                [*params, limit, offset],
            )
            return [dict(row) for row in cur.fetchall()], total

    def transition(self, order_id: int, row_version: int, action: str) -> tuple[dict, str]:
        transitions = {
            "start-processing": ("pending", "processing"),
            "ready-shipped": ("processing", "ready_shipped"),
            "cancel": ("pending", "cancelled"),
        }
        required_status, next_status = transitions[action]
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """SELECT order_id,record_origin,order_status,row_version
                   FROM public.orders WHERE order_id=%s FOR UPDATE""",
                (order_id,),
            )
            current = cur.fetchone()
            if not current:
                raise OrderWorkflowNotFound("Order not found.")
            if current["record_origin"] != "customer":
                raise OrderWorkflowConflict("Only customer-created orders use this lifecycle workflow.")
            cur.execute(
                "SELECT method_type,payment_status FROM public.order_payments WHERE order_id=%s FOR UPDATE",
                (order_id,),
            )
            payment = cur.fetchone()
            if not payment:
                raise OrderWorkflowConflict("The customer order has no payment record.")
            if int(current["row_version"]) != row_version:
                raise OrderWorkflowConflict(
                    f"Stale row_version: expected {row_version}, current value is {current['row_version']}."
                )
            if current["order_status"] != required_status:
                raise OrderWorkflowConflict(
                    f"Order must be {required_status} before it can become {next_status}."
                )
            method_type = payment["method_type"]
            payment_status = payment["payment_status"]
            if action in {"start-processing", "ready-shipped"}:
                compatible = (
                    payment_status == "paid"
                    or (method_type == "cash_on_delivery" and payment_status == "pending")
                )
                if not compatible:
                    raise OrderWorkflowConflict("The current payment state is incompatible with this order transition.")
            if action == "cancel":
                if payment_status == "paid":
                    cur.execute(
                        """UPDATE public.order_payments SET payment_status='refunded',
                                  row_version=row_version+1,updated_at=NOW()
                           WHERE order_id=%s""",
                        (order_id,),
                    )
                elif not (method_type == "cash_on_delivery" and payment_status == "pending"):
                    raise OrderWorkflowConflict("The current payment state does not permit cancellation.")
            elif action == "ready-shipped" and method_type == "cash_on_delivery" and payment_status == "pending":
                cur.execute(
                    """UPDATE public.order_payments SET payment_status='paid',processed_at=COALESCE(processed_at,NOW()),
                              row_version=row_version+1,updated_at=NOW() WHERE order_id=%s""",
                    (order_id,),
                )
            cur.execute(
                """UPDATE public.orders SET order_status=%s,row_version=row_version+1,updated_at=NOW()
                   WHERE order_id=%s""",
                (next_status, order_id),
            )
            cur.execute(self._projection() + " WHERE o.order_id=%s", (order_id,))
            return dict(cur.fetchone()), required_status
