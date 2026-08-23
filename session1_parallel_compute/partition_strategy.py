import json
import sys
import pandas as pd
import config as cfg
from load_and_join import build_working_dataset

def describe_key(df, key):
    counts = df.groupby(key, dropna=False).size().sort_values()
    return {
        "key": key,
        "distinct": int(len(counts)),
        "min": int(counts.min()),
        "median": float(counts.median()),
        "max": int(counts.max()),
        "mean": float(counts.mean()),
        "skew_ratio_max_min": float(counts.max() / counts.min()) if counts.min() else None,
        "largest_key": str(counts.idxmax()),
    }

def main():
    working, _ = build_working_dataset(verbose=False, write=False)
    cfg.banner("SESSION 1 - PARTITION STRATEGY")

    candidates = ["website_session_id", "user_id", "utm_source", "device_type"]
    reports = {}

    for key in candidates:
        r = describe_key(working, key)
        reports[key] = r
        print(
            f"{key}: distinct={r['distinct']:,} | "
            f"min={r['min']:,} | median={r['median']:.1f} | "
            f"max={r['max']:,} | skew={r['skew_ratio_max_min']:.2f}:1"
        )

    final = {
        "chosen_partition_key": cfg.PARTITION_KEY,
        "entity_owner": "WebsiteSession (website_sessions.csv)",
        "relationship": "WebsiteSession 1 -> many WebsitePageviews",
        "predicted_records_per_key": reports["website_session_id"],
        "workload": (
            "Compute pageview count, session duration, conversion flag, "
            "order revenue, and gross profit per website_session_id."
        ),
        "candidates": reports,
    }

    cfg.OUT_PARTITION_STRATEGY.write_text(
        json.dumps(final, indent=2), encoding="utf-8"
    )
    print(f"\nChosen key: {cfg.PARTITION_KEY}")
    print(f"Wrote {cfg.OUT_PARTITION_STRATEGY}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
