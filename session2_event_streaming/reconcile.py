from __future__ import annotations
import json
import pandas as pd

import config as cfg
from db import connect

TOL = 1e-6

def load_stream():
    path = cfg.RESULTS / "stream_session_metrics.csv"
    if not path.exists():
        raise RuntimeError(
            "stream_session_metrics.csv not found. Run the consumers first."
        )
    return pd.read_csv(path)

def load_session1_reference():
    parquet = cfg.SESSION1_RESULTS / "session_journey_metrics.parquet"
    if parquet.exists():
        return pd.read_parquet(parquet), "Session 1 parquet"

    # Fallback: reconstruct the exact Session 1-equivalent result from PostgreSQL.
    conn = connect()
    try:
        query = """
        WITH p AS (
            SELECT website_session_id,
                   COUNT(*) AS pageview_count,
                   EXTRACT(EPOCH FROM (MAX(created_at)-MIN(created_at)))
                       AS session_duration_seconds
            FROM website_pageviews
            GROUP BY website_session_id
        )
        SELECT
            p.website_session_id,
            p.pageview_count,
            p.session_duration_seconds,
            CASE WHEN o.order_id IS NULL THEN 0 ELSE 1 END AS converted,
            COALESCE(o.price_usd,0)::double precision AS order_revenue_usd,
            COALESCE(o.price_usd-o.cogs_usd,0)::double precision AS gross_profit_usd
        FROM p
        LEFT JOIN orders o USING (website_session_id)
        ORDER BY p.website_session_id
        """
        return (
            pd.read_sql_query(query, conn),
            "PostgreSQL Session 1-equivalent reference",
        )
    finally:
        conn.close()

def main():
    stream = load_stream().sort_values("website_session_id").reset_index(drop=True)
    ref, ref_name = load_session1_reference()
    ref = ref.sort_values("website_session_id").reset_index(drop=True)

    keys_equal = set(stream.website_session_id) == set(ref.website_session_id)
    count_diff = abs(len(stream) - len(ref))

    merged = ref.merge(
        stream,
        on="website_session_id",
        suffixes=("_batch", "_stream"),
        how="outer",
        indicator=True,
    )

    structure_ok = bool((merged["_merge"] == "both").all())

    exact_fields = ["pageview_count", "converted"]
    approx_fields = [
        "session_duration_seconds",
        "order_revenue_usd",
        "gross_profit_usd",
    ]

    max_diffs = {}
    exact_ok = True
    approx_ok = True

    for field in exact_fields:
        a = merged[f"{field}_batch"].fillna(-999999)
        b = merged[f"{field}_stream"].fillna(-888888)
        diff = float((a - b).abs().max())
        max_diffs[field] = diff
        exact_ok = exact_ok and diff == 0.0

    for field in approx_fields:
        a = merged[f"{field}_batch"].fillna(0).astype(float)
        b = merged[f"{field}_stream"].fillna(0).astype(float)
        diff = float((a - b).abs().max())
        max_diffs[field] = diff
        approx_ok = approx_ok and diff <= TOL

    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT consumer_name,
                       GREATEST(
                           0,
                           (
                               SELECT COALESCE(MAX(log_offset),0)
                               FROM retailmetrics_event_log
                               WHERE topic=%s
                           ) - last_offset
                       ) AS lag
                FROM retailmetrics_consumer_offsets
                WHERE topic=%s
                  AND consumer_name IN (%s,%s,%s)
                """,
                (
                    cfg.TOPIC,
                    cfg.TOPIC,
                    cfg.PROJECTOR_GROUP,
                    cfg.AUDIT_GROUP,
                    cfg.REFUND_GROUP,
                ),
            )
            lags = {name: int(lag) for name, lag in cur.fetchall()}
    finally:
        conn.close()

    lag_ok = all(
        lags.get(group, 1) == 0
        for group in (
            cfg.PROJECTOR_GROUP,
            cfg.AUDIT_GROUP,
            cfg.REFUND_GROUP,
        )
    )

    passed = (
        keys_equal
        and structure_ok
        and count_diff == 0
        and exact_ok
        and approx_ok
        and lag_ok
    )

    report = {
        "reference": ref_name,
        "batch_groups": len(ref),
        "stream_groups": len(stream),
        "group_sets_identical": keys_equal,
        "count_difference": count_diff,
        "max_differences": max_diffs,
        "tolerance": TOL,
        "consumer_lag": lags,
        "passed": passed,
    }

    (cfg.RESULTS / "reconciliation_report.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print("RETAILMETRICS RECONCILIATION AGAINST SESSION 1")
    print("=" * 72)
    print(f"reference             : {ref_name}")
    print(f"batch groups          : {len(ref):,}")
    print(f"stream groups         : {len(stream):,}")
    print(f"group sets identical  : {keys_equal}")
    print(f"count difference      : {count_diff}")
    for field, diff in max_diffs.items():
        print(f"max diff {field:24}: {diff:.12g}")
    print(f"tolerance             : {TOL}")
    print(f"consumer lag          : {lags}")
    print(f"\nOVERALL: {'PASS' if passed else 'FAIL'}")

    if not passed:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
