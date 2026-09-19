RetailMetrics - CSV to PostgreSQL Migration

Project title:
RetailMetrics: An E-Commerce Analytics System for Sales, Website Performance, and Revenue Intelligence

AUTHORITATIVE LOCATION

MIT261-UTTO/session1_parallel_compute/postgresql_migration/

This is the repository's only authoritative CSV-to-PostgreSQL migration package.

Purpose
- Creates PostgreSQL tables for all six Toy Store E-Commerce CSV files.
- Preserves the primary-key and foreign-key relationships.
- Uses PostgreSQL COPY for faster bulk loading.
- Adds indexes useful for session, timestamp, order, and product access.
- Includes verification for expected row counts and orphan foreign keys.

Files
- schema.sql
- migrate_csv_to_postgres.py
- verify_migration.py
- requirements.txt
- .env.example
- RUN_MIGRATION.bat
- VERIFY_MIGRATION.bat

SETUP

1. Create the database in PostgreSQL:
   CREATE DATABASE retailmetrics;

2. Open a terminal in:
   MIT261-UTTO/session1_parallel_compute/postgresql_migration/

3. Install dependencies:
   pip install -r requirements.txt

4. Copy:
   .env.example
   to:
   .env

5. Edit .env with your PostgreSQL username and password.

6. Keep CSV_DIR=../datasets when the dataset folder is located at:
   MIT261-UTTO/session1_parallel_compute/datasets/

7. Run:
   RUN_MIGRATION.bat

8. Verify:
   VERIFY_MIGRATION.bat

The Python migration and verification scripts load settings from the .env file
in this directory. The RetailMetrics Tkinter GUI can also pass these settings
directly through process environment variables.

Expected row counts
- website_sessions: 472,871
- website_pageviews: 1,188,124
- orders: 32,313
- order_items: 40,025
- order_item_refunds: 1,731
- products: 4

Repository layout

MIT261-UTTO/
  RetailMetricsGUI/
    gui.py
    GUI_README.txt
    RUN_GUI.bat

  session1_parallel_compute/
    datasets/
      website_sessions.csv
      website_pageviews.csv
      orders.csv
      order_items.csv
      order_item_refunds.csv
      products.csv
    postgresql_migration/
      .env.example
      migrate_csv_to_postgres.py
      README_MIGRATION.txt
      requirements.txt
      RUN_MIGRATION.bat
      schema.sql
      VERIFY_MIGRATION.bat
      verify_migration.py
    results/

Important
- The migration truncates and reloads the six RetailMetrics public tables each time.
- It does not modify the source CSV files.
- It does not create or migrate the separate RetailMetricsWeb webapp schema.
- Do not run the migration when the intent is only to apply RetailMetricsWeb's
  additive webapp migrations.
