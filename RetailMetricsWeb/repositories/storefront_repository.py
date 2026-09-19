from __future__ import annotations

from decimal import Decimal
from typing import Any, Protocol

from psycopg2 import errors

from core.models import CartItem, CatalogProduct, ShoppingCart


class CartQuantityExceeded(ValueError):
    pass


CATALOG_SELECT = """
SELECT p.product_id, p.product_name, d.description, d.current_price_usd,
       d.current_cogs_usd, d.image_url, d.is_available,
       d.updated_by_app_user_id, d.row_version, d.created_at, d.updated_at
FROM public.products p
LEFT JOIN public.product_catalog_details d ON d.product_id=p.product_id
"""

CART_ITEM_SELECT = """
SELECT ci.cart_item_id, ci.product_id, p.product_name, d.image_url, ci.quantity,
       ci.unit_price_usd, d.current_price_usd,
       (d.product_id IS NOT NULL AND d.is_available AND BTRIM(d.description) <> ''),
       ci.row_version, ci.created_at, ci.updated_at
FROM public.cart_items ci
JOIN public.shopping_carts sc ON sc.shopping_cart_id=ci.shopping_cart_id
JOIN public.products p ON p.product_id=ci.product_id
LEFT JOIN public.product_catalog_details d ON d.product_id=ci.product_id
"""


def _catalog(row) -> CatalogProduct:
    return CatalogProduct(*row)


def _cart_item(row) -> CartItem:
    return CartItem(*row)


class StorefrontRepository(Protocol):
    def list_catalog(self) -> list[CatalogProduct]: ...
    def get_catalog_product(self, product_id: int) -> CatalogProduct | None: ...
    def configure_catalog(self, product_id: int, values: dict[str, Any], actor_id: int, row_version: int | None) -> CatalogProduct | None: ...
    def list_store_products(self, search: str | None) -> list[CatalogProduct]: ...
    def get_store_product(self, product_id: int) -> CatalogProduct | None: ...
    def get_cart(self, customer_id: int) -> ShoppingCart: ...
    def get_cart_item(self, customer_id: int, cart_item_id: int) -> CartItem | None: ...
    def add_cart_item(self, customer_id: int, product_id: int, quantity: int, unit_price: Decimal) -> CartItem: ...
    def update_cart_item(self, customer_id: int, cart_item_id: int, quantity: int, row_version: int) -> CartItem | None: ...
    def delete_cart_item(self, customer_id: int, cart_item_id: int, row_version: int) -> bool: ...


class PostgresStorefrontRepository:
    def __init__(self, conn):
        self.conn = conn

    def list_catalog(self) -> list[CatalogProduct]:
        with self.conn.cursor() as cur:
            cur.execute(CATALOG_SELECT + " ORDER BY p.product_id")
            return [_catalog(row) for row in cur.fetchall()]

    def get_catalog_product(self, product_id: int) -> CatalogProduct | None:
        with self.conn.cursor() as cur:
            cur.execute(CATALOG_SELECT + " WHERE p.product_id=%s", (product_id,))
            row = cur.fetchone()
            return _catalog(row) if row else None

    def configure_catalog(self, product_id: int, values: dict[str, Any], actor_id: int, row_version: int | None) -> CatalogProduct | None:
        image_url = values.get("image_url")
        with self.conn.cursor() as cur:
            if row_version is None:
                cur.execute(
                    """INSERT INTO public.product_catalog_details
                       (product_id,description,current_price_usd,current_cogs_usd,image_url,is_available,updated_by_app_user_id)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                    (product_id, values["description"], values["current_price_usd"], values["current_cogs_usd"], image_url, values["is_available"], actor_id),
                )
            else:
                cur.execute(
                    """UPDATE public.product_catalog_details SET description=%s,
                       current_price_usd=%s,current_cogs_usd=%s,image_url=%s,
                       is_available=%s,updated_by_app_user_id=%s,
                       row_version=row_version+1,updated_at=NOW()
                       WHERE product_id=%s AND row_version=%s""",
                    (values["description"], values["current_price_usd"], values["current_cogs_usd"], image_url, values["is_available"], actor_id, product_id, row_version),
                )
                if cur.rowcount != 1:
                    return None
        return self.get_catalog_product(product_id)

    def list_store_products(self, search: str | None) -> list[CatalogProduct]:
        query = CATALOG_SELECT + " WHERE d.product_id IS NOT NULL AND d.is_available AND BTRIM(d.description) <> ''"
        params: list[Any] = []
        if search:
            query += " AND p.product_name ILIKE %s"
            params.append(f"%{search}%")
        query += " ORDER BY p.product_id"
        with self.conn.cursor() as cur:
            cur.execute(query, params)
            return [_catalog(row) for row in cur.fetchall()]

    def get_store_product(self, product_id: int) -> CatalogProduct | None:
        with self.conn.cursor() as cur:
            cur.execute(CATALOG_SELECT + " WHERE p.product_id=%s AND d.product_id IS NOT NULL AND d.is_available AND BTRIM(d.description) <> ''", (product_id,))
            row = cur.fetchone()
            return _catalog(row) if row else None

    def get_cart(self, customer_id: int) -> ShoppingCart:
        with self.conn.cursor() as cur:
            cur.execute("SELECT shopping_cart_id,row_version FROM public.shopping_carts WHERE customer_account_id=%s AND cart_status='active'", (customer_id,))
            cart = cur.fetchone()
            if not cart:
                return ShoppingCart(None, None, [])
            cur.execute(CART_ITEM_SELECT + " WHERE sc.customer_account_id=%s AND sc.cart_status='active' ORDER BY ci.cart_item_id", (customer_id,))
            return ShoppingCart(int(cart[0]), int(cart[1]), [_cart_item(row) for row in cur.fetchall()])

    def get_cart_item(self, customer_id: int, cart_item_id: int) -> CartItem | None:
        with self.conn.cursor() as cur:
            cur.execute(CART_ITEM_SELECT + " WHERE sc.customer_account_id=%s AND sc.cart_status='active' AND ci.cart_item_id=%s", (customer_id, cart_item_id))
            row = cur.fetchone()
            return _cart_item(row) if row else None

    def add_cart_item(self, customer_id: int, product_id: int, quantity: int, unit_price: Decimal) -> CartItem:
        with self.conn.cursor() as cur:
            cur.execute("SELECT customer_account_id FROM public.customer_accounts WHERE customer_account_id=%s FOR UPDATE", (customer_id,))
            if cur.fetchone() is None:
                raise LookupError("Customer account not found.")
            cur.execute("SELECT shopping_cart_id FROM public.shopping_carts WHERE customer_account_id=%s AND cart_status='active' FOR UPDATE", (customer_id,))
            row = cur.fetchone()
            if row:
                cart_id = int(row[0])
            else:
                try:
                    cur.execute("INSERT INTO public.shopping_carts (customer_account_id) VALUES (%s) RETURNING shopping_cart_id", (customer_id,))
                    cart_id = int(cur.fetchone()[0])
                except errors.UniqueViolation:
                    self.conn.rollback()
                    raise
            cur.execute("SELECT cart_item_id,quantity,row_version FROM public.cart_items WHERE shopping_cart_id=%s AND product_id=%s FOR UPDATE", (cart_id, product_id))
            existing = cur.fetchone()
            if existing:
                new_quantity = int(existing[1]) + quantity
                if new_quantity > 99:
                    raise CartQuantityExceeded("Cart item quantity cannot exceed 99.")
                cur.execute("UPDATE public.cart_items SET quantity=%s,row_version=row_version+1,updated_at=NOW() WHERE cart_item_id=%s", (new_quantity, int(existing[0])))
                item_id = int(existing[0])
            else:
                cur.execute("INSERT INTO public.cart_items (shopping_cart_id,product_id,quantity,unit_price_usd) VALUES (%s,%s,%s,%s) RETURNING cart_item_id", (cart_id, product_id, quantity, unit_price))
                item_id = int(cur.fetchone()[0])
            cur.execute("UPDATE public.shopping_carts SET row_version=row_version+1,updated_at=NOW() WHERE shopping_cart_id=%s", (cart_id,))
        item = self.get_cart_item(customer_id, item_id)
        assert item is not None
        return item

    def update_cart_item(self, customer_id: int, cart_item_id: int, quantity: int, row_version: int) -> CartItem | None:
        with self.conn.cursor() as cur:
            cur.execute(
                """UPDATE public.cart_items ci SET quantity=%s,row_version=ci.row_version+1,updated_at=NOW()
                   FROM public.shopping_carts sc
                   WHERE ci.shopping_cart_id=sc.shopping_cart_id AND sc.customer_account_id=%s
                     AND sc.cart_status='active' AND ci.cart_item_id=%s AND ci.row_version=%s
                   RETURNING ci.shopping_cart_id""",
                (quantity, customer_id, cart_item_id, row_version),
            )
            changed = cur.fetchone()
            if not changed:
                return None
            cur.execute("UPDATE public.shopping_carts SET row_version=row_version+1,updated_at=NOW() WHERE shopping_cart_id=%s", (int(changed[0]),))
        return self.get_cart_item(customer_id, cart_item_id)

    def delete_cart_item(self, customer_id: int, cart_item_id: int, row_version: int) -> bool:
        with self.conn.cursor() as cur:
            cur.execute(
                """DELETE FROM public.cart_items ci USING public.shopping_carts sc
                   WHERE ci.shopping_cart_id=sc.shopping_cart_id AND sc.customer_account_id=%s
                     AND sc.cart_status='active' AND ci.cart_item_id=%s AND ci.row_version=%s""",
                (customer_id, cart_item_id, row_version),
            )
            deleted = cur.rowcount == 1
            if deleted:
                cur.execute("UPDATE public.shopping_carts SET row_version=row_version+1,updated_at=NOW() WHERE customer_account_id=%s AND cart_status='active'", (customer_id,))
            return deleted
