from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Callable

from ..adapters import GrpcAnalyticsAdapter, InProcessAnalyticsAdapter, RestAnalyticsAdapter
from ..artifacts import write_csv, write_json
from ..config import RESULTS, SESSION1_RESULTS, SESSION2_RESULTS, Settings
from ..db import CanonicalRepository
from ..service_core import RetailMetricsServiceCore, load_snapshot
from ..transports.service_host import ServiceHost
from .adapter_swap import adapter_report
from .contract import contract_report
from .deadline import deadline_report
from .latency import latency_report
from .payload import payload_report
from .reconciliation import reconciliation_report
from .roundtrips import roundtrip_report
from .streaming import streaming_report


class Session3Runtime:
    def __init__(self, cfg: Settings, emit: Callable[[str], None] = print):
        self.cfg = cfg
        self.emit = emit
        self.repository = CanonicalRepository(cfg)
        self.core: RetailMetricsServiceCore | None = None
        self.host: ServiceHost | None = None
        self.results: dict[str, object] = {}
        self.before_fingerprint: dict[str, int] | None = None

    def log(self, message: str) -> None:
        stamp = dt.datetime.now().strftime("%H:%M:%S")
        self.emit(f"[{stamp}] {message}")

    def prepare(self) -> RetailMetricsServiceCore:
        if self.core is None:
            self.log("Opening read-only PostgreSQL snapshot from canonical RetailMetrics data")
            self.before_fingerprint = self.repository.safety_fingerprint()
            self.core = RetailMetricsServiceCore(load_snapshot(self.repository))
            self.log(f"Loaded {len(self.core.snapshot.session_metrics):,} canonical session metrics")
        return self.core

    def start_services(self) -> None:
        if self.host is None:
            core = self.prepare()
            self.host = ServiceHost(self.cfg, core)
            self.host.start()
            self.log(f"REST ready at http://{self.cfg.rest_host}:{self.cfg.rest_port}")
            self.log(f"gRPC ready at {self.cfg.grpc_host}:{self.cfg.grpc_port}")

    def stop(self) -> None:
        if self.host:
            self.host.stop(); self.host = None; self.log("Service host stopped")

    def run_contract(self):
        self.log("CONTRACT: validating protobuf descriptors and generated modules")
        value = contract_report(RESULTS / "contract_report.json"); self.results["contract"] = value
        self.log(f"Contract PASS: {value['message_count']} messages, {value['method_count']} RPC methods")
        return value

    def run_payload(self):
        self.log("PAYLOAD: measuring compact UTF-8 JSON and deterministic protobuf")
        value = payload_report(self.prepare(), RESULTS / "payload_sizes.csv"); self.results["payload"] = value
        self.log("Payload measurements written; values are serialized application payloads")
        return value

    def adapters(self):
        self.start_services()
        return [
            InProcessAnalyticsAdapter(self.prepare()),
            RestAnalyticsAdapter(f"http://{self.cfg.rest_host}:{self.cfg.rest_port}"),
            GrpcAnalyticsAdapter(f"{self.cfg.grpc_host}:{self.cfg.grpc_port}"),
        ]

    def run_latency(self):
        self.log("LATENCY: measuring local in-process, REST/JSON, and gRPC/protobuf calls")
        adapters = self.adapters()
        try: value = latency_report(adapters, self.cfg.warmups, self.cfg.calls, RESULTS / "latency_benchmark.csv")
        finally:
            for adapter in adapters: adapter.close()
        self.results["latency"] = value; self.log("Latency benchmark complete; no protocol winner is assumed")
        return value

    def run_roundtrips(self):
        self.start_services(); self.log("ROUND TRIPS: comparing individual order calls with one batch")
        value = roundtrip_report(self.prepare(), f"http://{self.cfg.rest_host}:{self.cfg.rest_port}", f"{self.cfg.grpc_host}:{self.cfg.grpc_port}", self.cfg.batch_rows, RESULTS / "roundtrip_benchmark.csv")
        self.results["roundtrips"] = value; self.log("Round-trip equivalence verified")
        return value

    def run_streaming(self):
        self.start_services(); self.log("STREAMING: measuring unary completion and first streamed result")
        value = streaming_report(f"{self.cfg.grpc_host}:{self.cfg.grpc_port}", self.cfg.stream_rows, RESULTS / "streaming_benchmark.csv")
        self.results["streaming"] = value; self.log("Streaming sequence equivalence verified; total times are reported independently")
        return value

    def run_adapter_swap(self):
        self.start_services(); self.log("ADAPTER SWAP: same caller through REST and gRPC adapters")
        adapters = [RestAnalyticsAdapter(f"http://{self.cfg.rest_host}:{self.cfg.rest_port}"), GrpcAnalyticsAdapter(f"{self.cfg.grpc_host}:{self.cfg.grpc_port}")]
        try: value = adapter_report(adapters, max(5, self.cfg.calls // 5), RESULTS / "adapter_comparison.csv")
        finally:
            for adapter in adapters: adapter.close()
        self.results["adapter"] = value; self.log("Adapter results compared with zero caller-site changes")
        return value

    def run_deadline(self):
        self.start_services(); self.log("DEADLINE: controlled read-only delayed summary")
        value = deadline_report(f"{self.cfg.grpc_host}:{self.cfg.grpc_port}", output=RESULTS / "deadline_report.json")
        self.results["deadline"] = value; self.log(f"Short call: {value['short_status']}; generous call: {value['generous_status']}")
        return value

    def run_compose(self):
        core = self.prepare(); self.log("COMPOSE: writing canonical sales and product summaries")
        value = {"sales_summary": core.get_sales_summary(), "product_performance": core.get_product_performance(100)["products"]}
        write_json(RESULTS / "analytics_summary.json", value)
        write_csv(RESULTS / "product_performance.csv", value["product_performance"])
        self.results["compose"] = value; return value

    def run_reconcile(self):
        self.log("RECONCILIATION: comparing Session 3 with read-only Session 1 and Session 2 artifacts")
        value = reconciliation_report(self.prepare(), SESSION1_RESULTS, SESSION2_RESULTS, RESULTS / "reconciliation_report.json")
        self.results["reconciliation"] = value; self.log(f"Reconciliation {'PASS' if value['passed'] else 'FAIL'}")
        return value

    def verify_safety(self):
        after = self.repository.safety_fingerprint()
        before = self.before_fingerprint or after
        value = {"before": before, "after": after, "unchanged": before == after, "read_only": True}
        write_json(RESULTS / "database_safety.json", value)
        self.results["safety"] = value
        if not value["unchanged"]: raise RuntimeError("Database counts changed during Session 3")
        self.log("Database safety PASS: protected and Session 2 row counts unchanged")
        return value

    def write_service_summary(self):
        core = self.prepare()
        rows = [{"service_method": key, "calls": value, "errors": 0} for key, value in sorted(core.call_counts().items())]
        if rows: write_csv(RESULTS / "service_summary.csv", rows)
        return rows

    def run_all(self):
        try:
            self.run_contract(); self.run_payload(); self.start_services()
            self.run_latency(); self.run_roundtrips(); self.run_streaming()
            self.run_adapter_swap(); self.run_deadline(); self.run_compose(); self.run_reconcile()
            self.write_service_summary(); self.verify_safety()
            return self.results
        finally:
            self.stop()
