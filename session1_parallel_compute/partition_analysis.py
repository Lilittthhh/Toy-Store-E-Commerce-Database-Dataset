import csv
import sys
import config as cfg
from parallel_compute import build_joined

def main():
    cfg.require_files()
    cfg.banner("SESSION 1 - PARTITION BALANCE")

    spark = cfg.build_spark()
    try:
        joined, _ = build_joined(spark, verbose=False)
        partitioned = joined.repartition(cfg.CHOSEN_PARTITIONS, cfg.PARTITION_KEY)

        sizes = (
            partitioned.rdd
            .mapPartitionsWithIndex(
                lambda idx, rows: [(idx, sum(1 for _ in rows))]
            )
            .collect()
        )
        sizes = sorted(sizes)

        total = sum(n for _, n in sizes)
        target = total / cfg.CHOSEN_PARTITIONS

        rows = []
        for idx, count in sizes:
            ratio = count / target if target else 0
            rows.append({
                "partition": idx,
                "predicted_even_count": round(target, 2),
                "actual_count": count,
                "ratio_to_even": round(ratio, 4),
            })
            print(
                f"partition_{idx}: predicted={target:,.1f} | "
                f"actual={count:,} | ratio={ratio:.4f}"
            )

        with open(cfg.OUT_PARTITIONS, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=rows[0].keys())
            w.writeheader()
            w.writerows(rows)

        print(f"\nWrote {cfg.OUT_PARTITIONS}")
        return 0
    finally:
        spark.stop()

if __name__ == "__main__":
    sys.exit(main())
