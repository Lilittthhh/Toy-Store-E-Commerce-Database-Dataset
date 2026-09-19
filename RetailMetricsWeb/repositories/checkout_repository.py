from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Protocol

from psycopg2.extras import RealDictCursor


class CheckoutConflict(ValueError):
    pass


class CheckoutResourceNotFound(ValueError):
    pass


class CustomerOrderNotFound(ValueError):
    pass


class CustomerOrderConflict(ValueError):
    pass


class CheckoutRepository(Protocol):
    def checkout(self, customer_id: int, address_id: int, payment_method_id: int, cart_version: int) -> dict: ...
    def list_orders(self, customer_id: int) -> list[dict]: ...
    def get_order(self, customer_id: int, order_id: int) -> dict | None: ...
    def cancel_order(self, customer_id: int, order_id: int, row_version: int) -> dict: ...
    def confirm_delivery(self, customer_id: int, order_id: int, row_version: int) -> dict: ...


class PostgresCheckoutRepository:
    def __init__(self, conn):
        self.conn = conn

    def checkout(self, customer_id: int, address_id: int, payment_method_id: int, cart_version: int) -> dict:
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT shopping_cart_id,row_version FROM public.shopping_carts WHERE customer_account_id=%s AND cart_status='active' FOR UPDATE",
                (customer_id,),
            )
            cart = cur.fetchone()
            if not cart:
                raise CheckoutConflict("No active cart is available for checkout.")
            if int(cart["row_version"]) != cart_version:
                raise CheckoutConflict(f"Stale cart row_version: expected {cart_version}, current value is {cart['row_version']}.")
            cart_id = int(cart["shopping_cart_id"])
            cur.execute(
                "SELECT cart_item_id,product_id,quantity,unit_price_usd FROM public.cart_items WHERE shopping_cart_id=%s ORDER BY cart_item_id FOR UPDATE",
                (cart_id,),
            )
            cart_items = [dict(row) for row in cur.fetchall()]
            if not cart_items:
                raise CheckoutConflict("The active cart is empty.")

            authoritative = []
            for cart_item in cart_items:
                cur.execute(
                    """SELECT p.product_name,d.current_price_usd,d.current_cogs_usd,d.is_available,d.description
                       FROM public.products p
                       JOIN public.product_catalog_details d ON d.product_id=p.product_id
                       WHERE p.product_id=%s
                       FOR SHARE OF d""",
                    (cart_item["product_id"],),
                )
                product = cur.fetchone()
                if not product or product["current_price_usd"] is None or not product["is_available"] or not str(product["description"] or "").strip():
                    name = product["product_name"] if product else f"Product {cart_item['product_id']}"
                    raise CheckoutConflict(f"{name} is unavailable and cannot be checked out.")
                stored = Decimal(cart_item["unit_price_usd"])
                current = Decimal(product["current_price_usd"])
                if stored != current:
                    raise CheckoutConflict(f"The price of {product['product_name']} changed from {stored:.2f} to {current:.2f}. Review the cart before checkout.")
                authoritative.append({
                    **cart_item, "product_name": product["product_name"],
                    "price": current, "cogs": Decimal(product["current_cogs_usd"]),
                })

            cur.execute(
                """SELECT * FROM public.customer_addresses
                   WHERE customer_address_id=%s AND customer_account_id=%s AND is_active FOR SHARE""",
                (address_id, customer_id),
            )
            address = cur.fetchone()
            if not address:
                raise CheckoutResourceNotFound("Active shipping address not found.")
            cur.execute(
                """SELECT * FROM public.payment_methods
                   WHERE payment_method_id=%s AND customer_account_id=%s AND is_active FOR SHARE""",
                (payment_method_id, customer_id),
            )
            payment = cur.fetchone()
            if not payment:
                raise CheckoutResourceNotFound("Active payment method not found.")

            total_quantity = sum(int(item["quantity"]) for item in authoritative)
            revenue = sum((item["price"] * int(item["quantity"]) for item in authoritative), Decimal("0.00"))
            cogs = sum((item["cogs"] * int(item["quantity"]) for item in authoritative), Decimal("0.00"))
            cur.execute(
                """INSERT INTO public.orders
                   (created_at,website_session_id,user_id,primary_product_id,items_purchased,
                    price_usd,cogs_usd,created_by_app_user_id,record_origin,
                    customer_account_id,order_status,updated_at)
                   VALUES (NOW(),NULL,NULL,%s,%s,%s,%s,NULL,'customer',%s,'pending',NOW())
                   RETURNING order_id""",
                (authoritative[0]["product_id"], total_quantity, revenue, cogs, customer_id),
            )
            order_id = int(cur.fetchone()["order_id"])
            primary = True
            for item in authoritative:
                for _ in range(int(item["quantity"])):
                    cur.execute(
                        """INSERT INTO public.order_items
                           (created_at,order_id,product_id,is_primary_item,price_usd,cogs_usd,
                            created_by_app_user_id,record_origin)
                           VALUES (NOW(),%s,%s,%s,%s,%s,NULL,'customer')""",
                        (order_id, item["product_id"], 1 if primary else 0, item["price"], item["cogs"]),
                    )
                    primary = False

            cur.execute(
                """INSERT INTO public.order_shipping_addresses
                   (order_id,customer_account_id,source_customer_address_id,recipient_first_name,
                    recipient_last_name,phone,address_line_1,address_line_2,city,province_region,
                    postal_code,country_code)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (order_id, customer_id, address_id, address["recipient_first_name"], address["recipient_last_name"],
                 address["phone"], address["address_line_1"], address["address_line_2"], address["city"],
                 address["province_region"], address["postal_code"], address["country_code"]),
            )
            prepaid = payment["method_type"] != "cash_on_delivery"
            payment_status = "paid" if prepaid else "pending"
            cur.execute(
                """INSERT INTO public.order_payments
                   (order_id,customer_account_id,payment_method_id,method_type,payment_display_snapshot,
                    payment_status,amount_usd,simulated_reference,processed_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (order_id, customer_id, payment_method_id, payment["method_type"], payment["display_label"],
                 payment_status, revenue, "RM-DEMO-" + uuid.uuid4().hex.upper(),
                 None),
            )
            if prepaid:
                cur.execute("UPDATE public.order_payments SET processed_at=NOW() WHERE order_id=%s", (order_id,))
            cur.execute(
                """UPDATE public.shopping_carts SET cart_status='converted',converted_order_id=%s,
                   row_version=row_version+1,updated_at=NOW()
                   WHERE shopping_cart_id=%s AND customer_account_id=%s AND cart_status='active' AND row_version=%s""",
                (order_id, cart_id, customer_id, cart_version),
            )
            if cur.rowcount != 1:
                raise CheckoutConflict("The cart changed during checkout.")
        detail = self.get_order(customer_id, order_id)
        assert detail is not None
        return detail

    def list_orders(self, customer_id: int) -> list[dict]:
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """SELECT o.order_id,o.created_at,o.order_status,o.delivered_at,
                          o.delivered_confirmed_by_customer,op.payment_status,
                          COUNT(DISTINCT oi.order_item_id)::int AS item_count,
                          o.items_purchased AS total_quantity,o.price_usd AS total_usd,o.row_version
                   FROM public.orders o
                   JOIN public.order_payments op ON op.order_id=o.order_id
                   JOIN public.order_items oi ON oi.order_id=o.order_id
                   WHERE o.customer_account_id=%s AND o.record_origin='customer'
                   GROUP BY o.order_id,op.payment_status
                   ORDER BY o.order_id DESC""",
                (customer_id,),
            )
            return [dict(row) for row in cur.fetchall()]

    def get_order(self, customer_id: int, order_id: int) -> dict | None:
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """SELECT o.order_id,o.created_at,o.order_status,o.delivered_at,
                          o.delivered_confirmed_by_customer,o.items_purchased AS total_quantity,
                          o.price_usd AS total_usd,o.row_version,
                          s.recipient_first_name,s.recipient_last_name,s.phone,s.address_line_1,
                          s.address_line_2,s.city,s.province_region,s.postal_code,s.country_code,
                          p.method_type,p.payment_display_snapshot,p.payment_status,p.amount_usd,
                          p.simulated_reference
                   FROM public.orders o
                   JOIN public.order_shipping_addresses s ON s.order_id=o.order_id
                   JOIN public.order_payments p ON p.order_id=o.order_id
                   WHERE o.order_id=%s AND o.customer_account_id=%s AND o.record_origin='customer'""",
                (order_id, customer_id),
            )
            row = cur.fetchone()
            if not row:
                return None
            data = dict(row)
            cur.execute(
                """SELECT oi.product_id,pr.product_name,COUNT(*)::int AS quantity,
                          oi.price_usd AS unit_price_usd,SUM(oi.price_usd) AS line_total_usd
                   FROM public.order_items oi JOIN public.products pr ON pr.product_id=oi.product_id
                   WHERE oi.order_id=%s AND oi.record_origin='customer'
                   GROUP BY oi.product_id,pr.product_name,oi.price_usd ORDER BY MIN(oi.order_item_id)""",
                (order_id,),
            )
            data["items"] = [dict(item) for item in cur.fetchall()]
        data["shipping"] = {key: data.pop(key) for key in (
            "recipient_first_name", "recipient_last_name", "phone", "address_line_1",
            "address_line_2", "city", "province_region", "postal_code", "country_code",
        )}
        data["payment"] = {
            "method_type": data.pop("method_type"),
            "display_label": data.pop("payment_display_snapshot"),
            "payment_status": data.pop("payment_status"),
            "amount_usd": data.pop("amount_usd"),
            "simulated_reference": data.pop("simulated_reference"),
        }
        return data

    def cancel_order(self, customer_id: int, order_id: int, row_version: int) -> dict:
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """SELECT order_status,row_version FROM public.orders
                   WHERE order_id=%s AND customer_account_id=%s AND record_origin='customer' FOR UPDATE""",
                (order_id, customer_id),
            )
            order = cur.fetchone()
            if not order:
                raise CustomerOrderNotFound("Order not found.")
            if int(order["row_version"]) != row_version:
                raise CustomerOrderConflict(f"Stale row_version: expected {row_version}, current value is {order['row_version']}.")
            if order["order_status"] != "pending":
                raise CustomerOrderConflict("Only a pending order can be cancelled.")
            cur.execute("SELECT method_type,payment_status FROM public.order_payments WHERE order_id=%s FOR UPDATE", (order_id,))
            payment = cur.fetchone()
            if not payment:
                raise CustomerOrderConflict("Order payment record is unavailable.")
            if payment["payment_status"] == "paid":
                next_status = "refunded"
            elif payment["method_type"] == "cash_on_delivery" and payment["payment_status"] == "pending":
                next_status = "pending"
            else:
                raise CustomerOrderConflict("The current payment state does not permit cancellation.")
            cur.execute("UPDATE public.order_payments SET payment_status=%s,row_version=row_version+1,updated_at=NOW() WHERE order_id=%s", (next_status, order_id))
            cur.execute("UPDATE public.orders SET order_status='cancelled',row_version=row_version+1,updated_at=NOW() WHERE order_id=%s", (order_id,))
        result = self.get_order(customer_id, order_id)
        assert result is not None
        return result

    def confirm_delivery(self, customer_id: int, order_id: int, row_version: int) -> dict:
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """SELECT order_status,row_version FROM public.orders
                   WHERE order_id=%s AND customer_account_id=%s AND record_origin='customer'
                   FOR UPDATE""",
                (order_id, customer_id),
            )
            order = cur.fetchone()
            if not order:
                raise CustomerOrderNotFound("Order not found.")
            if int(order["row_version"]) != row_version:
                raise CustomerOrderConflict(
                    f"Stale row_version: expected {row_version}, current value is {order['row_version']}."
                )
            if order["order_status"] != "ready_shipped":
                raise CustomerOrderConflict("Only a Ready / Shipped order can be marked as received.")
            cur.execute(
                """UPDATE public.orders SET order_status='delivered',delivered_at=NOW(),
                          delivered_confirmed_by_customer=TRUE,row_version=row_version+1,updated_at=NOW()
                   WHERE order_id=%s AND customer_account_id=%s AND record_origin='customer'
                     AND order_status='ready_shipped' AND row_version=%s""",
                (order_id, customer_id, row_version),
            )
            if cur.rowcount != 1:
                raise CustomerOrderConflict("The order changed before delivery could be confirmed.")
        result = self.get_order(customer_id, order_id)
        assert result is not None
        return result
