from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import config as cfg

REQUIRED_CSVS = [
    "website_sessions.csv",
    "website_pageviews.csv",
    "orders.csv",
    "order_items.csv",
    "order_item_refunds.csv",
    "products.csv",
]


def main():
    dataset_dir = cfg.SESSION1_DIR / "datasets"
    parquet = cfg.SESSION1_RESULTS / "session_journey_metrics.parquet"

    missing_csv = [name for name in REQUIRED_CSVS if not (dataset_dir / name).exists()]
    dataset_ok = dataset_dir.exists() and not missing_csv
    parquet_ok = parquet.exists()

    if not dataset_ok:
        raise RuntimeError(
            f"Session 1 dataset path is incomplete: {dataset_dir}; missing={missing_csv}"
        )
    if not parquet_ok:
        raise RuntimeError(f"Session 1 batch output not found: {parquet}")

    df = pd.read_parquet(parquet)
    expected_cols = {
        "website_session_id", "pageview_count", "session_duration_seconds",
        "converted", "order_revenue_usd", "gross_profit_usd",
    }
    missing_cols = sorted(expected_cols - set(df.columns))
    if missing_cols:
        raise RuntimeError(f"Session 1 parquet missing columns: {missing_cols}")

    report = {
        "session1_dataset_path": str(dataset_dir.resolve()),
        "dataset_path_resolved": True,
        "required_csv_files": REQUIRED_CSVS,
        "session1_batch_output": str(parquet.resolve()),
        "batch_output_exists_and_loads": True,
        "group_count": int(len(df)),
        "aggregate_order_revenue_usd": float(df["order_revenue_usd"].sum()),
        "aggregate_gross_profit_usd": float(df["gross_profit_usd"].sum()),
        "partition_key_inherited": cfg.PARTITION_KEY,
        "event_time_field": cfg.EVENT_TIME,
        "passed": True,
    }
    (cfg.RESULTS / "handover_verification.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )

    print("RETAILMETRICS SESSION 1 HANDOVER VERIFICATION")
    print("=" * 72)
    print(f"dataset path            : {dataset_dir.resolve()}")
    print("source dataset files    : PASS")
    print(f"Session 1 batch output  : {parquet.resolve()}")
    print(f"group count             : {len(df):,}")
    print(f"order revenue total     : ${df['order_revenue_usd'].sum():,.2f}")
    print(f"gross profit total      : ${df['gross_profit_usd'].sum():,.2f}")
    print(f"partition key inherited : {cfg.PARTITION_KEY}")
    print(f"event-time field        : {cfg.EVENT_TIME}")
    print("OVERALL                 : PASS")

if __name__ == "__main__":
    main()
