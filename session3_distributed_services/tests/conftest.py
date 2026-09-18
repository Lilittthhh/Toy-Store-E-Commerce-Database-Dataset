from __future__ import annotations

import socket
from dataclasses import replace

import pytest

from retailmetrics_s3.config import Settings
from retailmetrics_s3.service_core import RetailMetricsServiceCore, ServiceSnapshot
from retailmetrics_s3.transports.service_host import ServiceHost


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def fake_core() -> RetailMetricsServiceCore:
    timestamp = "2014-01-01T00:00:00Z"
    products = ({"product_id": 1, "created_at": timestamp, "product_name": "Toy Rocket"},)
    orders = tuple({
        "order_id": i, "created_at": timestamp, "website_session_id": i,
        "user_id": 1000 + i, "primary_product_id": 1, "items_purchased": 1,
        "price_cents": 1999, "cogs_cents": 700,
    } for i in range(1, 11))
    items = ({"order_item_id": 1, "created_at": timestamp, "order_id": 1, "product_id": 1, "is_primary_item": 1, "price_cents": 1999, "cogs_cents": 700},)
    refunds = ({"refund_id": 1, "created_at": timestamp, "order_item_id": 1, "order_id": 1, "refund_amount_cents": 500},)
    sessions = tuple({
        "website_session_id": i, "created_at": timestamp, "user_id": 1000 + i,
        "is_repeat_session": 0, "utm_source": "search", "utm_campaign": "toys",
        "utm_content": None, "device_type": "desktop", "http_referer": None,
    } for i in range(1, 11))
    metrics = tuple({
        "website_session_id": i, "pageview_count": 2,
        "session_duration_seconds": 10.0, "converted": True,
        "order_revenue_cents": 1999, "gross_profit_cents": 1299,
    } for i in range(1, 11))
    summary = {"session_count": 10, "order_count": 10, "conversion_count": 10, "revenue_cents": 19990, "gross_profit_cents": 12990, "refund_cents": 500, "conversion_rate": 1.0}
    performance = ({"product_id": 1, "product_name": "Toy Rocket", "order_count": 10, "units": 10, "revenue_cents": 19990, "cogs_cents": 7000, "refund_cents": 500, "net_revenue_cents": 19490},)
    snapshot = ServiceSnapshot(
        counts={"website_sessions": 10, "website_pageviews": 20, "products": 1, "orders": 10, "order_items": 1, "order_item_refunds": 1},
        products=products, orders=orders, order_items=items, refunds=refunds,
        sessions=sessions, session_metrics=metrics, sales_summary=summary,
        product_performance=performance,
    )
    return RetailMetricsServiceCore(snapshot)


@pytest.fixture
def transport_host(fake_core):
    cfg = replace(Settings(), rest_port=_free_port(), grpc_port=_free_port())
    host = ServiceHost(cfg, fake_core); host.start()
    try:
        yield cfg, fake_core
    finally:
        host.stop()

