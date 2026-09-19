"""Post-deployment Audit Trail checks against the opted-in local database."""
import os
import secrets
from dataclasses import replace
from types import SimpleNamespace

import psycopg2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.audit import router as audit_router
from core.config import Settings, get_settings
from core.dependencies import get_db_connection
from core.security import create_access_token, create_customer_access_token
from services.audit import AuditEvent, event_for_request, set_actor, write_event

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def migrated_connection():
    if os.getenv("RUN_DB_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_DB_INTEGRATION_TESTS=1 to use PostgreSQL")
    settings = Settings.from_environment()
    if not settings.audit_trail_enabled:
        pytest.skip("Set AUDIT_TRAIL_ENABLED=true to run deployed Audit Trail tests")
    conn = psycopg2.connect(**settings.database_kwargs())
    conn.set_session(readonly=True, autocommit=True)
    try:
        yield conn
    finally:
        conn.close()


def test_audit_table_indexes_and_constraints(migrated_connection):
    with migrated_connection.cursor() as cur:
        cur.execute("SELECT to_regclass('public.audit_logs')")
        assert cur.fetchone()[0] == "audit_logs"
        cur.execute("SELECT indexname FROM pg_indexes WHERE schemaname='public' AND tablename='audit_logs'")
        names = {row[0] for row in cur.fetchall()}
        assert {"audit_logs_pkey", "idx_audit_logs_created_at", "idx_audit_logs_actor",
                "idx_audit_logs_actor_role", "idx_audit_logs_action", "idx_audit_logs_entity"} <= names
        cur.execute("SELECT conname FROM pg_constraint WHERE conrelid='public.audit_logs'::regclass")
        constraints = {row[0] for row in cur.fetchall()}
        assert {"ck_audit_actor_type", "ck_audit_actor_role", "ck_audit_action",
                "ck_audit_old_values", "ck_audit_new_values"} <= constraints


def test_canonical_counts_unchanged_after_migration(migrated_connection):
    expected = {"products": 4, "orders": 32313, "order_items": 40025, "order_item_refunds": 1731}
    with migrated_connection.cursor() as cur:
        for table, count in expected.items():
            cur.execute(f"SELECT count(*) FROM public.canonical_{table}")
            assert cur.fetchone()[0] == count


def test_audit_storage_admin_access_and_other_role_refusal(migrated_connection):
    """Exercise real SQL and authenticated API reads; roll back every test row."""
    settings = replace(
        Settings.from_environment(),
        jwt_secret_key=secrets.token_urlsafe(48), notification_mode="mock",
        smtp_live_send_enabled=False, sms_live_send_enabled=False,
        infobip_live_send_enabled=False, audit_trail_enabled=True,
    )
    conn = psycopg2.connect(**settings.database_kwargs())
    conn.autocommit = False
    expected = {"products": 4, "orders": 32313, "order_items": 40025, "order_item_refunds": 1731}
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database()")
            assert cur.fetchone()[0] == "retailmetrics"
            users = {}
            for role in ("admin", "operations_staff", "analyst"):
                cur.execute("""SELECT app_user_id, token_version FROM public.app_users
                               WHERE role=%s AND is_active AND (locked_until IS NULL OR locked_until<=NOW())
                               ORDER BY app_user_id LIMIT 1""", (role,))
                user = cur.fetchone()
                assert user is not None, f"An active unlocked {role} is required for RBAC verification"
                users[role] = SimpleNamespace(app_user_id=user[0], token_version=user[1])
            cur.execute("""SELECT customer_account_id, token_version FROM public.customer_accounts
                           WHERE is_active AND (locked_until IS NULL OR locked_until<=NOW())
                           ORDER BY customer_account_id LIMIT 1""")
            customer = cur.fetchone()
            assert customer is not None, "An active unlocked customer is required for token-domain verification"
            customer_account = SimpleNamespace(customer_account_id=customer[0], token_version=customer[1])
            cur.execute("SELECT product_id FROM public.canonical_products ORDER BY product_id LIMIT 1")
            product_id = cur.fetchone()[0]
            assert product_id is not None

        actor_id = users["admin"].app_user_id
        read_request = SimpleNamespace(
            method="GET", scope={"route": SimpleNamespace(path="/products/{product_id}"),
                                 "query_string": b"search=password%3Dnever-store"},
            path_params={"product_id": product_id}, state=SimpleNamespace(),
            client=SimpleNamespace(host="127.0.0.1"),
        )
        set_actor(read_request, "staff", actor_id, "admin")
        read_event = event_for_request(read_request)
        assert read_event is not None and read_event.action == "VIEW_PRODUCT_DETAIL"
        write_event(conn, read_request, read_event)
        with conn.cursor() as cur:
            cur.execute("SELECT currval(pg_get_serial_sequence('public.audit_logs','audit_log_id'))")
            read_id = cur.fetchone()[0]

        mutation_request = SimpleNamespace(state=SimpleNamespace(audit_actor=("staff", actor_id, "admin")),
                                           client=SimpleNamespace(host="127.0.0.1"))
        write_event(conn, mutation_request, AuditEvent(
            "PRODUCT_UPDATED", "product", str(product_id),
            {"is_available": False, "password": "never-store", "reset_token": "never-store"},
            {"is_available": True, "api_key": "never-store", "authorization": "never-store"},
        ))
        with conn.cursor() as cur:
            cur.execute("SELECT currval(pg_get_serial_sequence('public.audit_logs','audit_log_id'))")
            mutation_id = cur.fetchone()[0]
            cur.execute("""SELECT action, actor_type, actor_id, actor_role, entity_type, entity_id,
                                  old_values, new_values, ip_address
                           FROM public.audit_logs WHERE audit_log_id IN (%s,%s)
                           ORDER BY audit_log_id""", (read_id, mutation_id))
            read_row, mutation_row = cur.fetchall()
        assert read_row[:6] == ("VIEW_PRODUCT_DETAIL", "staff", actor_id, "admin", "product", str(product_id))
        assert read_row[6] is None and read_row[7] is None
        assert read_row[8] == "127.0.0.1"
        assert mutation_row[0] == "PRODUCT_UPDATED"
        assert mutation_row[6] == {"is_available": False}
        assert mutation_row[7] == {"is_available": True}
        assert "never-store" not in str((read_row, mutation_row))

        app = FastAPI()
        app.include_router(audit_router)
        app.dependency_overrides[get_settings] = lambda: settings
        app.dependency_overrides[get_db_connection] = lambda: conn
        tokens = {role: create_access_token(user, settings)[0] for role, user in users.items()}
        customer_token = create_customer_access_token(customer_account, settings)[0]
        with TestClient(app) as client:
            admin_headers = {"Authorization": f"Bearer {tokens['admin']}"}
            detail = client.get(f"/admin/audit-logs/{read_id}", headers=admin_headers)
            assert detail.status_code == 200
            assert detail.json()["action"] == "VIEW_PRODUCT_DETAIL"
            filtered = client.get("/admin/audit-logs", params={"action": "PRODUCT_UPDATED", "entity_id": str(product_id)}, headers=admin_headers)
            assert filtered.status_code == 200
            assert any(row["audit_log_id"] == mutation_id for row in filtered.json()["items"])
            for role in ("operations_staff", "analyst"):
                headers = {"Authorization": f"Bearer {tokens[role]}"}
                assert client.get("/admin/audit-logs", headers=headers).status_code == 403
                assert client.get(f"/admin/audit-logs/{read_id}", headers=headers).status_code == 403
            customer_headers = {"Authorization": f"Bearer {customer_token}"}
            assert client.get("/admin/audit-logs", headers=customer_headers).status_code in {401, 403}
            assert client.get(f"/admin/audit-logs/{read_id}", headers=customer_headers).status_code in {401, 403}
            assert client.put(f"/admin/audit-logs/{read_id}", headers=admin_headers, json={}).status_code == 405
            assert client.delete(f"/admin/audit-logs/{read_id}", headers=admin_headers).status_code == 405

        with migrated_connection.cursor() as cur:
            for table, count in expected.items():
                cur.execute(f"SELECT count(*) FROM public.canonical_{table}")
                assert cur.fetchone()[0] == count
    finally:
        # Inserted audit rows are never committed or visible to another connection.
        conn.rollback()
        conn.close()
