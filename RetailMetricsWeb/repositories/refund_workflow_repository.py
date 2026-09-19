from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from psycopg2.extras import RealDictCursor


ZERO = Decimal("0.00")


class RefundWorkflowNotFound(ValueError):
    pass


class RefundWorkflowConflict(ValueError):
    pass


class RefundWorkflowRepository(Protocol):
    def create_request(self, customer_id: int, order_item_id: int, amount: Decimal, reason: str) -> dict: ...
    def list_customer_requests(self, customer_id: int) -> list[dict]: ...
    def get_customer_request(self, customer_id: int, request_id: int) -> dict | None: ...
    def eligibility(self, customer_id: int, order_id: int) -> list[dict]: ...
    def list_staff_requests(self, status_filter: str | None, limit: int, offset: int) -> tuple[list[dict], int]: ...
    def get_staff_request(self, request_id: int) -> dict | None: ...
    def approve(self, request_id: int, row_version: int, reviewer_id: int, note: str | None) -> dict: ...
    def reject(self, request_id: int, row_version: int, reviewer_id: int, note: str) -> dict: ...
    def process(self, request_id: int, row_version: int, processor_id: int) -> dict: ...


class PostgresRefundWorkflowRepository:
    def __init__(self, conn):
        self.conn = conn

    @staticmethod
    def _remaining(item_price, refunded, reserved=ZERO) -> Decimal:
        return max(ZERO, Decimal(item_price) - Decimal(refunded or ZERO) - Decimal(reserved or ZERO))

    def _request_projection(self, where: str, params: tuple) -> dict | None:
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"""SELECT rr.refund_request_id,rr.order_id,rr.order_item_id,
                           oi.product_id,p.product_name,
                           rr.requested_amount_usd AS requested_amount,rr.reason,
                           rr.request_status AS status,rr.created_at,rr.reviewed_at,
                           rr.resolution_note,rr.row_version
                    FROM public.refund_requests rr
                    JOIN public.order_items oi ON oi.order_item_id=rr.order_item_id
                    JOIN public.products p ON p.product_id=oi.product_id
                    WHERE {where}""",
                params,
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def _lock_owned_item(self, cur, customer_id: int, order_item_id: int):
        cur.execute(
            """SELECT oi.order_item_id,oi.order_id,oi.product_id,oi.price_usd,
                      o.order_status,op.payment_status
               FROM public.order_items oi
               JOIN public.orders o ON o.order_id=oi.order_id
               JOIN public.order_payments op ON op.order_id=o.order_id
               WHERE oi.order_item_id=%s AND o.customer_account_id=%s
                 AND o.record_origin='customer' AND oi.record_origin='customer'
               FOR UPDATE OF oi,o,op""",
            (order_item_id, customer_id),
        )
        item = cur.fetchone()
        if not item:
            raise RefundWorkflowNotFound("Eligible order item not found.")
        return item

    def _actual_refunded(self, cur, order_item_id: int) -> Decimal:
        cur.execute(
            "SELECT COALESCE(SUM(refund_amount_usd),0) AS amount FROM public.order_item_refunds WHERE order_item_id=%s",
            (order_item_id,),
        )
        return Decimal(cur.fetchone()["amount"])

    def _approved_reserved(self, cur, order_item_id: int, exclude_request_id: int | None = None) -> Decimal:
        query = """SELECT COALESCE(SUM(requested_amount_usd),0) AS amount
                   FROM public.refund_requests
                   WHERE order_item_id=%s AND request_status='approved'"""
        params: list[int] = [order_item_id]
        if exclude_request_id is not None:
            query += " AND refund_request_id<>%s"
            params.append(exclude_request_id)
        cur.execute(query, params)
        return Decimal(cur.fetchone()["amount"])

    @staticmethod
    def _require_eligible(item) -> None:
        if item["order_status"] not in {"ready_shipped", "delivered"}:
            raise RefundWorkflowConflict("Refund requests are available only for Ready / Shipped or Delivered orders.")
        if item["payment_status"] not in {"paid", "partially_refunded"}:
            raise RefundWorkflowConflict("The order has no refundable paid balance.")

    def create_request(self, customer_id: int, order_item_id: int, amount: Decimal, reason: str) -> dict:
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            item = self._lock_owned_item(cur, customer_id, order_item_id)
            self._require_eligible(item)
            cur.execute(
                """SELECT 1 FROM public.refund_requests
                   WHERE customer_account_id=%s AND order_item_id=%s AND request_status='pending'""",
                (customer_id, order_item_id),
            )
            if cur.fetchone():
                raise RefundWorkflowConflict("A pending refund request already exists for this item.")
            remaining = self._remaining(
                item["price_usd"], self._actual_refunded(cur, order_item_id),
                self._approved_reserved(cur, order_item_id),
            )
            if amount > remaining:
                raise RefundWorkflowConflict(f"Requested amount exceeds the remaining refundable amount of {remaining:.2f}.")
            cur.execute(
                """INSERT INTO public.refund_requests
                   (customer_account_id,order_id,order_item_id,reason,requested_amount_usd,request_status)
                   VALUES (%s,%s,%s,%s,%s,'pending') RETURNING refund_request_id""",
                (customer_id, item["order_id"], order_item_id, reason, amount),
            )
            request_id = int(cur.fetchone()["refund_request_id"])
        result = self.get_customer_request(customer_id, request_id)
        assert result is not None
        return result

    def list_customer_requests(self, customer_id: int) -> list[dict]:
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """SELECT rr.refund_request_id,rr.order_id,rr.order_item_id,
                          oi.product_id,p.product_name,
                          rr.requested_amount_usd AS requested_amount,rr.reason,
                          rr.request_status AS status,rr.created_at,rr.reviewed_at,
                          rr.resolution_note
                   FROM public.refund_requests rr
                   JOIN public.order_items oi ON oi.order_item_id=rr.order_item_id
                   JOIN public.products p ON p.product_id=oi.product_id
                   WHERE rr.customer_account_id=%s ORDER BY rr.refund_request_id DESC""",
                (customer_id,),
            )
            return [dict(row) for row in cur.fetchall()]

    def get_customer_request(self, customer_id: int, request_id: int) -> dict | None:
        result = self._request_projection(
            "rr.refund_request_id=%s AND rr.customer_account_id=%s", (request_id, customer_id)
        )
        if result:
            result.pop("row_version", None)
        return result

    def eligibility(self, customer_id: int, order_id: int) -> list[dict]:
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """SELECT o.order_status,op.payment_status
                   FROM public.orders o JOIN public.order_payments op ON op.order_id=o.order_id
                   WHERE o.order_id=%s AND o.customer_account_id=%s AND o.record_origin='customer'""",
                (order_id, customer_id),
            )
            order = cur.fetchone()
            if not order:
                raise RefundWorkflowNotFound("Order not found.")
            cur.execute(
                """SELECT oi.order_item_id,oi.product_id,p.product_name,oi.price_usd,
                          COALESCE((SELECT SUM(r.refund_amount_usd) FROM public.order_item_refunds r
                                    WHERE r.order_item_id=oi.order_item_id),0) AS refunded,
                          COALESCE((SELECT SUM(rr.requested_amount_usd) FROM public.refund_requests rr
                                    WHERE rr.order_item_id=oi.order_item_id AND rr.request_status='approved'),0) AS reserved,
                          (SELECT rr.request_status FROM public.refund_requests rr
                           WHERE rr.order_item_id=oi.order_item_id AND rr.request_status IN ('pending','approved')
                           ORDER BY rr.refund_request_id DESC LIMIT 1) AS current_request_status
                   FROM public.order_items oi JOIN public.products p ON p.product_id=oi.product_id
                   WHERE oi.order_id=%s AND oi.record_origin='customer' ORDER BY oi.order_item_id""",
                (order_id,),
            )
            result = []
            for row in cur.fetchall():
                remaining = self._remaining(row["price_usd"], row["refunded"], row["reserved"])
                reason = None
                if order["order_status"] not in {"ready_shipped", "delivered"}:
                    reason = "Order must be Ready / Shipped or Delivered."
                elif order["payment_status"] not in {"paid", "partially_refunded"}:
                    reason = "No refundable paid balance."
                elif row["current_request_status"]:
                    reason = f"A {row['current_request_status']} request already reserves this item."
                elif remaining <= ZERO:
                    reason = "This item has been fully refunded."
                result.append({
                    "order_item_id": row["order_item_id"], "product_id": row["product_id"],
                    "product_name": row["product_name"], "item_price_usd": row["price_usd"],
                    "remaining_refundable_usd": remaining, "eligible": reason is None,
                    "reason": reason, "current_request_status": row["current_request_status"],
                })
            return result

    def list_staff_requests(self, status_filter: str | None, limit: int, offset: int) -> tuple[list[dict], int]:
        where, params = "TRUE", []
        if status_filter:
            where = "rr.request_status=%s"
            params.append(status_filter)
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(f"SELECT COUNT(*) FROM public.refund_requests rr WHERE {where}", params)
            total = int(cur.fetchone()["count"])
            cur.execute(
                f"""SELECT rr.refund_request_id,rr.order_id,rr.order_item_id,
                           oi.product_id,p.product_name,
                           rr.requested_amount_usd AS requested_amount,rr.reason,
                           rr.request_status AS status,rr.created_at,rr.reviewed_at,
                           rr.resolution_note,rr.row_version
                    FROM public.refund_requests rr
                    JOIN public.order_items oi ON oi.order_item_id=rr.order_item_id
                    JOIN public.products p ON p.product_id=oi.product_id
                    WHERE {where} ORDER BY rr.refund_request_id DESC LIMIT %s OFFSET %s""",
                [*params, limit, offset],
            )
            return [dict(row) for row in cur.fetchall()], total

    def get_staff_request(self, request_id: int) -> dict | None:
        return self._request_projection("rr.refund_request_id=%s", (request_id,))

    def _lock_request_and_item(self, cur, request_id: int):
        cur.execute("SELECT order_item_id FROM public.refund_requests WHERE refund_request_id=%s", (request_id,))
        identity = cur.fetchone()
        if not identity:
            raise RefundWorkflowNotFound("Refund request not found.")
        cur.execute("SELECT order_item_id FROM public.order_items WHERE order_item_id=%s FOR UPDATE", (identity["order_item_id"],))
        cur.execute("SELECT * FROM public.refund_requests WHERE refund_request_id=%s FOR UPDATE", (request_id,))
        return cur.fetchone()

    @staticmethod
    def _check_transition(request, row_version: int, required_status: str) -> None:
        if int(request["row_version"]) != row_version:
            raise RefundWorkflowConflict(
                f"Stale row_version: expected {row_version}, current value is {request['row_version']}."
            )
        if request["request_status"] != required_status:
            raise RefundWorkflowConflict(f"Refund request must be {required_status} for this action.")

    def approve(self, request_id: int, row_version: int, reviewer_id: int, note: str | None) -> dict:
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            request = self._lock_request_and_item(cur, request_id)
            self._check_transition(request, row_version, "pending")
            cur.execute(
                """SELECT o.order_status,op.payment_status
                   FROM public.orders o JOIN public.order_payments op ON op.order_id=o.order_id
                   WHERE o.order_id=%s FOR UPDATE OF o,op""",
                (request["order_id"],),
            )
            eligibility_context = cur.fetchone()
            self._require_eligible(eligibility_context)
            refunded = self._actual_refunded(cur, request["order_item_id"])
            reserved = self._approved_reserved(cur, request["order_item_id"], request_id)
            cur.execute("SELECT price_usd FROM public.order_items WHERE order_item_id=%s", (request["order_item_id"],))
            remaining = self._remaining(cur.fetchone()["price_usd"], refunded, reserved)
            if Decimal(request["requested_amount_usd"]) > remaining:
                raise RefundWorkflowConflict(f"Approved amount exceeds the remaining refundable amount of {remaining:.2f}.")
            cur.execute(
                """UPDATE public.refund_requests SET request_status='approved',resolution_note=%s,
                          reviewed_by_app_user_id=%s,reviewed_at=NOW(),row_version=row_version+1,updated_at=NOW()
                   WHERE refund_request_id=%s""",
                (note, reviewer_id, request_id),
            )
        result = self.get_staff_request(request_id)
        assert result is not None
        return result

    def reject(self, request_id: int, row_version: int, reviewer_id: int, note: str) -> dict:
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            request = self._lock_request_and_item(cur, request_id)
            self._check_transition(request, row_version, "pending")
            cur.execute(
                """UPDATE public.refund_requests SET request_status='rejected',resolution_note=%s,
                          reviewed_by_app_user_id=%s,reviewed_at=NOW(),row_version=row_version+1,updated_at=NOW()
                   WHERE refund_request_id=%s""",
                (note, reviewer_id, request_id),
            )
        result = self.get_staff_request(request_id)
        assert result is not None
        return result

    def process(self, request_id: int, row_version: int, processor_id: int) -> dict:
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            request = self._lock_request_and_item(cur, request_id)
            self._check_transition(request, row_version, "approved")
            cur.execute(
                """SELECT oi.order_id,oi.price_usd,o.customer_account_id,o.record_origin,
                          o.price_usd AS order_total,o.order_status,op.payment_status
                   FROM public.order_items oi
                   JOIN public.orders o ON o.order_id=oi.order_id
                   JOIN public.order_payments op ON op.order_id=o.order_id
                   WHERE oi.order_item_id=%s FOR UPDATE OF o,op""",
                (request["order_item_id"],),
            )
            context = cur.fetchone()
            if not context or context["order_id"] != request["order_id"] or context["customer_account_id"] != request["customer_account_id"] or context["record_origin"] != "customer":
                raise RefundWorkflowConflict("Refund request order linkage is no longer valid.")
            if context["order_status"] not in {"ready_shipped", "delivered"}:
                raise RefundWorkflowConflict("Only a Ready / Shipped or Delivered order can have a refund processed.")
            if context["payment_status"] not in {"paid", "partially_refunded"}:
                raise RefundWorkflowConflict("The order has no refundable paid balance.")
            actual = self._actual_refunded(cur, request["order_item_id"])
            amount = Decimal(request["requested_amount_usd"])
            remaining = self._remaining(context["price_usd"], actual)
            if amount > remaining:
                raise RefundWorkflowConflict(f"Approved amount exceeds the remaining refundable amount of {remaining:.2f}.")
            cur.execute(
                """INSERT INTO public.order_item_refunds
                   (created_at,order_item_id,order_id,refund_amount_usd,created_by_app_user_id,
                    record_origin,refund_request_id)
                   VALUES (NOW(),%s,%s,%s,%s,'customer',%s)""",
                (request["order_item_id"], request["order_id"], amount, processor_id, request_id),
            )
            cur.execute(
                """UPDATE public.refund_requests SET request_status='processed',row_version=row_version+1,
                          updated_at=NOW() WHERE refund_request_id=%s""",
                (request_id,),
            )
            cur.execute("SELECT COALESCE(SUM(refund_amount_usd),0) AS amount FROM public.order_item_refunds WHERE order_id=%s", (request["order_id"],))
            order_refunded = Decimal(cur.fetchone()["amount"])
            fully_refunded = order_refunded >= Decimal(context["order_total"])
            payment_status = "refunded" if fully_refunded else "partially_refunded"
            cur.execute(
                """UPDATE public.order_payments SET payment_status=%s,row_version=row_version+1,
                          updated_at=NOW() WHERE order_id=%s""",
                (payment_status, request["order_id"]),
            )
            if fully_refunded:
                cur.execute(
                    """UPDATE public.orders SET order_status='refunded',row_version=row_version+1,
                              updated_at=NOW() WHERE order_id=%s""",
                    (request["order_id"],),
                )
        result = self.get_staff_request(request_id)
        assert result is not None
        return result
