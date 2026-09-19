from __future__ import annotations

import csv
import os
from pathlib import Path

import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# When this folder is placed at:
# session1_parallel_compute/postgresql_migration/
# the default dataset folder is:
# session1_parallel_compute/datasets/
CSV_DIR = Path(os.getenv("CSV_DIR", "../datasets"))
if not CSV_DIR.is_absolute():
    CSV_DIR = (BASE_DIR / CSV_DIR).resolve()

FILES = [
    ("website_sessions.csv", "website_sessions"),
    ("products.csv", "products"),
    ("website_pageviews.csv", "website_pageviews"),
    ("orders.csv", "orders"),
    ("order_items.csv", "order_items"),
    ("order_item_refunds.csv", "order_item_refunds"),
]


def connect():
    return psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=int(os.getenv("PGPORT", "5432")),
        dbname=os.getenv("PGDATABASE", "retailmetrics"),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", ""),
    )


def run_schema(conn):
    schema_file = BASE_DIR / "schema.sql"
    if not schema_file.exists():
        raise FileNotFoundError(f"schema.sql was not found in {BASE_DIR}")

    with schema_file.open("r", encoding="utf-8") as f:
        schema = f.read()

    with conn.cursor() as cur:
        cur.execute(schema)
    conn.commit()


def get_csv_columns(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return next(csv.reader(f))


def copy_csv(conn, csv_path: Path, table_name: str):
    columns = get_csv_columns(csv_path)
    statement = sql.SQL(
        "COPY {} ({}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE, NULL '')"
    ).format(
        sql.Identifier(table_name),
        sql.SQL(", ").join(sql.Identifier(column) for column in columns),
    )

    with conn.cursor() as cur, csv_path.open(
        "r", encoding="utf-8-sig", newline=""
    ) as f:
        cur.copy_expert(statement.as_string(conn), f)
    conn.commit()


def truncate_tables(conn):
    tables = [
        "order_item_refunds",
        "order_items",
        "orders",
        "website_pageviews",
        "products",
        "website_sessions",
    ]

    with conn.cursor() as cur:
        cur.execute(
            sql.SQL("TRUNCATE TABLE {} RESTART IDENTITY CASCADE").format(
                sql.SQL(", ").join(sql.Identifier(table) for table in tables)
            )
        )
    conn.commit()


def main():
    print("RetailMetrics CSV -> PostgreSQL Migration")
    print(f"CSV folder: {CSV_DIR}")

    missing = [filename for filename, _ in FILES if not (CSV_DIR / filename).exists()]
    if missing:
        print("\nMissing CSV files:")
        for filename in missing:
            print(f"  - {filename}")
        raise SystemExit("\nChoose the correct CSV folder in the RetailMetrics GUI.")

    conn = connect()
    try:
        print("\n[1/3] Creating RetailMetrics schema...")
        run_schema(conn)

        print("[2/3] Clearing target tables...")
        truncate_tables(conn)

        print("[3/3] Importing CSV files...")
        for filename, table in FILES:
            print(f"  {filename} -> {table} ...", end=" ", flush=True)
            copy_csv(conn, CSV_DIR / filename, table)

            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table))
                )
                count = cur.fetchone()[0]
            print(f"{count:,} rows")

        print("\nMigration completed successfully.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
