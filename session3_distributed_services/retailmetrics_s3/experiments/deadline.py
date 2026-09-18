from __future__ import annotations

import time
from pathlib import Path

import grpc

from ..artifacts import write_json
from ..proto import retailmetrics_pb2 as pb
from ..proto import retailmetrics_pb2_grpc as rpc


def deadline_report(grpc_target: str, delay_ms: int = 250, short_timeout: float = .05, generous_timeout: float = 2.0, output: Path | None = None) -> dict:
    with grpc.insecure_channel(grpc_target) as channel:
        stub = rpc.DiagnosticsServiceStub(channel)
        start = time.perf_counter_ns()
        try:
            stub.DelaySummary(pb.DelayRequest(delay_ms=delay_ms), timeout=short_timeout)
            short_status = "UNEXPECTED_SUCCESS"
        except grpc.RpcError as exc:
            short_status = exc.code().name
        short_ms = (time.perf_counter_ns() - start) / 1e6
        start = time.perf_counter_ns()
        response = stub.DelaySummary(pb.DelayRequest(delay_ms=delay_ms), timeout=generous_timeout)
        generous_ms = (time.perf_counter_ns() - start) / 1e6
    result = {
        "delay_ms": delay_ms, "short_timeout_ms": short_timeout * 1000,
        "short_status": short_status, "short_elapsed_ms": round(short_ms, 6),
        "generous_timeout_ms": generous_timeout * 1000,
        "generous_status": "SUCCESS" if response.completed else "FAIL",
        "generous_elapsed_ms": round(generous_ms, 6),
        "passed": short_status == "DEADLINE_EXCEEDED" and response.completed,
    }
    if output: write_json(output, result)
    return result
