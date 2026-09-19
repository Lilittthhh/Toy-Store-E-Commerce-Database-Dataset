from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.audit import router
from core.config import Settings, get_settings
from core.dependencies import get_current_user
from core.models import Role
from db.connection import get_db_connection
from frontend.navigation import navigation_for_role, CUSTOMER_ACCOUNT_NAVIGATION
from services.audit import AuditEvent, POLICY, event_for_request, sanitize_values, set_actor, write_event
from db import connection as connection_module


class Cursor:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params):
        self.calls.append((sql, params))


def test_migration_005_is_additive_transactional_and_unapplied_by_tests():
    sql = (Path(__file__).resolve().parents[2] / "db/migrations/005_audit_trail.sql").read_text()
    assert "BEGIN;" in sql and sql.rstrip().endswith("COMMIT;")
    assert "CREATE TABLE IF NOT EXISTS public.audit_logs" in sql
    assert "GENERATED ALWAYS AS IDENTITY PRIMARY KEY" in sql
    assert "old_values JSONB" in sql and "new_values JSONB" in sql
    for name in ("created_at", "actor", "actor_role", "action", "entity"):
        assert f"idx_audit_logs_{name}" in sql
    for forbidden in ("UPDATE public.", "DELETE FROM public.", "TRUNCATE", "DROP TABLE"):
        assert forbidden not in sql


def test_sensitive_values_never_survive_even_under_safe_named_fields():
    values = {"password": "secret", "reset_token": "token", "smtp_password": "credential",
              "payment_card": "1234", "order_status": "Bearer secret", "role": "token",
              "quantity": 2, "is_active": False, "request_status": "approved"}
    assert sanitize_values(values) == {"quantity": 2, "is_active": False, "request_status": "approved"}


def test_only_known_successful_mutations_are_classified():
    req = SimpleNamespace(method="POST", scope={"route": SimpleNamespace(path="/customer/checkout")},
                          state=SimpleNamespace(audit_entity_id="81"), path_params={})
    event = event_for_request(req)
    assert event.action == "ORDER_CREATED" and event.entity_id == "81"
    req.method = "GET"
    assert event_for_request(req) is None
    req.method = "POST"
    req.scope["route"].path = "/customer/orders/{order_id}/confirm-delivery"
    req.state = SimpleNamespace()
    req.path_params = {"order_id": 81}
    assert event_for_request(req).new_values["order_status"] == "delivered"


@pytest.mark.parametrize("actor,path,action,entity_id", [
    (("staff", 1, "admin"), "/analytics/workspace", "VIEW_DASHBOARD", None),
    (("staff", 1, "admin"), "/admin/audit-logs", "VIEW_AUDIT_TRAIL", None),
    (("staff", 1, "admin"), "/admin/audit-logs/{audit_log_id}", "VIEW_AUDIT_DETAIL", "17"),
    (("staff", 1, "admin"), "/admin/users", "VIEW_STAFF_LIST", None),
    (("staff", 2, "operations_staff"), "/order-workflow/orders", "VIEW_ORDER_LIST", None),
    (("staff", 2, "operations_staff"), "/products", "VIEW_PRODUCT_LIST", None),
    (("staff", 3, "analyst"), "/analytics/dashboard", "VIEW_ANALYTICS", None),
    (("staff", 3, "analyst"), "/analytics/reports", "VIEW_REPORT", None),
    (("customer", 4, "customer"), "/customer/profile", "VIEW_PROFILE", None),
    (("customer", 4, "customer"), "/customer/addresses", "VIEW_ADDRESSES", None),
    (("customer", 4, "customer"), "/customer/payment-methods", "VIEW_PAYMENT_METHODS", None),
    (("customer", 4, "customer"), "/customer/cart", "VIEW_CART", None),
    (("customer", 4, "customer"), "/customer/orders", "VIEW_ORDER_HISTORY", None),
    (("customer", 4, "customer"), "/customer/orders/{order_id}", "VIEW_ORDER_DETAIL", "22"),
    (("customer", 4, "customer"), "/customer/refund-requests", "VIEW_REFUND_STATUS", None),
])
def test_meaningful_authenticated_views_have_safe_single_events(actor, path, action, entity_id):
    path_key = "audit_log_id" if "{audit_log_id}" in path else "order_id"
    request = SimpleNamespace(method="GET", scope={"route": SimpleNamespace(path=path),
                                                    "query_string": b"search=password%3Dsecret"},
                              state=SimpleNamespace(audit_actor=actor),
                              path_params={path_key: int(entity_id)} if entity_id else {})
    event = event_for_request(request)
    assert event.action == action
    assert event.entity_id == entity_id
    assert event.old_values is None and event.new_values is None
    assert "password" not in str(event)


@pytest.mark.parametrize("path", [
    "/health", "/auth/me", "/customer/auth/me", "/admin/notifications/config",
    "/customer/orders/{order_id}/refund-eligibility",
    "/customer/orders/{order_id}/notifications", "/static/logo.png",
])
def test_technical_or_supporting_gets_are_excluded(path):
    request = SimpleNamespace(method="GET", scope={"route": SimpleNamespace(path=path)},
                              state=SimpleNamespace(audit_actor=("staff", 1, "admin")), path_params={})
    assert event_for_request(request) is None


def test_anonymous_get_cannot_create_view_event_and_policy_routes_are_unique():
    request = SimpleNamespace(method="GET", scope={"route": SimpleNamespace(path="/products")},
                              state=SimpleNamespace(), path_params={})
    assert event_for_request(request) is None
    assert len(POLICY) == 94
    assert sum(method == "GET" for method, _ in POLICY) == 41


def test_read_event_never_carries_state_even_if_request_state_is_polluted():
    request = SimpleNamespace(method="GET", scope={"route": SimpleNamespace(path="/customer/cart")},
                              state=SimpleNamespace(audit_actor=("customer", 4, "customer"),
                                                    audit_old_values={"order_status": "pending"},
                                                    audit_new_values={"order_status": "delivered"}),
                              path_params={})
    event = event_for_request(request)
    assert event.old_values is None and event.new_values is None


def test_composite_page_fetches_have_distinct_view_actions():
    for paths in (
        ("/analytics/workspace", "/analytics/dashboard"),
        ("/products", "/admin/catalog"),
        ("/customer/store/products", "/customer/store/products/{product_id}"),
        ("/orders", "/order-workflow/orders"),
    ):
        actions = [POLICY[("GET", path)][0] for path in paths]
        assert len(actions) == len(set(actions))


@pytest.mark.parametrize("path, action", [
    ("/orders/{order_id}/start-processing", "ORDER_STATUS_CHANGED"),
    ("/orders/{order_id}/ready-shipped", "ORDER_STATUS_CHANGED"),
    ("/customer/orders/{order_id}/cancel", "ORDER_CANCELLED"),
    ("/customer/refund-requests", "REFUND_REQUESTED"),
    ("/refund-requests/{request_id}/approve", "REFUND_APPROVED"),
    ("/refund-requests/{request_id}/reject", "REFUND_REJECTED"),
    ("/refund-requests/{request_id}/process", "REFUND_PROCESSED"),
    ("/admin/users", "STAFF_ACCOUNT_CREATED"),
    ("/admin/catalog/{product_id}", "CATALOG_UPDATED"),
])
def test_critical_business_routes_have_audit_actions(path, action):
    req = SimpleNamespace(method="PUT" if path == "/admin/catalog/{product_id}" else "POST",
                          scope={"route": SimpleNamespace(path=path)}, state=SimpleNamespace(), path_params={})
    assert event_for_request(req).action == action


def test_writer_uses_parameters_and_never_includes_raw_request():
    cursor = Cursor()
    conn = SimpleNamespace(cursor=lambda: cursor)
    req = SimpleNamespace(state=SimpleNamespace(), client=SimpleNamespace(host="127.0.0.1"))
    set_actor(req, "customer", 12, "customer")
    write_event(conn, req, AuditEvent("ORDER_CREATED", "order", "81", {"password": "do-not-log"},
                                       {"order_status": "pending", "api_key": "do-not-log"}))
    sql, params = cursor.calls[0]
    assert "INSERT INTO public.audit_logs" in sql
    assert "do-not-log" not in str(params)
    assert params[1:3] == (12, "customer")


def test_ip_uses_validated_socket_peer_not_untrusted_forwarded_headers():
    cursor = Cursor()
    request = SimpleNamespace(state=SimpleNamespace(audit_actor=("staff", 1, "admin")),
                              client=SimpleNamespace(host="127.0.0.1"),
                              headers={"x-forwarded-for": "8.8.8.8", "authorization": "Bearer secret"})
    write_event(SimpleNamespace(cursor=lambda: cursor), request, AuditEvent("VIEW_DASHBOARD", "dashboard"))
    _, params = cursor.calls[0]
    assert params[-1] == "127.0.0.1"
    assert "8.8.8.8" not in str(params) and "Bearer secret" not in str(params)


def test_successful_write_and_audit_share_one_commit(monkeypatch):
    class FakeConnection:
        def __init__(self):
            self.events = []

        def cursor(self):
            cursor = Cursor()
            original_execute = cursor.execute

            def execute(sql, params):
                self.events.append("audit_insert")
                original_execute(sql, params)

            cursor.execute = execute
            return cursor

        def commit(self):
            self.events.append("commit")

        def rollback(self):
            self.events.append("rollback")

    conn = FakeConnection()
    pool = SimpleNamespace(getconn=lambda: conn, putconn=lambda value: None)
    monkeypatch.setattr(connection_module, "_pool", pool)
    req = SimpleNamespace(method="POST", scope={"route": SimpleNamespace(path="/customer/checkout")},
                          state=SimpleNamespace(audit_actor=("customer", 12, "customer"), audit_entity_id="81"),
                          path_params={}, client=SimpleNamespace(host="127.0.0.1"))
    dependency = connection_module.get_db_connection(req, Settings(audit_trail_enabled=True))
    assert next(dependency) is conn
    conn.events.append("business_write")
    try:
        next(dependency)
    except StopIteration:
        pass
    assert conn.events == ["business_write", "audit_insert", "commit"]


@pytest.mark.parametrize("actor,path", [
    (("staff", 2, "operations_staff"), "/order-workflow/orders"),
    (("staff", 3, "analyst"), "/analytics/reports"),
    (("customer", 4, "customer"), "/customer/orders"),
])
def test_read_audit_has_actor_and_one_entry_despite_multiple_internal_selects(monkeypatch, actor, path):
    class FakeConnection:
        def __init__(self):
            self.calls = []

        def cursor(self):
            parent = self

            class AuditCursor(Cursor):
                def execute(self, sql, params):
                    parent.calls.append((sql, params))

            return AuditCursor()

        def commit(self):
            self.calls.append(("commit", None))

        def rollback(self):
            self.calls.append(("rollback", None))

    conn = FakeConnection()
    monkeypatch.setattr(connection_module, "_pool", SimpleNamespace(getconn=lambda: conn, putconn=lambda _: None))
    request = SimpleNamespace(method="GET", scope={"route": SimpleNamespace(path=path)},
                              state=SimpleNamespace(audit_actor=actor), path_params={},
                              client=SimpleNamespace(host="127.0.0.1"))
    dependency = connection_module.get_db_connection(request, Settings(audit_trail_enabled=True))
    next(dependency)
    conn.calls.extend([("internal SELECT 1", None), ("internal SELECT 2", None)])
    with pytest.raises(StopIteration):
        next(dependency)
    inserts = [(sql, params) for sql, params in conn.calls if "INSERT INTO public.audit_logs" in sql]
    assert len(inserts) == 1
    assert inserts[0][1][0:3] == actor
    assert conn.calls[-1][0] == "commit"


def test_failed_audit_insert_rolls_back_business_write(monkeypatch):
    class FailingConnection:
        def __init__(self):
            self.events = []

        def cursor(self):
            raise RuntimeError("audit insert failed")

        def commit(self):
            self.events.append("commit")

        def rollback(self):
            self.events.append("rollback")

    conn = FailingConnection()
    monkeypatch.setattr(connection_module, "_pool", SimpleNamespace(getconn=lambda: conn, putconn=lambda value: None))
    req = SimpleNamespace(method="POST", scope={"route": SimpleNamespace(path="/customer/checkout")},
                          state=SimpleNamespace(), path_params={}, client=None)
    dependency = connection_module.get_db_connection(req, Settings(audit_trail_enabled=True))
    next(dependency)
    try:
        next(dependency)
        assert False, "audit failure must propagate"
    except RuntimeError:
        pass
    assert conn.events == ["rollback"]


def test_audit_navigation_is_admin_only():
    assert "Audit Trail" in navigation_for_role("admin")
    assert "Audit Trail" not in navigation_for_role("operations_staff")
    assert "Audit Trail" not in navigation_for_role("analyst")
    assert "Audit Trail" not in CUSTOMER_ACCOUNT_NAVIGATION


def test_admin_api_refuses_non_admin_and_has_no_mutation_routes():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_settings] = lambda: Settings(audit_trail_enabled=False)
    app.dependency_overrides[get_db_connection] = lambda: SimpleNamespace()
    assert {method for route in router.routes if route.path.startswith("/admin/audit-logs")
            for method in route.methods} == {"GET"}
    for role, expected in ((Role.ADMIN, 503), (Role.OPERATIONS_STAFF, 403), (Role.ANALYST, 403)):
        app.dependency_overrides[get_current_user] = lambda role=role: SimpleNamespace(role=role)
        with TestClient(app) as client:
            assert client.get("/admin/audit-logs").status_code == expected
            assert client.get("/admin/audit-logs/1").status_code == expected
            assert client.delete("/admin/audit-logs/1").status_code == 405
    app.dependency_overrides.clear()


def test_admin_can_filter_and_page_audit_entries_without_raw_sql_values():
    class QueryCursor(Cursor):
        def fetchone(self):
            return {"total": 1}

        def fetchall(self):
            return [{"audit_log_id": 9, "actor_type": "staff", "actor_role": "admin",
                     "action": "PRODUCT_CREATED", "entity_type": "product", "entity_id": "7"}]

    cursor = QueryCursor()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role=Role.ADMIN)
    app.dependency_overrides[get_settings] = lambda: Settings(audit_trail_enabled=True)
    app.dependency_overrides[get_db_connection] = lambda: SimpleNamespace(cursor=lambda **kwargs: cursor)
    with TestClient(app) as client:
        response = client.get("/admin/audit-logs", params={"action": "PRODUCT_CREATED", "search": "product", "limit": 10})
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["entity_id"] == "7"
    assert len(cursor.calls) == 2
    assert all("PRODUCT_CREATED" not in sql for sql, _ in cursor.calls)
    assert all("PRODUCT_CREATED" in params for _, params in cursor.calls)


def test_auth_login_actor_domains_and_failure_do_not_log_credentials():
    from fastapi import HTTPException
    from api.routers import auth, customer_auth
    from api.schemas.auth import LoginRequest
    from api.schemas.customer_auth import CustomerLoginRequest

    staff_req = SimpleNamespace(state=SimpleNamespace(), method="POST",
                                scope={"route": SimpleNamespace(path="/auth/login")}, path_params={})
    staff_service = SimpleNamespace(login=lambda **kwargs: ("token", 1800),
                                    authenticate_token=lambda token: SimpleNamespace(app_user_id=3, role=Role.ADMIN))
    auth.login(LoginRequest(identifier="someone", password="do-not-log"), staff_req, staff_service)
    assert staff_req.state.audit_actor == ("staff", 3, "admin")
    assert "do-not-log" not in str(event_for_request(staff_req))

    customer_req = SimpleNamespace(state=SimpleNamespace(), method="POST",
                                   scope={"route": SimpleNamespace(path="/customer/auth/login")}, path_params={})
    customer_service = SimpleNamespace(login=lambda *args: ("token", 1800),
                                       authenticate_token=lambda token: SimpleNamespace(customer_account_id=8))
    customer_auth.login(CustomerLoginRequest(email="person@example.com", password="do-not-log"),
                        customer_req, customer_service)
    assert customer_req.state.audit_actor == ("customer", 8, "customer")

    def failed_login(**kwargs):
        raise HTTPException(401, "Invalid credentials")

    failed_req = SimpleNamespace(state=SimpleNamespace())
    try:
        auth.login(LoginRequest(identifier="person", password="do-not-log"), failed_req,
                   SimpleNamespace(login=failed_login))
        assert False
    except HTTPException:
        pass
    assert failed_req.state.audit_failed_login is True
    assert "do-not-log" not in str(failed_req.state.__dict__)


def test_reset_audit_event_has_no_reset_code():
    request = SimpleNamespace(method="POST", scope={"route": SimpleNamespace(path="/customer/auth/reset-password")},
                              state=SimpleNamespace(), path_params={})
    event = event_for_request(request)
    assert event.action == "CUSTOMER_PASSWORD_RESET_COMPLETED"
    assert event.old_values is None and event.new_values is None
