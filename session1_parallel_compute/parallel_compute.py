import json
import sys
import time
import pandas as pd
import config as cfg
from sequential_baseline import compute as baseline_compute
from load_and_join import build_working_dataset

def build_joined(spark, verbose=True):
    from pyspark.sql import functions as F

    pageviews = (
        spark.read.option("header", True).option("inferSchema", True)
        .csv(str(cfg.FILES["website_pageviews"]))
        .withColumnRenamed("created_at", "pageview_created_at")
        .withColumn("pageview_created_at", F.to_timestamp("pageview_created_at"))
    )

    sessions = (
        spark.read.option("header", True).option("inferSchema", True)
        .csv(str(cfg.FILES["website_sessions"]))
        .withColumnRenamed("created_at", "session_created_at")
        .withColumn("session_created_at", F.to_timestamp("session_created_at"))
    )

    orders = (
        spark.read.option("header", True).option("inferSchema", True)
        .csv(str(cfg.FILES["orders"]))
        .withColumnRenamed("created_at", "order_created_at")
        .withColumnRenamed("price_usd", "order_revenue_usd")
        .withColumnRenamed("cogs_usd", "order_cogs_usd")
        .withColumn("order_created_at", F.to_timestamp("order_created_at"))
    )

    before = pageviews.count()
    t0 = time.perf_counter()

    # The session table is relatively large, so allow Spark to choose a shuffle strategy.
    # Orders is much smaller, so broadcast it.
    joined = (
        pageviews
        .join(sessions, on="website_session_id", how="inner")
        .join(F.broadcast(orders), on="website_session_id", how="left")
        .withColumn("converted", F.when(F.col("order_id").isNotNull(), 1).otherwise(0))
        .withColumn(
            "gross_profit_usd",
            F.col("order_revenue_usd") - F.col("order_cogs_usd"),
        )
        .cache()
    )

    after = joined.count()
    elapsed = time.perf_counter() - t0

    if before != after:
        raise AssertionError(f"Spark join changed pageview rows: {before} -> {after}")

    plan = joined._jdf.queryExecution().executedPlan().toString()

    info = {
        "rows_before": int(before),
        "rows_after": int(after),
        "join_seconds": elapsed,
        "broadcast_hash_join_occurrences": plan.count("BroadcastHashJoin"),
        "sort_merge_join_occurrences": plan.count("SortMergeJoin"),
    }

    if verbose:
        cfg.banner("SPARK JOIN")
        print(f"Rows before join : {before:,}")
        print(f"Rows after join  : {after:,}")
        print(f"Difference       : {after - before:,}")
        print(f"Join/cache time  : {elapsed:.4f} s")
        print(f"BroadcastHashJoin occurrences: {info['broadcast_hash_join_occurrences']}")
        print(f"SortMergeJoin occurrences    : {info['sort_merge_join_occurrences']}")

    return joined, info

def compute_parallel(joined, partitions):
    from pyspark.sql import functions as F

    partitioned = joined.repartition(partitions, cfg.PARTITION_KEY)

    result = (
        partitioned
        .groupBy(cfg.PARTITION_KEY)
        .agg(
            F.count(F.lit(1)).alias("pageview_count"),
            F.min("pageview_created_at").alias("first_pageview"),
            F.max("pageview_created_at").alias("last_pageview"),
            F.max("converted").alias("converted"),
            F.max(F.coalesce(F.col("order_revenue_usd"), F.lit(0.0))).alias("order_revenue_usd"),
            F.max(F.coalesce(F.col("gross_profit_usd"), F.lit(0.0))).alias("gross_profit_usd"),
        )
        .withColumn(
            "session_duration_seconds",
            F.unix_timestamp("last_pageview") - F.unix_timestamp("first_pageview"),
        )
        .select(
            cfg.PARTITION_KEY,
            "pageview_count",
            "session_duration_seconds",
            "converted",
            "order_revenue_usd",
            "gross_profit_usd",
        )
    )

    return partitioned, result

def validate(result, baseline):
    par = result.orderBy(cfg.PARTITION_KEY).toPandas()
    base = baseline.sort_values(cfg.PARTITION_KEY).reset_index(drop=True)

    comp = par.merge(
        base,
        on=cfg.PARTITION_KEY,
        suffixes=("_par", "_base"),
        validate="one_to_one",
    )

    diffs = {
        "pageview_count": float(
            (comp["pageview_count_par"] - comp["pageview_count_base"]).abs().max()
        ),
        "session_duration_seconds": float(
            (comp["session_duration_seconds_par"] - comp["session_duration_seconds_base"]).abs().max()
        ),
        "converted": float(
            (comp["converted_par"] - comp["converted_base"]).abs().max()
        ),
        "order_revenue_usd": float(
            (comp["order_revenue_usd_par"] - comp["order_revenue_usd_base"]).abs().max()
        ),
        "gross_profit_usd": float(
            (comp["gross_profit_usd_par"] - comp["gross_profit_usd_base"]).abs().max()
        ),
    }

    assert len(par) == len(base)
    assert diffs["pageview_count"] == 0
    assert diffs["session_duration_seconds"] == 0
    assert diffs["converted"] == 0
    assert diffs["order_revenue_usd"] <= cfg.TOLERANCE
    assert diffs["gross_profit_usd"] <= cfg.TOLERANCE

    return {
        "parallel_groups": int(len(par)),
        "baseline_groups": int(len(base)),
        "max_differences": diffs,
        "tolerance": cfg.TOLERANCE,
        "result": "PASS",
    }

def main():
    cfg.require_files()
    cfg.banner("SESSION 1 - PARALLEL COMPUTE")

    working_pd, _ = build_working_dataset(verbose=False, write=True)
    baseline = baseline_compute(working_pd)

    spark = cfg.build_spark()
    try:
        joined, join_info = build_joined(spark)

        t0 = time.perf_counter()
        partitioned, result = compute_parallel(joined, cfg.CHOSEN_PARTITIONS)
        groups = result.count()
        elapsed = time.perf_counter() - t0

        print(f"\nConfigured partitions : {cfg.CHOSEN_PARTITIONS}")
        print(f"Actual partitions     : {partitioned.rdd.getNumPartitions()}")
        print(f"Result groups         : {groups:,}")
        print(f"Parallel time         : {elapsed:.4f} s")

        validation = validate(result, baseline)

        print("\nCORRECTNESS")
        for k, v in validation.items():
            print(f"{k}: {v}")

        result.orderBy(cfg.PARTITION_KEY).toPandas().to_parquet(
            cfg.OUT_FINAL, index=False
        )

        cfg.OUT_VALIDATION.write_text(
            json.dumps(
                {
                    "join": join_info,
                    "configured_partitions": cfg.CHOSEN_PARTITIONS,
                    "actual_partitions": partitioned.rdd.getNumPartitions(),
                    "parallel_seconds": elapsed,
                    "validation": validation,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        print(f"\nWrote {cfg.OUT_FINAL}")
        print(f"Wrote {cfg.OUT_VALIDATION}")
        return 0
    finally:
        spark.stop()

if __name__ == "__main__":
    sys.exit(main())
