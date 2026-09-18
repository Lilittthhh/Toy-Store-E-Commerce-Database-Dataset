from __future__ import annotations

import httpx


class RestAnalyticsAdapter:
    name = "rest-json"
    def __init__(self, base_url: str, timeout: float = 15.0):
        self.client = httpx.Client(base_url=base_url, timeout=timeout)
    def get_sales_summary(self):
        response = self.client.get("/v1/analytics/sales-summary"); response.raise_for_status(); return response.json()
    def get_session_metrics(self, limit: int):
        response = self.client.get("/v1/analytics/session-metrics", params={"limit": limit}); response.raise_for_status(); return response.json()["metrics"]
    def get_product_performance(self):
        response = self.client.get("/v1/analytics/product-performance", params={"limit": 100}); response.raise_for_status(); return response.json()["products"]
    def close(self): self.client.close()

