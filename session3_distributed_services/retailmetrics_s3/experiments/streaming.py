from __future__ import annotations

import time
from pathlib import Path

import grpc

from ..artifacts import write_csv
from ..mapping import metric_from_pb
from ..proto import retailmetrics_pb2 as pb
from ..proto import retailmetrics_pb2_grpc as rpc


def streaming_report(grpc_target: str, rows: int, output: Path | None = None) -> list[dict]:
    with grpc.insecure_channel(grpc_target) as channel:
        stub = rpc.AnalyticsServiceStub(channel)
        request = pb.SessionMetricsRequest(limit=rows)
        start = time.perf_counter_ns()
        unary = stub.GetSessionMetrics(request)
        unary_total = (time.perf_counter_ns() - start) / 1e6
        unary_values = [metric_from_pb(v) for v in unary.metrics]

        start = time.perf_counter_ns(); first_ms = None; streamed = []
        for message in stub.StreamSessionMetrics(request):
            if first_ms is None: first_ms = (time.perf_counter_ns() - start) / 1e6
            streamed.append(metric_from_pb(message))
        stream_total = (time.perf_counter_ns() - start) / 1e6
    result = [{
        "transport": "grpc-protobuf", "rows": len(streamed),
        "unary_total_ms": round(unary_total, 6),
        "stream_total_ms": round(stream_total, 6),
        "first_message_ms": round(first_ms or 0, 6),
        "first_result_earlier_x": round(unary_total / first_ms, 4) if first_ms else 0,
        "equivalent": unary_values == streamed,
    }]
    if output: write_csv(output, result)
    return result

