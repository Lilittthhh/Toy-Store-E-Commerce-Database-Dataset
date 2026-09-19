from decimal import Decimal

from core.models import Role
from services.analytics_service import AnalyticsService


class FakeAnalyticsRepository:
    def dashboard(self, scope):
        return {"scope": scope}

    def workspace(self):
        return {"active_staff": 3}

    def list_historical_customers(self, search, limit, offset):
        return ([{"dataset_user_id": 7}], 1)

    def historical_customer_detail(self, dataset_user_id):
        return None if dataset_user_id == 404 else {"dataset_user_id": dataset_user_id}

    def list_registered_customers(self, search, limit, offset):
        return ([{"customer_account_id": 9, "dataset_user_id": None, "email": "private@example.com",
                  "first_name": "Private", "last_name": "Customer", "is_active": True,
                  "is_locked": False, "created_at": "2026-09-11", "order_count": 2,
                  "total_spent": Decimal("20.00")}], 1)


def test_scope_and_registered_customer_role_projection():
    service = AnalyticsService(FakeAnalyticsRepository())
    assert service.dashboard("imported")["scope"] == "imported"
    analyst = service.registered_customers(Role.ANALYST, None, 25, 0)["items"][0]
    assert analyst["customer_label"] == "Registered Customer #9"
    assert "email" not in analyst and "first_name" not in analyst and "is_locked" not in analyst
    operations = service.registered_customers(Role.OPERATIONS_STAFF, None, 25, 0)["items"][0]
    assert operations["email"] == "private@example.com"
    assert "is_locked" not in operations
    admin = service.registered_customers(Role.ADMIN, None, 25, 0)["items"][0]
    assert admin["is_locked"] is False


def test_reports_are_vetted_artifacts_and_not_executable_imports():
    report = AnalyticsService.reports()
    assert report["available"] is True
    assert report["reconciliation"]["passed"] is True
    assert report["latency"] and report["payload_sizes"] and report["product_performance"]
