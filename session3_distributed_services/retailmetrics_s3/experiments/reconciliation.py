from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pandas as pd

from ..artifacts import write_json
from ..models import decimal_to_cents
from ..service_core import RetailMetricsServiceCore


TOLERANCE = 1e-6


def _reference_money_to_cents(series: pd.Series) -> pd.Series:
    return series.map(lambda value: decimal_to_cents(Decimal(str(value))))


def _compare_session_frame(current: pd.DataFrame, reference: pd.DataFrame, name: str) -> dict:
    left = current.sort_values("website_session_id").reset_index(drop=True)
    right = reference.sort_values("website_session_id").reset_index(drop=True)
    same_count = len(left) == len(right)
    # Session 1 stores IDs as int32 while PostgreSQL/pandas exposes them as
    # int64.  Reconciliation compares identifier values, not storage width.
    ids_equal = same_count and left["website_session_id"].astype("int64").equals(
        right["website_session_id"].astype("int64")
    )
    exact = {}
    for field in ("pageview_count", "converted"):
        a = left[field].astype("int64")
        b = right[field].astype("int64")
        exact[field] = int((a - b).abs().max()) if same_count else -1
    duration_diff = float((left["session_duration_seconds"].astype(float) - right["session_duration_seconds"].astype(float)).abs().max()) if same_count else float("inf")
    revenue_diff = int((left["order_revenue_cents"] - _reference_money_to_cents(right["order_revenue_usd"])).abs().max()) if same_count else -1
    profit_diff = int((left["gross_profit_cents"] - _reference_money_to_cents(right["gross_profit_usd"])).abs().max()) if same_count else -1
    passed = ids_equal and same_count and all(v == 0 for v in exact.values()) and duration_diff <= TOLERANCE and revenue_diff == 0 and profit_diff == 0
    return {
        "compared_against": name, "session3_records": len(left),
        "reference_records": len(right), "ids_equal": bool(ids_equal),
        "max_exact_differences": exact,
        "max_duration_difference": duration_diff,
        "max_revenue_difference_cents": revenue_diff,
        "max_gross_profit_difference_cents": profit_diff,
        "tolerance": TOLERANCE, "passed": bool(passed),
    }


def reconciliation_report(core: RetailMetricsServiceCore, session1_results: Path, session2_results: Path, output: Path | None = None) -> dict:
    current = pd.DataFrame(core.snapshot.session_metrics)
    session1_path = session1_results / "session_journey_metrics.parquet"
    if not session1_path.exists(): session1_path = session1_results / "baseline_result.csv"
    session1 = pd.read_parquet(session1_path) if session1_path.suffix == ".parquet" else pd.read_csv(session1_path)
    session2_path = session2_results / "stream_session_metrics.csv"
    session2 = pd.read_csv(session2_path)
    comparisons = [
        _compare_session_frame(current, session1, f"Session 1: {session1_path.name}"),
        _compare_session_frame(current, session2, f"Session 2: {session2_path.name}"),
    ]
    summary_path = session2_results / "consumer_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    refund_group = next(v for v in summary["groups"] if v["group"] == "refund-monitor")
    refund_count = core.snapshot.counts["order_item_refunds"]
    refund_cents = core.snapshot.sales_summary["refund_cents"]
    refund_reference_cents = decimal_to_cents(Decimal(str(refund_group["refund_total_usd"])))
    refund_comparison = {
        "compared_against": "Session 2: consumer_summary.json/refund-monitor",
        "session3_refund_count": refund_count,
        "reference_refund_count": int(refund_group["refund_events"]),
        "refund_difference_cents": refund_cents - refund_reference_cents,
    }
    refund_comparison["passed"] = refund_comparison["session3_refund_count"] == refund_comparison["reference_refund_count"] and refund_comparison["refund_difference_cents"] == 0
    report = {
        "comparisons": comparisons,
        "refund_comparison": refund_comparison,
        "json_protobuf_equivalence_required_separately": True,
        "product_performance_cross_session_comparison": "not applicable; Sessions 1 and 2 do not publish the same metric",
        "passed": all(v["passed"] for v in comparisons) and refund_comparison["passed"],
    }
    if output: write_json(output, report)
    return report
