from __future__ import annotations

from typing import Any, Protocol


class AnalyticsServiceAdapter(Protocol):
    name: str
    def get_sales_summary(self) -> dict[str, Any]: ...
    def get_session_metrics(self, limit: int) -> list[dict[str, Any]]: ...
    def get_product_performance(self) -> list[dict[str, Any]]: ...
    def close(self) -> None: ...


def run_analytics(adapter: AnalyticsServiceAdapter) -> dict[str, Any]:
    """Caller is intentionally transport-blind."""
    return {
        "sales_summary": adapter.get_sales_summary(),
        "product_performance": adapter.get_product_performance(),
    }

