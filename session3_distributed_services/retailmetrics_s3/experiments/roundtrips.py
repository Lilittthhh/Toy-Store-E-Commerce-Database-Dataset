from __future__ import annotations

import statistics
import time
from pathlib import Path

import grpc
import httpx

from ..artifacts import write_csv
from ..mapping import order_from_pb
from ..proto import retailmetrics_pb2 as pb
from ..proto import retailmetrics_pb2_grpc as rpc
from ..service_core import RetailMetricsServiceCore


def roundtrip_report(core: RetailMetricsServiceCore, rest_url: str, grpc_target: str, rows: int, output: Path | None = None) -> list[dict]:
    ids = [v["order_id"] for v in core.snapshot.orders[:rows]]
    results = []
    with httpx.Client(base_url=rest_url, timeout=30) as client:
        results.append(_measure_rest(client, ids))
    with grpc.insecure_channel(grpc_target) as channel:
        results.append(_measure_grpc(rpc.OrderDataServiceStub(channel), ids))
    if output: write_csv(output, results)
    return results


def _measure_rest(client, ids):
    individual = []
    start = time.perf_counter_ns()
    for value in ids:
        response = client.get(f"/v1/orders/{value}"); response.raise_for_status(); individual.append(response.json())
    individual_ms = (time.perf_counter_ns() - start) / 1e6
    start = time.perf_counter_ns()
    response = client.post("/v1/orders/batch-query", json={"order_ids": ids}); response.raise_for_status()
    batch_ms = (time.perf_counter_ns() - start) / 1e6
    batch = response.json()["orders"]
    return _row("rest-json", ids, individual, batch, individual_ms, batch_ms)


def _measure_grpc(stub, ids):
    start = time.perf_counter_ns()
    individual = [order_from_pb(stub.GetOrder(pb.OrderIdRequest(order_id=v))) for v in ids]
    individual_ms = (time.perf_counter_ns() - start) / 1e6
    start = time.perf_counter_ns()
    response = stub.BatchGetOrders(pb.OrderBatchRequest(order_ids=ids))
    batch_ms = (time.perf_counter_ns() - start) / 1e6
    batch = [order_from_pb(v) for v in response.orders]
    return _row("grpc-protobuf", ids, individual, batch, individual_ms, batch_ms)


def _row(codec, ids, individual, batch, individual_ms, batch_ms):
    equivalent = individual == batch and [v["order_id"] for v in batch] == ids
    return {
        "transport": codec, "rows": len(ids),
        "batch_ms": round(batch_ms, 6), "individual_ms": round(individual_ms, 6),
        "speedup": round(individual_ms / batch_ms, 4) if batch_ms else 0,
        "round_trips_saved": max(0, len(ids) - 1), "equivalent": equivalent,
    }

