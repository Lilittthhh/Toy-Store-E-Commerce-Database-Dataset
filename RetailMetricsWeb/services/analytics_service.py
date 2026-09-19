from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from core.models import Role
from repositories.analytics_repository import AnalyticsRepository


class AnalyticsService:
    def __init__(self, repository: AnalyticsRepository):
        self.repository = repository

    def dashboard(self, scope: str) -> dict[str, Any]:
        if scope not in {"imported", "application", "combined"}:
            raise HTTPException(status_code=422, detail="scope must be imported, application, or combined.")
        return self.repository.dashboard(scope)

    def workspace(self) -> dict[str, Any]:
        return self.repository.workspace()

    def historical_customers(self, search: str | None, limit: int, offset: int):
        items, total = self.repository.list_historical_customers(search, limit, offset)
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    def historical_detail(self, dataset_user_id: int):
        result = self.repository.historical_customer_detail(dataset_user_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Historical customer not found.")
        return result

    def registered_customers(self, role: Role, search: str | None, limit: int, offset: int):
        items, total = self.repository.list_registered_customers(search, limit, offset)
        projected = []
        for item in items:
            common = {key: item[key] for key in ("customer_account_id", "dataset_user_id", "created_at", "order_count", "total_spent")}
            if role is Role.ANALYST:
                common["customer_label"] = f"Registered Customer #{item['customer_account_id']}"
            else:
                common.update({"customer_label": f"{item['first_name']} {item['last_name']}", "email": item["email"], "is_active": item["is_active"]})
                if role is Role.ADMIN:
                    common["is_locked"] = item["is_locked"]
            projected.append(common)
        return {"items": projected, "total": total, "limit": limit, "offset": offset}

    @staticmethod
    def reports() -> dict[str, Any]:
        root = Path(__file__).resolve().parents[2] / "session3_distributed_services" / "results"
        try:
            with (root / "reconciliation_report.json").open(encoding="utf-8") as handle:
                reconciliation = json.load(handle)
            with (root / "latency_benchmark.csv").open(encoding="utf-8", newline="") as handle:
                latency = list(csv.DictReader(handle))
            with (root / "payload_sizes.csv").open(encoding="utf-8", newline="") as handle:
                payloads = list(csv.DictReader(handle))
            with (root / "product_performance.csv").open(encoding="utf-8", newline="") as handle:
                products = list(csv.DictReader(handle))
        except (OSError, ValueError):
            return {"available": False, "message": "Verified Session 3 result artifacts are unavailable."}
        return {"available": True, "source": "Verified Session 3 result artifacts", "reconciliation": reconciliation,
                "latency": latency, "payload_sizes": payloads, "product_performance": products,
                "observation_note": "Benchmarks are local, machine/run-specific observations—not universal protocol claims."}
