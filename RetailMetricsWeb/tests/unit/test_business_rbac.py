from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.business import router
from core.dependencies import get_business_repository, get_business_service, get_current_user
from core.models import AppUser, Role


def user(role: Role) -> AppUser:
    now = datetime.now(timezone.utc)
    return AppUser(1, "test", "test@example.com", "hash", role, True, 0, None, None, now, 1, 1, now, now)


class FakeRepository:
    def list_mutable(self, entity, clauses, params, limit, offset):
        return [], 0


class FakeService:
    def create(self, entity, data, creator_id):
        return {
            "product_id": 99,
            "created_at": data["created_at"],
            "product_name": data["product_name"],
            "created_by_app_user_id": creator_id,
            "row_version": 1,
            "origin": "web",
        }


def client_for(role: Role) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user(role)
    app.dependency_overrides[get_business_repository] = lambda: FakeRepository()
    app.dependency_overrides[get_business_service] = lambda: FakeService()
    return TestClient(app)


def test_analyst_can_read_but_cannot_create_order() -> None:
    client = client_for(Role.ANALYST)
    assert client.get("/products").status_code == 200
    assert client.post(
        "/orders",
        json={
            "created_at": "2026-01-01T00:00:00",
            "website_session_id": 1,
            "user_id": 1,
            "primary_product_id": 1,
            "items_purchased": 1,
            "price_usd": "10.00",
            "cogs_usd": "5.00",
        },
    ).status_code == 403


def test_operations_cannot_create_product_but_admin_can() -> None:
    payload = {"created_at": "2026-01-01T00:00:00", "product_name": "Demo"}
    assert client_for(Role.OPERATIONS_STAFF).post("/products", json=payload).status_code == 403
    response = client_for(Role.ADMIN).post("/products", json=payload)
    assert response.status_code == 201
    assert response.json()["created_by_app_user_id"] == 1
