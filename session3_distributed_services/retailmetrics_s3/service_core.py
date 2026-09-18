from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Iterable

from .db import CanonicalRepository


class NotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class ServiceSnapshot:
    counts: dict[str, int]
    products: tuple[dict[str, Any], ...]
    orders: tuple[dict[str, Any], ...]
    order_items: tuple[dict[str, Any], ...]
    refunds: tuple[dict[str, Any], ...]
    sessions: tuple[dict[str, Any], ...]
    session_metrics: tuple[dict[str, Any], ...]
    sales_summary: dict[str, Any]
    product_performance: tuple[dict[str, Any], ...]


def load_snapshot(repository: CanonicalRepository) -> ServiceSnapshot:
    return ServiceSnapshot(
        counts=repository.source_counts(),
        products=tuple(repository.products()),
        orders=tuple(repository.orders()),
        order_items=tuple(repository.order_items()),
        refunds=tuple(repository.refunds()),
        sessions=tuple(repository.sessions()),
        session_metrics=tuple(repository.session_metrics()),
        sales_summary=repository.sales_summary(),
        product_performance=tuple(repository.product_performance()),
    )


class RetailMetricsServiceCore:
    """Transport-neutral, immutable read service shared by REST and gRPC."""

    def __init__(self, snapshot: ServiceSnapshot):
        self.snapshot = snapshot
        self._calls: dict[str, int] = {}
        self._lock = threading.Lock()
        self._products = {v["product_id"]: v for v in snapshot.products}
        self._orders = {v["order_id"]: v for v in snapshot.orders}
        self._items = {v["order_item_id"]: v for v in snapshot.order_items}
        self._refunds = {v["refund_id"]: v for v in snapshot.refunds}
        self._sessions = {v["website_session_id"]: v for v in snapshot.sessions}

    def _called(self, name: str) -> None:
        with self._lock:
            self._calls[name] = self._calls.get(name, 0) + 1

    def call_counts(self) -> dict[str, int]:
        with self._lock:
            return dict(self._calls)

    @staticmethod
    def _one(store: dict[int, dict[str, Any]], key: int, entity: str) -> dict[str, Any]:
        try:
            return dict(store[key])
        except KeyError as exc:
            raise NotFoundError(f"{entity} {key} is not in the canonical benchmark snapshot") from exc

    def get_product(self, product_id: int) -> dict[str, Any]:
        self._called("CatalogService.GetProduct")
        return self._one(self._products, product_id, "Product")

    def list_products(self, limit: int, offset: int = 0) -> dict[str, Any]:
        self._called("CatalogService.ListProducts")
        return {"products": [dict(v) for v in self.snapshot.products[offset:offset + limit]], "total": len(self.snapshot.products)}

    def get_order(self, order_id: int) -> dict[str, Any]:
        self._called("OrderDataService.GetOrder")
        return self._one(self._orders, order_id, "Order")

    def list_orders(self, limit: int, offset: int = 0) -> dict[str, Any]:
        self._called("OrderDataService.ListOrders")
        return {"orders": [dict(v) for v in self.snapshot.orders[offset:offset + limit]], "total": self.snapshot.counts["orders"]}

    def batch_get_orders(self, order_ids: Iterable[int]) -> dict[str, Any]:
        self._called("OrderDataService.BatchGetOrders")
        orders = [self._one(self._orders, int(i), "Order") for i in order_ids]
        return {"orders": orders, "total": len(orders)}

    def get_order_item(self, item_id: int) -> dict[str, Any]:
        self._called("OrderDataService.GetOrderItem")
        return self._one(self._items, item_id, "Order item")

    def list_order_items(self, order_id: int, limit: int, offset: int = 0) -> dict[str, Any]:
        self._called("OrderDataService.ListOrderItems")
        values = [dict(v) for v in self.snapshot.order_items if v["order_id"] == order_id]
        return {"items": values[offset:offset + limit], "total": len(values)}

    def get_refund(self, refund_id: int) -> dict[str, Any]:
        self._called("OrderDataService.GetRefund")
        return self._one(self._refunds, refund_id, "Refund")

    def list_refunds(self, order_id: int, limit: int, offset: int = 0) -> dict[str, Any]:
        self._called("OrderDataService.ListRefunds")
        values = [dict(v) for v in self.snapshot.refunds if v["order_id"] == order_id]
        return {"refunds": values[offset:offset + limit], "total": len(values)}

    def get_session(self, session_id: int) -> dict[str, Any]:
        self._called("JourneyService.GetSession")
        return self._one(self._sessions, session_id, "Website session")

    def batch_get_sessions(self, session_ids: Iterable[int]) -> dict[str, Any]:
        self._called("JourneyService.BatchGetSessions")
        values = [self._one(self._sessions, int(i), "Website session") for i in session_ids]
        return {"sessions": values, "total": len(values)}

    def get_sales_summary(self) -> dict[str, Any]:
        self._called("AnalyticsService.GetSalesSummary")
        return dict(self.snapshot.sales_summary)

    def get_session_metrics(self, limit: int, after_session_id: int = 0) -> dict[str, Any]:
        self._called("AnalyticsService.GetSessionMetrics")
        values = [dict(v) for v in self.snapshot.session_metrics if v["website_session_id"] > after_session_id]
        values = values[:limit]
        return {"metrics": values, "total": len(self.snapshot.session_metrics)}

    def stream_session_metrics(self, limit: int, after_session_id: int = 0):
        self._called("AnalyticsService.StreamSessionMetrics")
        emitted = 0
        for value in self.snapshot.session_metrics:
            if value["website_session_id"] <= after_session_id:
                continue
            yield dict(value)
            emitted += 1
            if emitted >= limit:
                break

    def get_product_performance(self, limit: int) -> dict[str, Any]:
        self._called("AnalyticsService.GetProductPerformance")
        return {"products": [dict(v) for v in self.snapshot.product_performance[:limit]]}

    def delay_summary(self, delay_ms: int, active=lambda: True) -> dict[str, Any]:
        self._called("DiagnosticsService.DelaySummary")
        remaining = max(0, delay_ms) / 1000
        while remaining > 0:
            if not active():
                raise TimeoutError("Caller deadline expired")
            interval = min(0.01, remaining)
            time.sleep(interval)
            remaining -= interval
        return {"requested_delay_ms": delay_ms, "completed": True, "summary": self.get_sales_summary()}
