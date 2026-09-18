from __future__ import annotations

import grpc
from google.protobuf import empty_pb2

from ..mapping import (
    item_to_pb, metric_to_pb, order_to_pb, performance_to_pb, product_to_pb,
    refund_to_pb, session_to_pb, summary_to_pb,
)
from ..proto import retailmetrics_pb2 as pb
from ..proto import retailmetrics_pb2_grpc as rpc
from ..service_core import NotFoundError, RetailMetricsServiceCore


def _abort_not_found(context, exc: NotFoundError):
    context.abort(grpc.StatusCode.NOT_FOUND, str(exc))


class CatalogServicer(rpc.CatalogServiceServicer):
    def __init__(self, core): self.core = core
    def GetProduct(self, request, context):
        try: return product_to_pb(self.core.get_product(request.product_id))
        except NotFoundError as exc: return _abort_not_found(context, exc)
    def ListProducts(self, request, context):
        value = self.core.list_products(request.limit, request.offset)
        return pb.ProductList(products=[product_to_pb(v) for v in value["products"]], total=value["total"])


class OrderDataServicer(rpc.OrderDataServiceServicer):
    def __init__(self, core): self.core = core
    def GetOrder(self, request, context):
        try: return order_to_pb(self.core.get_order(request.order_id))
        except NotFoundError as exc: return _abort_not_found(context, exc)
    def ListOrders(self, request, context):
        value = self.core.list_orders(request.limit, request.offset)
        return pb.OrderBatch(orders=[order_to_pb(v) for v in value["orders"]], total=value["total"])
    def BatchGetOrders(self, request, context):
        try: value = self.core.batch_get_orders(request.order_ids)
        except NotFoundError as exc: return _abort_not_found(context, exc)
        return pb.OrderBatch(orders=[order_to_pb(v) for v in value["orders"]], total=value["total"])
    def GetOrderItem(self, request, context):
        try: return item_to_pb(self.core.get_order_item(request.order_item_id))
        except NotFoundError as exc: return _abort_not_found(context, exc)
    def ListOrderItems(self, request, context):
        value = self.core.list_order_items(request.order_id, request.limit, request.offset)
        return pb.OrderItemList(items=[item_to_pb(v) for v in value["items"]], total=value["total"])
    def GetRefund(self, request, context):
        try: return refund_to_pb(self.core.get_refund(request.refund_id))
        except NotFoundError as exc: return _abort_not_found(context, exc)
    def ListRefunds(self, request, context):
        value = self.core.list_refunds(request.order_id, request.limit, request.offset)
        return pb.RefundList(refunds=[refund_to_pb(v) for v in value["refunds"]], total=value["total"])


class JourneyServicer(rpc.JourneyServiceServicer):
    def __init__(self, core): self.core = core
    def GetSession(self, request, context):
        try: return session_to_pb(self.core.get_session(request.website_session_id))
        except NotFoundError as exc: return _abort_not_found(context, exc)
    def BatchGetSessions(self, request, context):
        try: value = self.core.batch_get_sessions(request.website_session_ids)
        except NotFoundError as exc: return _abort_not_found(context, exc)
        return pb.SessionBatch(sessions=[session_to_pb(v) for v in value["sessions"]], total=value["total"])


class AnalyticsServicer(rpc.AnalyticsServiceServicer):
    def __init__(self, core): self.core = core
    def GetSalesSummary(self, request, context):
        return summary_to_pb(self.core.get_sales_summary())
    def GetSessionMetrics(self, request, context):
        value = self.core.get_session_metrics(request.limit, request.after_session_id)
        return pb.SessionMetricList(metrics=[metric_to_pb(v) for v in value["metrics"]], total=value["total"])
    def StreamSessionMetrics(self, request, context):
        for value in self.core.stream_session_metrics(request.limit, request.after_session_id):
            if not context.is_active(): return
            yield metric_to_pb(value)
    def GetProductPerformance(self, request, context):
        value = self.core.get_product_performance(request.limit)
        return pb.ProductPerformanceList(products=[performance_to_pb(v) for v in value["products"]])


class DiagnosticsServicer(rpc.DiagnosticsServiceServicer):
    def __init__(self, core): self.core = core
    def DelaySummary(self, request, context):
        try:
            value = self.core.delay_summary(request.delay_ms, context.is_active)
        except TimeoutError:
            context.abort(grpc.StatusCode.DEADLINE_EXCEEDED, "Caller deadline expired")
        return pb.DelayResult(
            requested_delay_ms=value["requested_delay_ms"], completed=value["completed"],
            summary=summary_to_pb(value["summary"]),
        )


def register_services(server: grpc.Server, core: RetailMetricsServiceCore) -> None:
    rpc.add_CatalogServiceServicer_to_server(CatalogServicer(core), server)
    rpc.add_OrderDataServiceServicer_to_server(OrderDataServicer(core), server)
    rpc.add_JourneyServiceServicer_to_server(JourneyServicer(core), server)
    rpc.add_AnalyticsServiceServicer_to_server(AnalyticsServicer(core), server)
    rpc.add_DiagnosticsServiceServicer_to_server(DiagnosticsServicer(core), server)

