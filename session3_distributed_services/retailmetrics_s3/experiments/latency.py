from __future__ import annotations

import statistics
import time
from pathlib import Path

from ..artifacts import write_csv
from ..mapping import summary_to_pb
from ..models import compact_json_bytes, percentile


def latency_report(adapters: list, warmups: int, calls: int, output: Path | None = None) -> list[dict]:
    rows = []
    for adapter in adapters:
        for _ in range(warmups): adapter.get_sales_summary()
        times = []
        started = time.perf_counter_ns()
        latest = None
        for _ in range(calls):
            before = time.perf_counter_ns()
            latest = adapter.get_sales_summary()
            times.append((time.perf_counter_ns() - before) / 1_000_000)
        elapsed = (time.perf_counter_ns() - started) / 1_000_000_000
        if adapter.name == "rest-json":
            response_bytes = len(compact_json_bytes(latest)); codec = "JSON"; request_bytes = 0
        elif adapter.name == "grpc-protobuf":
            response_bytes = len(summary_to_pb(latest).SerializeToString(deterministic=True)); codec = "protobuf"; request_bytes = 0
        else:
            response_bytes = 0; codec = "none"; request_bytes = 0
        rows.append({
            "transport": adapter.name, "codec": codec, "calls": calls,
            "median_ms": round(statistics.median(times), 6),
            "p95_ms": round(percentile(times, .95), 6),
            "calls_per_sec": round(calls / elapsed, 3),
            "request_bytes": request_bytes, "response_bytes": response_bytes,
        })
    if output: write_csv(output, rows)
    return rows

