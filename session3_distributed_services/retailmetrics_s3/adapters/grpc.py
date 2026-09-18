from __future__ import annotations

import grpc
from google.protobuf import empty_pb2

from ..mapping import metric_from_pb, performance_from_pb, summary_from_pb
from ..proto import retailmetrics_pb2 as pb
from ..proto import retailmetrics_pb2_grpc as rpc


class GrpcAnalyticsAdapter:
    name = "grpc-protobuf"
    def __init__(self, target: str):
        self.channel = grpc.insecure_channel(target)
        self.stub = rpc.AnalyticsServiceStub(self.channel)
    def get_sales_summary(self):
        return summary_from_pb(self.stub.GetSalesSummary(empty_pb2.Empty()))
    def get_session_metrics(self, limit: int):
        response = self.stub.GetSessionMetrics(pb.SessionMetricsRequest(limit=limit))
        return [metric_from_pb(v) for v in response.metrics]
    def get_product_performance(self):
        response = self.stub.GetProductPerformance(pb.ProductPerformanceRequest(limit=100))
        return [performance_from_pb(v) for v in response.products]
    def close(self): self.channel.close()
