from __future__ import annotations

import argparse
import sys
from pathlib import Path

import psycopg2

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from core.config import Settings


PRESENTATION_EMAIL = "presentation.customer@example.com"


def parse_args():
    parser = argparse.ArgumentParser(description="Dry-run or reset explicit RetailMetrics presentation order IDs.")
    parser.add_argument("--order-id", type=int, action="append", required=True, help="Explicit presentation order ID; repeat for more than one.")
    parser.add_argument("--execute", action="store_true", help="Permit deletion after an interactive confirmation.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    order_ids = sorted(set(args.order_id))
    if any(value <= 0 for value in order_ids):
        raise RuntimeError("Every order ID must be positive.")
    conn = psycopg2.connect(**Settings.from_environment().database_kwargs())
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT customer_account_id FROM public.customer_accounts WHERE LOWER(email)=LOWER(%s) FOR UPDATE", (PRESENTATION_EMAIL,))
            account = cur.fetchone()
            if not account:
                raise RuntimeError("The approved presentation customer does not exist.")
            customer_id = int(account[0])
            cur.execute("""SELECT order_id,order_status,record_origin FROM public.orders
                           WHERE order_id=ANY(%s) AND customer_account_id=%s FOR UPDATE""", (order_ids, customer_id))
            orders = cur.fetchall()
            found = {int(row[0]) for row in orders}
            if found != set(order_ids):
                raise RuntimeError(f"Refused: requested IDs do not all belong to the approved presentation customer. Found {sorted(found)}.")
            if any(row[2] != "customer" for row in orders):
                raise RuntimeError("Refused: every target order must have record_origin='customer'.")
            print(f"Approved presentation customer ID: {customer_id}")
            print("Explicit target orders:", ", ".join(str(value) for value in order_ids))
            for table in ("order_item_refunds", "refund_requests", "order_payments", "order_shipping_addresses", "order_items"):
                cur.execute(f"SELECT COUNT(*) FROM public.{table} WHERE order_id=ANY(%s)", (order_ids,))
                print(f"{table}: {cur.fetchone()[0]}")
            cur.execute("SELECT COUNT(*) FROM public.shopping_carts WHERE converted_order_id=ANY(%s)", (order_ids,))
            print(f"converted carts: {cur.fetchone()[0]}")
            if not args.execute:
                conn.rollback()
                print("DRY RUN ONLY. Nothing was deleted. Add --execute only after reviewing these exact IDs.")
                return 0
            confirmation = input(f"Type RESET {PRESENTATION_EMAIL} to delete only these records: ")
            if confirmation != f"RESET {PRESENTATION_EMAIL}":
                conn.rollback()
                raise RuntimeError("Confirmation did not match; nothing was deleted.")
            cur.execute("DELETE FROM public.cart_items WHERE shopping_cart_id IN (SELECT shopping_cart_id FROM public.shopping_carts WHERE converted_order_id=ANY(%s))", (order_ids,))
            cur.execute("DELETE FROM public.shopping_carts WHERE converted_order_id=ANY(%s)", (order_ids,))
            cur.execute("DELETE FROM public.order_item_refunds WHERE order_id=ANY(%s) AND record_origin='customer'", (order_ids,))
            cur.execute("DELETE FROM public.refund_requests WHERE order_id=ANY(%s) AND customer_account_id=%s", (order_ids, customer_id))
            cur.execute("DELETE FROM public.order_payments WHERE order_id=ANY(%s) AND customer_account_id=%s", (order_ids, customer_id))
            cur.execute("DELETE FROM public.order_shipping_addresses WHERE order_id=ANY(%s) AND customer_account_id=%s", (order_ids, customer_id))
            cur.execute("DELETE FROM public.order_items WHERE order_id=ANY(%s) AND record_origin='customer'", (order_ids,))
            cur.execute("DELETE FROM public.orders WHERE order_id=ANY(%s) AND customer_account_id=%s AND record_origin='customer'", (order_ids, customer_id))
            if cur.rowcount != len(order_ids):
                raise RuntimeError("Final order deletion count did not match; transaction rolled back.")
        conn.commit()
        print("Targeted presentation reset committed. Catalog, customer account, addresses, and payment methods were retained.")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (Exception, KeyboardInterrupt) as exc:
        print(f"Reset stopped safely: {exc}", file=sys.stderr)
        raise SystemExit(1)
