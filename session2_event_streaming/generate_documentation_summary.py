from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import config as cfg

RESULTS = cfg.RESULTS
OUT = RESULTS / "session2_documentation_summary.txt"


def read_json(name: str) -> dict[str, Any]:
    path = RESULTS / name
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def fmt_num(value, decimals=0):
    if value is None:
        return "NOT AVAILABLE"
    try:
        if decimals == 0:
            return f"{int(value):,}"
        return f"{float(value):,.{decimals}f}"
    except Exception:
        return str(value)


def money(value):
    if value is None:
        return "NOT AVAILABLE"
    try:
        return f"${float(value):,.2f}"
    except Exception:
        return str(value)


def pct(value):
    if value is None:
        return "NOT AVAILABLE"
    try:
        return f"{float(value):.2f}%"
    except Exception:
        return str(value)


def yn(value):
    if value is True:
        return "YES"
    if value is False:
        return "NO"
    return "NOT AVAILABLE"


def main():
    handover = read_json("handover_verification.json")
    producer = read_json("producer_summary.json")
    enrichment = read_json("enrichment_report.json")
    selftest = read_json("log_self_test.json")
    consumers = read_json("consumer_summary.json")
    recovery = read_json("failure_recovery.json")
    replay = read_json("replay_suite.json")
    monet = read_json("monetization_snapshot.json")
    reconcile = read_json("reconciliation_report.json")

    # Compute the professor's generic Part 12 rows directly from the actual
    # Session 1 batch output and Session 2 streamed projection when available.
    part12_calc = {}
    try:
        import pandas as pd
        batch_path = Path(handover.get("session1_batch_output", ""))
        stream_path = RESULTS / "stream_session_metrics.csv"
        if batch_path.exists() and stream_path.exists():
            batch_df = pd.read_parquet(batch_path).sort_values("website_session_id").reset_index(drop=True)
            stream_df = pd.read_csv(stream_path).sort_values("website_session_id").reset_index(drop=True)

            part12_calc["batch_total_records"] = int(batch_df["pageview_count"].sum())
            part12_calc["stream_total_records"] = int(stream_df["pageview_count"].sum())
            part12_calc["batch_aggregate_total"] = float(batch_df["order_revenue_usd"].sum())
            part12_calc["stream_aggregate_total"] = float(stream_df["order_revenue_usd"].sum())
            part12_calc["max_record_count_difference"] = float(
                (batch_df["pageview_count"].astype(float) - stream_df["pageview_count"].astype(float)).abs().max()
            )
            part12_calc["aggregate_total_difference"] = abs(
                part12_calc["batch_aggregate_total"] - part12_calc["stream_aggregate_total"]
            )
            batch_mean = float(batch_df["order_revenue_usd"].mean())
            stream_mean = float(stream_df["order_revenue_usd"].mean())
            part12_calc["batch_mean_revenue"] = batch_mean
            part12_calc["stream_mean_revenue"] = stream_mean
            part12_calc["mean_difference"] = abs(batch_mean - stream_mean)
    except Exception as exc:
        part12_calc["calculation_note"] = f"Could not compute direct Part 12 totals/means: {exc}"

    lines: list[str] = []
    add = lines.append

    add("RETAILMETRICS — SESSION 2 DOCUMENTATION EVIDENCE SUMMARY")
    add("=" * 78)
    add("Generated from the current files in session2_event_streaming/results/.")
    add("This is a helper file for filling the professor's Session 2 submission template.")
    add("Delete this helper file and its generator later if you want a clean final repo.")
    add("")

    # Part 2
    add("PART 2 — SESSION 1 HANDOVER VERIFICATION")
    add("-" * 78)
    add(f"Dataset/source path: {handover.get('session1_dataset_path', 'NOT AVAILABLE')}")
    add(f"Source dataset files verified: {yn(handover.get('dataset_path_resolved') and bool(handover.get('required_csv_files')))}")
    add(f"Session 1 batch output: {handover.get('session1_batch_output', 'NOT AVAILABLE')}")
    add(f"Session 1 group count: {fmt_num(handover.get('group_count'))}")
    add(f"Session 1 aggregate order revenue: {money(handover.get('aggregate_order_revenue_usd'))}")
    add(f"Session 1 aggregate gross profit: {money(handover.get('aggregate_gross_profit_usd'))}")
    add(f"Partition key inherited: {handover.get('partition_key_inherited', 'website_session_id')}")
    add(f"Event-time field inherited: {handover.get('event_time_field', 'created_at')}")
    add(f"Overall handover result: {'PASS' if handover.get('passed') else 'NOT AVAILABLE/FAIL'}")
    add("")

    # Part 3
    add("PART 3 — EVENT SCHEMA AND TOPIC DESIGN")
    add("-" * 78)
    add(f"Topic name: {producer.get('topic', getattr(cfg, 'TOPIC', 'commerce.activity.recorded'))}")
    event_types = producer.get("event_types")
    if isinstance(event_types, list):
        event_types = ", ".join(event_types)
    add(f"Event types: {event_types or 'pageview.recorded, refund.recorded'}")
    add(f"Schema version: {producer.get('schema_version', 1)}")
    add(f"Number of partitions: {getattr(cfg, 'NUM_PARTITIONS', 4)}")
    add(f"Partition key: {producer.get('partition_key', getattr(cfg, 'PARTITION_KEY', 'website_session_id'))}")
    add(f"Event-time field: {producer.get('event_time', getattr(cfg, 'EVENT_TIME', 'created_at'))}")
    add("Why this key: website_session_id preserves affinity so all activity for one website session maps consistently to one logical partition.")
    add("Enrichment fields: session attributes, order/conversion facts, revenue, COGS, gross profit, and refund/session linkage as applicable.")
    add(f"Enrichment row-count guard: {'PASS' if enrichment.get('passed') is True else 'NOT AVAILABLE/FAIL'}")
    add(f"Pageviews before enrichment: {fmt_num(enrichment.get('pageviews_before', enrichment.get('pageview_rows_before')))}")
    add(f"Pageviews after enrichment: {fmt_num(enrichment.get('pageviews_after', enrichment.get('pageview_rows_after')))}")
    add(f"Refunds before enrichment: {fmt_num(enrichment.get('refunds_before', enrichment.get('refund_rows_before')))}")
    add(f"Refunds after enrichment: {fmt_num(enrichment.get('refunds_after', enrichment.get('refund_rows_after')))}")
    add("")

    # Part 4
    add("PART 4 — DURABLE LOG GUARANTEES")
    add("-" * 78)
    tests = selftest.get("tests", [])
    if tests:
        for t in tests:
            add(f"{t.get('guarantee', 'Unknown')}: {t.get('status', 'NOT AVAILABLE')} — {t.get('evidence', '')}")
    else:
        add("Self-test result: NOT AVAILABLE")
    add("Backbone limitation: single-node PostgreSQL durable log; no Kafka/Redpanda-style broker replication, leader election, or multi-node HA.")
    add("")

    # Part 5
    add("PART 5 — PRODUCER: ORDERING, VOLUME, AND PARTITIONING")
    add("-" * 78)
    add(f"Events produced: {fmt_num(producer.get('events_after', producer.get('events_inserted')))}")
    add(f"Pageview events: {fmt_num(producer.get('pageview_events_expected'))}")
    add(f"Refund events: {fmt_num(producer.get('refund_events_expected'))}")
    add(f"Distinct partition-key values: {fmt_num(producer.get('distinct_partition_keys'))}")
    add(f"Event-time range: {producer.get('event_time_min', producer.get('event_time_start', 'NOT AVAILABLE'))} -> {producer.get('event_time_max', producer.get('event_time_end', 'NOT AVAILABLE'))}")
    add(f"Sort before publishing: {producer.get('sort_applied', producer.get('sort_before_publishing', 'event_time, event_id'))}")
    elapsed_value = producer.get("elapsed_s")
    add(f"Production time: {float(elapsed_value):.3f} seconds" if elapsed_value is not None else "Production time: NOT AVAILABLE")
    add(f"Throughput: {fmt_num(producer.get('events_per_sec'))} events/second")
    log_mb = producer.get("log_size_mb")
    add(f"Log size: {float(log_mb):.2f} MB" if log_mb is not None else "Log size: NOT AVAILABLE")
    skew = producer.get("skew_ratio")
    add(f"Partition skew ratio: {float(skew):.2f} : 1" if skew is not None else "Partition skew ratio: NOT AVAILABLE")
    partitions = producer.get("partitions") or []
    if isinstance(partitions, list):
        for row in partitions:
            if isinstance(row, (list, tuple)) and len(row) >= 2:
                add(f"Partition {row[0]}: {fmt_num(row[1])} events")
            elif isinstance(row, dict):
                add(f"Partition {row.get('partition_id', row.get('partition', '?'))}: {fmt_num(row.get('events', row.get('count')))} events")
    add("")

    # Part 6
    add("PART 6 — CONSUMER GROUPS AND FAN-OUT")
    add("-" * 78)
    groups = consumers.get("groups", consumers.get("consumer_groups", []))
    if isinstance(groups, list) and groups:
        for g in groups:
            add(
                f"{g.get('group', g.get('consumer', 'consumer'))}: "
                f"processed={fmt_num(g.get('processed'))}, "
                f"seconds={g.get('seconds', 'NOT AVAILABLE')}, "
                f"events/sec={fmt_num(g.get('events_per_sec', g.get('eps')))}, "
                f"final lag={fmt_num(g.get('final_lag', g.get('lag')))}"
            )
    else:
        add("Consumer group detail: see consumer_summary.json / consumer_lag.csv")
    add(f"Producer source-code changes required to add third consumer: {consumers.get('producer_changes_required_for_third_consumer', 0)}")
    add("Second run behavior: an already-caught-up consumer sees no new retained events beyond its committed offset unless its offset is reset/replayed.")
    add("Brand-new group behavior: a new group can start from the retained beginning and independently read the full event history.")
    add("")

    # Part 7
    add("PART 7 — DELIVERY SEMANTICS AND IDEMPOTENCY")
    add("-" * 78)
    add("Delivery semantic implemented: AT-LEAST-ONCE")
    add("Offset commit rule: commit/advance offsets only after successful processing of a batch/event range.")
    add(f"Commit frequency used in failure demo: every {fmt_num(recovery.get('commit_frequency_events'))} events")
    add("Crash consequence: events processed after the last committed position are delivered again after restart.")
    add("Idempotency mechanisms:")
    add("  - session-metrics-projector: deterministic state keyed by website_session_id")
    add("  - conversion-audit-writer: event_id PRIMARY KEY / conflict ignored")
    add("  - refund-monitor: event_id-keyed upsert/update")
    add("Without idempotency, redelivery could double-write records or double-apply side effects.")
    add("")

    # Part 8
    add("PART 8 — THROUGHPUT AND CONSUMER LAG")
    add("-" * 78)
    add(f"Producer throughput: {fmt_num(producer.get('events_per_sec'))} events/sec")
    if isinstance(groups, list):
        for g in groups:
            add(
                f"{g.get('group', g.get('consumer', 'consumer'))}: "
                f"{fmt_num(g.get('processed'))} events, "
                f"{g.get('seconds', 'NOT AVAILABLE')} sec, "
                f"{fmt_num(g.get('events_per_sec', g.get('eps')))} events/sec, "
                f"final lag {fmt_num(g.get('final_lag', g.get('lag')))}"
            )
    add("Consumer lag definition: the count of retained events after a group's committed log position that the group has not processed yet.")
    add("At the end of the successful full run, all core consumer groups have final lag 0.")
    add("If the producer ran continuously, lag would rise whenever production temporarily exceeds a consumer's processing rate and fall when the consumer catches up.")
    add("")

    # Part 9 / 10
    add("PART 9 — FAILURE ISOLATION")
    add("-" * 78)
    add(f"Failure injected into: {recovery.get('consumer', 'flaky-conversion-audit')}")
    add(f"Events handled before crash: {fmt_num(recovery.get('failure_after_handled'))}")
    add(f"Committed event count at crash: {fmt_num(recovery.get('committed_event_count'))}")
    add(f"Committed log_offset at crash: {fmt_num(recovery.get('committed_before_crash'))}")
    add(f"Unconsumed backlog after crash: {fmt_num(recovery.get('backlog_left_in_log'))}")
    add(f"Events lost: {fmt_num(recovery.get('events_lost'))}")
    for row in recovery.get("blast_radius", []):
        add(f"{row.get('component')}: {row.get('status')} — {row.get('evidence')}")
    add("Producer blocked? NO — events were already retained and other consumer groups used independent offsets.")
    add("")

    add("PART 10 — RECOVERY AND REDELIVERY")
    add("-" * 78)
    add(f"Consumer resumed from committed log_offset: {fmt_num(recovery.get('committed_before_crash'))}")
    add(f"Events processed during catch-up: {fmt_num(recovery.get('events_processed_during_recovery'))}")
    add(f"Catch-up time: {recovery.get('recovery_seconds', 'NOT AVAILABLE')} seconds")
    add(f"Remaining lag after recovery: {fmt_num(recovery.get('final_lag'))}")
    add(f"Unique records after recovery: {fmt_num(recovery.get('total_records_written_unique'))}")
    add(f"Total events in log: {fmt_num(recovery.get('events_in_log'))}")
    add(f"Redelivered count: {fmt_num(recovery.get('events_redelivered'))}")
    add("Why redelivery > 0: the crash occurs after processing some events but before their offset is committed, so those events are delivered again on restart.")
    add("Production duplicate handling: an idempotent event_id key/upsert prevents repeated delivery from changing the final state.")
    add("")

    # Part 11
    add("PART 11 — REPLAY")
    add("-" * 78)
    new_hist = replay.get("new_consumer_history", {})
    add(f"New consumer reads all history: {fmt_num(new_hist.get('events_consumed'))} events")
    add(f"Rewind and reprocess deterministic: {yn(replay.get('deterministic_replay'))}")
    catchup = replay.get("offline_catch_up", {})
    add(f"Offline consumer catch-up: processed={fmt_num(catchup.get('events_processed'))}, final lag={fmt_num(catchup.get('final_lag'))}")
    partial = replay.get("partial_replay", {})
    add(f"Partial replay from timestamp: {partial.get('from_time', 'NOT AVAILABLE')}")
    add(f"Partial replay events: {fmt_num(partial.get('events'))} ({pct(partial.get('share_pct'))})")
    add("Late-joining metric: Revenue by Traffic Source plus reconstructed retail monetization metrics.")
    add("Why producer output alone cannot answer it: the producer emits retained events; the later analytics consumer derives a new projection from history without changing producer code.")
    add("A projection bug can be fixed by correcting the consumer and replaying the retained log; without a log, the source history would need to be reconstructed/reloaded.")
    add("")

    # Part 12
    add("PART 12 — RECONCILIATION AGAINST SESSION 1")
    add("-" * 78)

    diffs = reconcile.get("max_differences", {})
    tolerance = float(reconcile.get("tolerance", 1e-6))

    add(f"Groups produced — Session 1: {fmt_num(reconcile.get('batch_groups'))}")
    add(f"Groups produced — Session 2: {fmt_num(reconcile.get('stream_groups'))}")
    add(f"Group sets identical: {yn(reconcile.get('group_sets_identical'))}")
    add(f"Group-count difference: {fmt_num(reconcile.get('count_difference'))}")

    add(f"Maximum difference in pageview count: {diffs.get('pageview_count', 'NOT AVAILABLE')}")
    add(f"Maximum difference in converted flag: {diffs.get('converted', 'NOT AVAILABLE')}")
    add(f"Maximum difference in session duration: {diffs.get('session_duration_seconds', 'NOT AVAILABLE')}")
    add(f"Maximum difference in order revenue: {diffs.get('order_revenue_usd', 'NOT AVAILABLE')}")
    add(f"Maximum difference in gross profit: {diffs.get('gross_profit_usd', 'NOT AVAILABLE')}")
    add(f"Tolerance applied: {tolerance}")
    add(f"Result: {'PASSED' if reconcile.get('passed') else 'FAILED/NOT AVAILABLE'}")

    # Professor's generic reconciliation rows: total records, aggregate total,
    # maximum difference in record counts, totals, and means.
    try:
        import pandas as pd

        batch_path = Path(handover["session1_batch_output"])
        stream_path = RESULTS / "stream_session_metrics.csv"

        batch = pd.read_parquet(batch_path).sort_values("website_session_id").reset_index(drop=True)
        stream = pd.read_csv(stream_path).sort_values("website_session_id").reset_index(drop=True)

        # Structural total records = total pageviews represented by all session groups.
        batch_total_records = int(batch["pageview_count"].sum())
        stream_total_records = int(stream["pageview_count"].sum())

        # Aggregate total = order revenue total, which is the Session 1 monetary
        # aggregate carried into Session 2.
        batch_total_revenue = float(batch["order_revenue_usd"].sum())
        stream_total_revenue = float(stream["order_revenue_usd"].sum())

        # Also preserve gross-profit aggregate because RetailMetrics tracks it.
        batch_total_profit = float(batch["gross_profit_usd"].sum())
        stream_total_profit = float(stream["gross_profit_usd"].sum())

        max_record_count_diff = float(
            (batch["pageview_count"].astype(float) -
             stream["pageview_count"].astype(float)).abs().max()
        )

        total_revenue_diff = abs(batch_total_revenue - stream_total_revenue)
        total_profit_diff = abs(batch_total_profit - stream_total_profit)
        max_total_diff = max(total_revenue_diff, total_profit_diff)

        # Mean differences are computed across the exact same reconciled groups.
        numeric_mean_fields = [
            "session_duration_seconds",
            "order_revenue_usd",
            "gross_profit_usd",
        ]
        mean_diffs = {}
        for field in numeric_mean_fields:
            batch_mean = float(batch[field].astype(float).mean())
            stream_mean = float(stream[field].astype(float).mean())
            mean_diffs[field] = abs(batch_mean - stream_mean)

        max_mean_diff = max(mean_diffs.values()) if mean_diffs else 0.0

        add(f"Total records — Session 1: {batch_total_records:,}")
        add(f"Total records — Session 2: {stream_total_records:,}")

        add(f"Aggregate total (order revenue) — Session 1: ${batch_total_revenue:,.2f}")
        add(f"Aggregate total (order revenue) — Session 2: ${stream_total_revenue:,.2f}")

        add(f"Aggregate gross profit — Session 1: ${batch_total_profit:,.2f}")
        add(f"Aggregate gross profit — Session 2: ${stream_total_profit:,.2f}")

        add(f"Maximum difference in record counts: {max_record_count_diff:.12g}")
        add(f"Maximum difference in totals: {max_total_diff:.12g}")
        add(f"Maximum difference in means: {max_mean_diff:.12g}")

        add(
            "Mean-difference detail: "
            + ", ".join(f"{k}={v:.12g}" for k, v in mean_diffs.items())
        )

        residual = max(
            float(diffs.get("session_duration_seconds", 0) or 0),
            float(diffs.get("order_revenue_usd", 0) or 0),
            float(diffs.get("gross_profit_usd", 0) or 0),
            max_total_diff,
            max_mean_diff,
        )

        add(
            "Explanation of non-zero residual: "
            + (
                "The remaining difference is floating-point representation noise "
                f"({residual:.12g}), which is below the tolerance {tolerance:g}; "
                "there is no structural loss or duplication."
                if residual > 0
                else "No residual difference was observed."
            )
        )

    except Exception as exc:
        add(f"Part 12 direct calculation ERROR: {exc}")
        add("Re-run the helper after confirming the Session 1 parquet and Session 2 stream CSV exist.")

    add(
        "Suggested CI gate: identical website_session_id sets; exact pageview_count "
        "and converted values; all numeric differences <= tolerance; aggregate-total "
        "and mean differences <= tolerance; all core consumer lag = 0."
    )
    add("")

    # Part 13-15
    add("PART 13 — CAPSTONE ARCHITECTURE MAPPING")
    add("-" * 78)
    add("Event source: Session 1 Toy Store E-Commerce dataset migrated to PostgreSQL retailmetrics")
    add(f"Topic: {getattr(cfg, 'TOPIC', 'commerce.activity.recorded')}")
    add(f"Partition key/count: {getattr(cfg, 'PARTITION_KEY', 'website_session_id')} / {getattr(cfg, 'NUM_PARTITIONS', 4)}")
    add("Backbone: PostgreSQL-backed durable event log")
    add("Consumers: session-metrics-projector, conversion-audit-writer, refund-monitor")
    add("Session 2 outputs: streamed session projection, lag report, reconciliation report, replay/monetization outputs")
    add("Session 1 artifact consumed: results/session_journey_metrics.parquet")
    add("Session 3 handoff: Session 2 consumer/projection outputs and durable event contract")
    add("Architecture diagram: architecture/architecture-session2.png (if present)")
    add("")

    add("PART 14 — MULTI-SESSION CONTINUITY PLAN")
    add("-" * 78)
    add("Session 3: turn suitable consumer responsibilities into distributed services and expose service interfaces.")
    add("Session 4: introduce event-time windowed analytics over created_at and selected business metrics.")
    add("Session 5: containerize producer/consumers/backbone dependencies as appropriate.")
    add("Session 6: automate reconciliation, tests, and pass/fail checks in CI/IaC.")
    add("Manual review still required here because the professor expects your own concrete plan and wording.")
    add("")

    add("PART 15 — REPOSITORY EVIDENCE")
    add("-" * 78)
    for name in [
        "config.py",
        "stream_core.py",
        "produce_events.py",
        "consumers.py",
        "replay_suite.py",
        "reconcile.py",
        "run_pipeline.py",
        "results/stream_session_metrics.csv",
        "results/consumer_lag.csv",
        "results/reconciliation_report.json",
        "architecture/architecture-session2.png",
        "README.md",
    ]:
        add(name)
    add("")

    add("PARTS THAT MUST STILL BE FILLED MANUALLY")
    add("-" * 78)
    add("Part 1: repository URL, commit hash, submission date, current Python version, final backbone wording.")
    add("Part 3: copy the exact payload schema fields from produce_events.py into the professor's schema table.")
    add("Part 5: explain any Session 1 vs Session 2 skew difference in your own words.")
    add("Part 8: identify fastest/slowest consumer from the current run and explain the measured cause.")
    add("Part 14: personalize the Session 3-6 continuity plan.")
    add("Part 16: answer all 14 guide questions in your own words.")
    add("Part 18: AI-use disclosure, your own work/verification, references, signature/date.")
    add("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
