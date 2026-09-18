# Reconciliation

Session 3 independently queries the canonical PostgreSQL baseline and compares its result with existing evidence files. It does not import or execute Session 1 or Session 2 Python modules.

The per-session comparison covers `website_session_id`, pageview count, duration, conversion, order revenue, and gross profit for all sessions. Identifier storage widths may differ (`int32` in a Parquet artifact versus `int64` from PostgreSQL), so equality is based on integer values. Counts and discrete metrics must match exactly; duration uses a small floating-point tolerance; monetary values are converted to integer cents for exact comparison.

The refund comparison checks the canonical refund count and total against Session 2's consumer summary. Product performance is reported as a Session 3 result but is not falsely reconciled to Sessions 1 or 2 because they do not publish that same metric.
