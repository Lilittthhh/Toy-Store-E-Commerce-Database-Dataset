from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.analytics import router
from core.dependencies import get_analytics_service, get_current_user
from core.models import AppUser, Role


def _user(role: Role) -> AppUser:
    now = datetime.now(timezone.utc)
    return AppUser(1, "staff", "staff@example.com", "hash", role, True, 0, None, None, now, 1, 1, now, now)


class FakeService:
    def dashboard(self, scope): return {"scope": scope}
    def workspace(self): return {"orders_needing_action": []}
    def reports(self): return {"available": False}
    def historical_customers(self, search, limit, offset): return {"items": [], "total": 0, "limit": limit, "offset": offset}
    def historical_detail(self, dataset_user_id): return {"dataset_user_id": dataset_user_id}
    def registered_customers(self, role, search, limit, offset): return {"role": role.value, "items": []}


def _client(role: Role) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: _user(role)
    app.dependency_overrides[get_analytics_service] = lambda: FakeService()
    return TestClient(app)


def test_all_staff_roles_can_read_analytics_and_customer_intelligence():
    for role in Role:
        client = _client(role)
        assert client.get("/analytics/dashboard?scope=imported").status_code == 200
        assert client.get("/staff/customers/historical?limit=10").status_code == 200
        assert client.get("/staff/customers/registered?limit=10").status_code == 200


def test_page_size_limits_are_enforced():
    client = _client(Role.ANALYST)
    assert client.get("/staff/customers/historical?limit=101").status_code == 422
    assert client.get("/staff/customers/registered?limit=0").status_code == 422
