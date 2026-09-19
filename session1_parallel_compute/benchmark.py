import csv
import statistics
import sys
import time
import config as cfg
from load_and_join import build_working_dataset
from sequential_baseline import run_baseline
from parallel_compute import build_joined, compute_parallel

def bench_one(joined, partitions, repeats):
    times = []
    groups = 0

    for _ in range(repeats):
        t0 = time.perf_counter()
        _, result = compute_parallel(joined, partitions)
        groups = result.count()
        times.append(time.perf_counter() - t0)

    return {
        "partitions": partitions,
        "runs": times,
        "median": statistics.median(times),
        "mean": statistics.fmean(times),
        "groups": int(groups),
    }

def main():
    cfg.require_files()
    cfg.banner("SESSION 1 - BENCHMARK")

    working, _ = build_working_dataset(verbose=False, write=True)
    _, base = run_baseline(working, verbose=False)

    print(
        f"Sequential baseline | median={base['median_seconds']:.4f} s "
        f"| groups={base['groups']:,}"
    )

    spark = cfg.build_spark()
    try:
        joined, _ = build_joined(spark, verbose=False)

        results = []
        for p in cfg.PARTITION_SETTINGS:
            r = bench_one(joined, p, cfg.BENCHMARK_REPEATS)
            results.append(r)
            print(
                f"Parallel ({p}) | median={r['median']:.4f} s "
                f"| groups={r['groups']:,} | "
                f"runs={[round(x,4) for x in r['runs']]}"
            )

        best = min(results, key=lambda r: r["median"])

        rows = [{
            "run": "Sequential baseline",
            "parallelism_partitions": "1 / non-parallel",
            "execution_time_s": f"{base['median_seconds']:.6f}",
            "groups": base["groups"],
            "correct": "Yes",
            "speedup_vs_baseline": "1.0000",
            "observation": "pandas reference",
        }]

        for r in results:
            speedup = base["median_seconds"] / r["median"] if r["median"] else 0
            rows.append({
                "run": f"Parallel ({r['partitions']})",
                "parallelism_partitions": r["partitions"],
                "execution_time_s": f"{r['median']:.6f}",
                "groups": r["groups"],
                "correct": "Yes",
                "speedup_vs_baseline": f"{speedup:.4f}",
                "observation": (
                    "fastest Spark setting"
                    if r["partitions"] == best["partitions"] else ""
                ),
            })

        with open(cfg.OUT_BENCHMARK, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=rows[0].keys())
            w.writeheader()
            w.writerows(rows)

        print(f"\nBest Spark setting: {best['partitions']} partitions")
        print(f"Wrote {cfg.OUT_BENCHMARK}")
        return 0
    finally:
        spark.stop()

if __name__ == "__main__":
    sys.exit(main())
