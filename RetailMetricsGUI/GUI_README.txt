RetailMetrics - Session 1 Parallel Compute Console

This Tkinter desktop GUI provides a visual front end for the existing Session 1
parallel-compute pipeline and PostgreSQL migration utilities.

Current layout:

MIT261-UTTO/
  RetailMetricsGUI/
    gui.py
    GUI_README.txt
    RUN_GUI.bat

  session1_parallel_compute/
    profile_files.py
    load_and_join.py
    partition_strategy.py
    sequential_baseline.py
    parallel_compute.py
    benchmark.py
    partition_analysis.py
    config.py
    datasets/
    results/
    postgresql_migration/
      .env.example
      migrate_csv_to_postgres.py
      README_MIGRATION.txt
      requirements.txt
      RUN_MIGRATION.bat
      schema.sql
      VERIFY_MIGRATION.bat
      verify_migration.py

The GUI automatically finds session1_parallel_compute when that folder is beside
RetailMetricsGUI.


CSV -> PostgreSQL TAB

The GUI includes a dedicated "CSV -> PostgreSQL" tab. It supports:
- PostgreSQL host, port, database, user, and password fields
- CSV folder selection
- Test connection
- Migrate CSV files
- Verify migration
- Refresh current table data
- Open the authoritative migration folder
- Live migration output in the Console tab

The authoritative migration path is:

MIT261-UTTO/session1_parallel_compute/postgresql_migration/

The GUI passes the selected PostgreSQL and CSV settings to the migration scripts
through process environment variables. It does not use root-level migration
copies.
