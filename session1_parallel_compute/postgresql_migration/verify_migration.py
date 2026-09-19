import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

EXPECTED = {
    "website_sessions": 472_871,
    "website_pageviews": 1_188_124,
    "orders": 32_313,
    "order_items": 40_025,
    "order_item_refunds": 1_731,
    "products": 4,
}

COUNT_SOURCES = {
    "orders": "canonical_orders",
    "order_items": "canonical_order_items",
    "order_item_refunds": "canonical_order_item_refunds",
    "products": "canonical_products",
}


def connect():
    return psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=int(os.getenv("PGPORT", "5432")),
        dbname=os.getenv("PGDATABASE", "retailmetrics"),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", ""),
    )


def main():
    conn = connect()
    try:
        with conn.cursor() as cur:
            print("RetailMetrics migration verification\n")

            all_counts_ok = True
            for table, expected in EXPECTED.items():
                source = COUNT_SOURCES.get(table, table)
                cur.execute(f'SELECT COUNT(*) FROM "{source}"')
                actual = cur.fetchone()[0]
                ok = actual == expected
                all_counts_ok = all_counts_ok and ok
                status = "PASS" if ok else "CHECK"
                print(
                    f"{table:24} actual={actual:>10,} "
                    f"expected={expected:>10,}  {status}"
                )

            checks = {
                "pageview orphan sessions": """
                    SELECT COUNT(*)
                    FROM website_pageviews p
                    LEFT JOIN website_sessions s
                      ON p.website_session_id = s.website_session_id
                    WHERE s.website_session_id IS NULL
                """,
                "order orphan sessions": """
                    SELECT COUNT(*)
                    FROM canonical_orders o
                    LEFT JOIN website_sessions s
                      ON o.website_session_id = s.website_session_id
                    WHERE s.website_session_id IS NULL
                """,
                "item orphan orders": """
                    SELECT COUNT(*)
                    FROM canonical_order_items oi
                    LEFT JOIN canonical_orders o ON oi.order_id = o.order_id
                    WHERE o.order_id IS NULL
                """,
                "refund orphan items": """
                    SELECT COUNT(*)
                    FROM canonical_order_item_refunds r
                    LEFT JOIN canonical_order_items oi
                      ON r.order_item_id = oi.order_item_id
                    WHERE oi.order_item_id IS NULL
                """,
            }

            print("\nReferential-integrity checks:")
            all_fk_ok = True
            for label, query in checks.items():
                cur.execute(query)
                value = cur.fetchone()[0]
                all_fk_ok = all_fk_ok and value == 0
                status = "PASS" if value == 0 else "CHECK"
                print(f"{label:28} {value:>8,}  {status}")

            if all_counts_ok and all_fk_ok:
                print("\nOVERALL: PASS")
            else:
                print("\nOVERALL: CHECK")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
