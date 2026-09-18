from __future__ import annotations

import time

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from ..service_core import NotFoundError, RetailMetricsServiceCore


class OrderBatchBody(BaseModel):
    order_ids: list[int] = Field(min_length=1, max_length=500)


class SessionBatchBody(BaseModel):
    website_session_ids: list[int] = Field(min_length=1, max_length=500)


class DelayBody(BaseModel):
    delay_ms: int = Field(ge=0, le=10_000)


def create_rest_app(core: RetailMetricsServiceCore) -> FastAPI:
    app = FastAPI(title="RetailMetrics Session 3 REST Service", version="1.0.0")

    def call(fn, *args):
        try:
            return fn(*args)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/health")
    def health():
        return {"status": "ok", "read_only": True}

    @app.get("/v1/products")
    def products(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
        return core.list_products(limit, offset)

    @app.get("/v1/products/{product_id}")
    def product(product_id: int):
        return call(core.get_product, product_id)

    @app.get("/v1/orders")
    def orders(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
        return core.list_orders(limit, offset)

    @app.get("/v1/orders/{order_id}")
    def order(order_id: int):
        return call(core.get_order, order_id)

    @app.post("/v1/orders/batch-query")
    def order_batch(body: OrderBatchBody):
        return call(core.batch_get_orders, body.order_ids)

    @app.get("/v1/order-items/{item_id}")
    def item(item_id: int):
        return call(core.get_order_item, item_id)

    @app.get("/v1/order-items")
    def items(order_id: int, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
        return core.list_order_items(order_id, limit, offset)

    @app.get("/v1/refunds/{refund_id}")
    def refund(refund_id: int):
        return call(core.get_refund, refund_id)

    @app.get("/v1/refunds")
    def refunds(order_id: int, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
        return core.list_refunds(order_id, limit, offset)

    @app.get("/v1/sessions/{session_id}")
    def session(session_id: int):
        return call(core.get_session, session_id)

    @app.post("/v1/sessions/batch-query")
    def session_batch(body: SessionBatchBody):
        return call(core.batch_get_sessions, body.website_session_ids)

    @app.get("/v1/analytics/sales-summary")
    def sales_summary():
        return core.get_sales_summary()

    @app.get("/v1/analytics/session-metrics")
    def session_metrics(limit: int = Query(100, ge=1, le=10_000), after_session_id: int = Query(0, ge=0)):
        return core.get_session_metrics(limit, after_session_id)

    @app.get("/v1/analytics/product-performance")
    def product_performance(limit: int = Query(100, ge=1, le=500)):
        return core.get_product_performance(limit)

    @app.post("/v1/diagnostics/delay-summary")
    def delay_summary(body: DelayBody):
        return core.delay_summary(body.delay_ms)

    return app

