from __future__ import annotations

import statistics
import time
from pathlib import Path

from ..adapters.base import run_analytics
from ..artifacts import write_csv
from ..mapping import performance_to_pb, summary_to_pb
from ..models import compact_json_bytes


def adapter_report(adapters: list, calls: int, output: Path | None = None) -> list[dict]:
    rows = []; canonical = None
    for adapter in adapters:
        durations = []; value = None
        for _ in range(calls):
            start = time.perf_counter_ns(); value = run_analytics(adapter)
            durations.append((time.perf_counter_ns() - start) / 1e6)
        if canonical is None: canonical = value
        if adapter.name == "rest-json":
            received = len(compact_json_bytes(value)); sent = 0
        else:
            received = len(summary_to_pb(value["sales_summary"]).SerializeToString(deterministic=True))
            received += sum(len(performance_to_pb(v).SerializeToString(deterministic=True)) for v in value["product_performance"])
            sent = 0
        rows.append({
            "adapter": adapter.name, "calls": calls,
            "median_ms_per_call": round(statistics.median(durations), 6),
            "bytes_sent_per_call": sent, "bytes_received_per_call": received,
            "bytes_per_call": sent + received, "identical_results": value == canonical,
            "caller_sites_changed": 0,
        })
    if output: write_csv(output, rows)
    return rows

