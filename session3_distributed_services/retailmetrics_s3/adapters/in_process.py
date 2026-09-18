from __future__ import annotations

from ..service_core import RetailMetricsServiceCore


class InProcessAnalyticsAdapter:
    name = "in-process"
    def __init__(self, core: RetailMetricsServiceCore): self.core = core
    def get_sales_summary(self): return self.core.get_sales_summary()
    def get_session_metrics(self, limit: int): return self.core.get_session_metrics(limit)["metrics"]
    def get_product_performance(self): return self.core.get_product_performance(100)["products"]
    def close(self): return None

