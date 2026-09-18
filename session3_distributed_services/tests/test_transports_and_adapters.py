from __future__ import annotations

import grpc
import httpx
from google.protobuf import empty_pb2

from retailmetrics_s3.adapters import GrpcAnalyticsAdapter, RestAnalyticsAdapter
from retailmetrics_s3.adapters.base import run_analytics
from retailmetrics_s3.experiments.adapter_swap import adapter_report
from retailmetrics_s3.experiments.deadline import deadline_report
from retailmetrics_s3.experiments.latency import latency_report
from retailmetrics_s3.experiments.roundtrips import roundtrip_report
from retailmetrics_s3.experiments.streaming import streaming_report
from retailmetrics_s3.mapping import summary_from_pb
from retailmetrics_s3.proto import retailmetrics_pb2_grpc as rpc


def _addresses(cfg):
    return f"http://{cfg.rest_host}:{cfg.rest_port}", f"{cfg.grpc_host}:{cfg.grpc_port}"


def test_rest_and_grpc_normalized_result_equality(transport_host):
    cfg, _ = transport_host; rest_url, grpc_target = _addresses(cfg)
    with httpx.Client(base_url=rest_url) as client, grpc.insecure_channel(grpc_target) as channel:
        rest = client.get("/v1/analytics/sales-summary"); rest.raise_for_status()
        protobuf = rpc.AnalyticsServiceStub(channel).GetSalesSummary(empty_pb2.Empty())
        assert rest.json() == summary_from_pb(protobuf)


def test_adapter_equivalence_and_unchanged_caller(transport_host):
    cfg, _ = transport_host; rest_url, grpc_target = _addresses(cfg)
    adapters = [RestAnalyticsAdapter(rest_url), GrpcAnalyticsAdapter(grpc_target)]
    try:
        assert run_analytics(adapters[0]) == run_analytics(adapters[1])
        rows = adapter_report(adapters, calls=2)
        assert all(row["identical_results"] for row in rows)
        assert all(row["caller_sites_changed"] == 0 for row in rows)
    finally:
        for adapter in adapters: adapter.close()


def test_batch_equals_individual_calls(transport_host):
    cfg, core = transport_host; rest_url, grpc_target = _addresses(cfg)
    rows = roundtrip_report(core, rest_url, grpc_target, rows=5)
    assert len(rows) == 2
    assert all(row["equivalent"] and row["round_trips_saved"] == 4 for row in rows)


def test_unary_and_streaming_sequences_are_equal(transport_host):
    cfg, _ = transport_host; _, grpc_target = _addresses(cfg)
    row = streaming_report(grpc_target, rows=10)[0]
    assert row["equivalent"] is True
    assert row["rows"] == 10
    assert row["first_message_ms"] > 0


def test_deadline_exceeded_then_success(transport_host):
    cfg, _ = transport_host; _, grpc_target = _addresses(cfg)
    result = deadline_report(grpc_target, delay_ms=80, short_timeout=.01, generous_timeout=1)
    assert result["short_status"] == "DEADLINE_EXCEEDED"
    assert result["generous_status"] == "SUCCESS"
    assert result["passed"] is True


def test_benchmark_structure_without_performance_winner_assertion(transport_host):
    cfg, _ = transport_host; rest_url, grpc_target = _addresses(cfg)
    adapters = [RestAnalyticsAdapter(rest_url), GrpcAnalyticsAdapter(grpc_target)]
    try:
        rows = latency_report(adapters, warmups=1, calls=3)
        assert {row["transport"] for row in rows} == {"rest-json", "grpc-protobuf"}
        assert all(row["median_ms"] > 0 and row["calls_per_sec"] > 0 for row in rows)
    finally:
        for adapter in adapters: adapter.close()

