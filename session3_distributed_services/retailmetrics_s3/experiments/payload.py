from __future__ import annotations

from pathlib import Path

from ..artifacts import write_csv
from ..mapping import (
    item_to_pb, metric_to_pb, order_to_pb, performance_to_pb, product_to_pb,
    refund_to_pb, session_to_pb, summary_to_pb,
)
from ..models import compact_json_bytes
from ..service_core import RetailMetricsServiceCore


def payload_report(core: RetailMetricsServiceCore, output: Path | None = None) -> list[dict]:
    samples = [
        ("Product", core.snapshot.products[0], product_to_pb),
        ("Order", core.snapshot.orders[0], order_to_pb),
        ("OrderItem", core.snapshot.order_items[0], item_to_pb),
        ("Refund", core.snapshot.refunds[0], refund_to_pb),
        ("WebsiteSession", core.snapshot.sessions[0], session_to_pb),
        ("SessionMetric", core.snapshot.session_metrics[0], metric_to_pb),
        ("SalesSummary", core.snapshot.sales_summary, summary_to_pb),
        ("ProductPerformance", core.snapshot.product_performance[0], performance_to_pb),
    ]
    rows = []
    for name, value, mapper in samples:
        json_size = len(compact_json_bytes(value))
        proto_size = len(mapper(value).SerializeToString(deterministic=True))
        saved = json_size - proto_size
        rows.append({
            "message": name, "fields": len(value), "json_bytes": json_size,
            "protobuf_bytes": proto_size, "bytes_saved": saved,
            "reduction_pct": round(saved / json_size * 100, 4) if json_size else 0,
        })
    if output: write_csv(output, rows)
    return rows

