from __future__ import annotations

import os
import secrets
import uuid
from dataclasses import replace

import psycopg2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.auth import router as auth_router
from api.routers.business import router as business_router
from core.config import Settings, get_settings
from core.dependencies import get_current_user
from core.security import hash_password
from db.connection import get_db_connection


pytestmark = pytest.mark.integration
PASSWORD = "Business-integration-1!"
NOW = "2026-01-01T00:00:00"
CANONICAL_VIEWS = (
    "canonical_products",
    "canonical_orders",
    "canonical_order_items",
    "canonical_order_item_refunds",
)


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def connect(settings: Settings):
    return psycopg2.connect(**settings.database_kwargs())


def canonical_counts(settings: Settings) -> tuple[int, ...]:
    conn = connect(settings)
    try:
        with conn.cursor() as cur:
            values = []
            for view in CANONICAL_VIEWS:
                cur.execute(f"SELECT COUNT(*) FROM public.{view}")
                values.append(int(cur.fetchone()[0]))
            return tuple(values)
    finally:
        conn.close()


def migration002_is_applied(settings: Settings) -> bool:
    conn = connect(settings)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'orders'
                      AND column_name = 'record_origin'
                )
                """
            )
            return bool(cur.fetchone()[0])
    finally:
        conn.close()


def insert_user(settings: Settings, username: str, role: str) -> int:
    conn = connect(settings)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO public.app_users
                        (username, email, password_hash, role)
                    VALUES (%s, %s, %s, %s)
                    RETURNING app_user_id
                    """,
                    (username, f"{username}@example.com", hash_password(PASSWORD), role),
                )
                return int(cur.fetchone()[0])
    finally:
        conn.close()


@pytest.fixture(scope="module")
def crud_context():
    if os.getenv("RUN_DB_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_DB_INTEGRATION_TESTS=1 to use the real database")

    previous_secret = os.environ.get("JWT_SECRET_KEY")
    os.environ["JWT_SECRET_KEY"] = secrets.token_urlsafe(48)
    get_settings.cache_clear()
    settings = replace(Settings.from_environment(), auth_expose_reset_token=True)
    prefix = f"rmitcrud_{uuid.uuid4().hex[:12]}_"
    expected_database = os.getenv("DB_INTEGRATION_EXPECTED_DATABASE", "retailmetrics")
    baseline = canonical_counts(settings)

    target_probe = connect(settings)
    try:
        with target_probe.cursor() as cur:
            cur.execute("SELECT current_database()")
            assert cur.fetchone()[0] == expected_database
    finally:
        target_probe.close()

    admin_name = prefix + "admin"
    operations_name = prefix + "operations"
    insert_user(settings, admin_name, "admin")
    insert_user(settings, operations_name, "operations_staff")

    probe = connect(settings)
    try:
        with probe.cursor() as cur:
            cur.execute(
                """
                SELECT ws.website_session_id, ws.user_id
                FROM public.website_sessions ws
                WHERE NOT EXISTS (
                    SELECT 1 FROM public.orders o
                    WHERE o.website_session_id = ws.website_session_id
                )
                ORDER BY ws.website_session_id
                LIMIT 5
                """
            )
            free_sessions = [(int(row[0]), int(row[1])) for row in cur.fetchall()]
            cur.execute("SELECT product_id FROM public.canonical_products ORDER BY product_id LIMIT 1")
            canonical_product = int(cur.fetchone()[0])
            cur.execute("SELECT order_id FROM public.canonical_orders ORDER BY order_id LIMIT 1")
            canonical_order = int(cur.fetchone()[0])
            cur.execute("SELECT order_item_id FROM public.canonical_order_items ORDER BY order_item_id LIMIT 1")
            canonical_item = int(cur.fetchone()[0])
            cur.execute("SELECT order_item_refund_id FROM public.canonical_order_item_refunds ORDER BY order_item_refund_id LIMIT 1")
            canonical_refund = int(cur.fetchone()[0])
        assert len(free_sessions) >= 2
    finally:
        probe.close()

    def db_override():
        conn = connect(settings)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(business_router)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db_connection] = db_override

    try:
        with TestClient(app) as client:
            admin_token = client.post(
                "/auth/login", json={"identifier": admin_name, "password": PASSWORD}
            ).json()["access_token"]
            operations_token = client.post(
                "/auth/login",
                json={"identifier": operations_name, "password": PASSWORD},
            ).json()["access_token"]
            analyst_name = prefix + "analyst"
            registration = client.post(
                "/auth/register",
                json={
                    "username": analyst_name,
                    "email": f"{analyst_name}@example.com",
                    "password": PASSWORD,
                },
            )
            assert registration.status_code == 201
            analyst_token = client.post(
                "/auth/login", json={"identifier": analyst_name, "password": PASSWORD}
            ).json()["access_token"]
            yield {
                "client": client,
                "settings": settings,
                "prefix": prefix,
                "admin": admin_token,
                "operations": operations_token,
                "analyst": analyst_token,
                "free_sessions": free_sessions,
                "canonical_ids": (
                    canonical_product,
                    canonical_order,
                    canonical_item,
                    canonical_refund,
                ),
                "baseline": baseline,
                "expected_database": expected_database,
            }
    finally:
        cleanup = connect(settings)
        try:
            with cleanup:
                with cleanup.cursor() as cur:
                    cur.execute(
                        "SELECT app_user_id FROM public.app_users WHERE username LIKE %s",
                        (prefix + "%",),
                    )
                    ids = [int(row[0]) for row in cur.fetchall()]
                    if ids:
                        for table in (
                            "order_item_refunds",
                            "order_items",
                            "orders",
                            "products",
                        ):
                            cur.execute(
                                f"DELETE FROM public.{table} WHERE created_by_app_user_id = ANY(%s)",
                                (ids,),
                            )
                        cur.execute(
                            "DELETE FROM public.app_users WHERE app_user_id = ANY(%s)",
                            (ids,),
                        )
            assert canonical_counts(settings) == baseline
        finally:
            cleanup.close()
            if previous_secret is None:
                os.environ.pop("JWT_SECRET_KEY", None)
            else:
                os.environ["JWT_SECRET_KEY"] = previous_secret
            get_settings.cache_clear()


def test_read_pagination_filters_and_rbac_refusals(crud_context) -> None:
    client = crud_context["client"]
    analyst = bearer(crud_context["analyst"])
    operations = bearer(crud_context["operations"])

    products = client.get("/products?limit=2&offset=0&origin=imported", headers=analyst)
    assert products.status_code == 200
    assert len(products.json()["items"]) == 2
    assert products.json()["total"] == 4
    assert client.get("/website-sessions?limit=1", headers=analyst).status_code == 200
    eligible = client.get("/website-sessions?has_order=false&limit=1", headers=analyst)
    assert eligible.status_code == 200
    assert eligible.json()["items"]
    assert client.get("/website-pageviews?limit=1", headers=analyst).status_code == 200

    assert client.post(
        "/products",
        headers=operations,
        json={"created_at": NOW, "product_name": "Forbidden product"},
    ).status_code == 403
    assert client.post(
        "/orders",
        headers=analyst,
        json={
            "created_at": NOW,
            "website_session_id": crud_context["free_sessions"][1][0],
            "user_id": crud_context["free_sessions"][1][1],
            "primary_product_id": crud_context["canonical_ids"][0],
            "items_purchased": 1,
            "price_usd": "10.00",
            "cogs_usd": "4.00",
        },
    ).status_code == 403


def test_all_imported_entities_are_protected(crud_context) -> None:
    client = crud_context["client"]
    admin = bearer(crud_context["admin"])
    product_id, order_id, item_id, refund_id = crud_context["canonical_ids"]
    targets = (
        (f"/products/{product_id}", client.get(f"/products/{product_id}", headers=admin)),
        (f"/orders/{order_id}", client.get(f"/orders/{order_id}", headers=admin)),
        (f"/order-items/{item_id}", client.get(f"/order-items/{item_id}", headers=admin)),
        (f"/refunds/{refund_id}", client.get(f"/refunds/{refund_id}", headers=admin)),
    )
    for path, read_response in targets:
        assert read_response.status_code == 200
        version = read_response.json()["row_version"]
        assert client.delete(f"{path}?row_version={version}", headers=admin).status_code == 403


def test_staff_item_under_imported_order_is_clean_conflict(crud_context) -> None:
    if not migration002_is_applied(crud_context["settings"]):
        pytest.skip("Migration-002 origin validation requires the migrated schema")

    client = crud_context["client"]
    operations = bearer(crud_context["operations"])
    imported_order_id = crud_context["canonical_ids"][1]
    product_id = crud_context["canonical_ids"][0]

    before = connect(crud_context["settings"])
    try:
        with before.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM public.order_items WHERE order_id = %s "
                "AND created_by_app_user_id IS NOT NULL",
                (imported_order_id,),
            )
            count_before = int(cur.fetchone()[0])
    finally:
        before.close()

    response = client.post(
        "/order-items",
        headers=operations,
        json={
            "created_at": NOW,
            "order_id": imported_order_id,
            "product_id": product_id,
            "is_primary_item": 0,
            "price_usd": "1.00",
            "cogs_usd": "0.50",
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Order items can only be added to application-created staff orders."
    )

    after = connect(crud_context["settings"])
    try:
        with after.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM public.order_items WHERE order_id = %s "
                "AND created_by_app_user_id IS NOT NULL",
                (imported_order_id,),
            )
            assert int(cur.fetchone()[0]) == count_before
    finally:
        after.close()


def test_full_web_crud_validation_and_concurrency(crud_context) -> None:
    client = crud_context["client"]
    admin = bearer(crud_context["admin"])
    operations = bearer(crud_context["operations"])
    session_id, shopper_id = crud_context["free_sessions"][0]

    product = client.post(
        "/products",
        headers=admin,
        json={"created_at": NOW, "product_name": "Integration product"},
    )
    assert product.status_code == 201
    product_row = product.json()
    assert product_row["created_by_app_user_id"] is not None
    assert product_row["origin"] == "web"
    product_id = product_row["product_id"]
    if migration002_is_applied(crud_context["settings"]):
        check_conn = connect(crud_context["settings"])
        try:
            with check_conn.cursor() as cur:
                cur.execute("SELECT record_origin FROM public.products WHERE product_id=%s", (product_id,))
                assert cur.fetchone()[0] == "staff"
        finally:
            check_conn.close()

    updated_product = client.put(
        f"/products/{product_id}",
        headers=admin,
        json={"created_at": NOW, "product_name": "Updated integration product", "row_version": 1},
    )
    assert updated_product.status_code == 200
    assert updated_product.json()["row_version"] == 2
    assert client.put(
        f"/products/{product_id}",
        headers=admin,
        json={"created_at": NOW, "product_name": "Stale", "row_version": 1},
    ).status_code == 409
    assert client.delete(
        f"/products/{product_id}?row_version=1", headers=admin
    ).status_code == 409

    order_payload = {
        "created_at": NOW,
        "website_session_id": session_id,
        "user_id": shopper_id,
        "primary_product_id": product_id,
        "items_purchased": 1,
        "price_usd": "10.00",
        "cogs_usd": "4.00",
    }
    order = client.post("/orders", headers=operations, json=order_payload)
    assert order.status_code == 201
    order_id = order.json()["order_id"]
    if migration002_is_applied(crud_context["settings"]):
        check_conn = connect(crud_context["settings"])
        try:
            with check_conn.cursor() as cur:
                cur.execute(
                    "SELECT record_origin, order_status FROM public.orders WHERE order_id=%s",
                    (order_id,),
                )
                assert cur.fetchone() == ("staff", "ready_shipped")
        finally:
            check_conn.close()
    updated_order = client.put(
        f"/orders/{order_id}",
        headers=operations,
        json={**order_payload, "row_version": 1},
    )
    assert updated_order.status_code == 200
    assert updated_order.json()["row_version"] == 2
    assert client.post("/orders", headers=operations, json=order_payload).status_code == 409

    bad_order = {**order_payload, "website_session_id": 999999999999999}
    assert client.post("/orders", headers=operations, json=bad_order).status_code == 422
    assert client.post(
        "/orders",
        headers=operations,
        json={**order_payload, "website_session_id": crud_context["free_sessions"][1][0], "user_id": 999999999999999},
    ).status_code == 422

    item_payload = {
        "created_at": NOW,
        "order_id": order_id,
        "product_id": product_id,
        "is_primary_item": 1,
        "price_usd": "10.00",
        "cogs_usd": "4.00",
    }
    bad_item = {**item_payload, "product_id": 999999999999999}
    assert client.post("/order-items", headers=operations, json=bad_item).status_code == 422
    item = client.post("/order-items", headers=operations, json=item_payload)
    assert item.status_code == 201
    item_id = item.json()["order_item_id"]
    if migration002_is_applied(crud_context["settings"]):
        check_conn = connect(crud_context["settings"])
        try:
            with check_conn.cursor() as cur:
                cur.execute("SELECT record_origin FROM public.order_items WHERE order_item_id=%s", (item_id,))
                assert cur.fetchone()[0] == "staff"
        finally:
            check_conn.close()
    updated_item = client.put(
        f"/order-items/{item_id}",
        headers=operations,
        json={**item_payload, "cogs_usd": "3.50", "row_version": 1},
    )
    assert updated_item.status_code == 200
    assert updated_item.json()["row_version"] == 2

    refund_payload = {
        "created_at": NOW,
        "order_item_id": item_id,
        "order_id": order_id,
        "refund_amount_usd": "6.00",
    }
    assert client.post(
        "/refunds", headers=operations, json={**refund_payload, "order_id": crud_context["canonical_ids"][1]}
    ).status_code == 422
    assert client.post(
        "/refunds", headers=operations, json={**refund_payload, "refund_amount_usd": "10.01"}
    ).status_code == 422
    refund = client.post("/refunds", headers=operations, json=refund_payload)
    assert refund.status_code == 201
    refund_id = refund.json()["order_item_refund_id"]
    if migration002_is_applied(crud_context["settings"]):
        check_conn = connect(crud_context["settings"])
        try:
            with check_conn.cursor() as cur:
                cur.execute(
                    "SELECT record_origin, refund_request_id FROM public.order_item_refunds "
                    "WHERE order_item_refund_id=%s",
                    (refund_id,),
                )
                assert cur.fetchone() == ("staff", None)
                for view in CANONICAL_VIEWS:
                    cur.execute(f"SELECT COUNT(*) FROM public.{view}")
                    assert int(cur.fetchone()[0]) == crud_context["baseline"][CANONICAL_VIEWS.index(view)]
        finally:
            check_conn.close()

    assert client.post(
        "/refunds", headers=operations, json={**refund_payload, "refund_amount_usd": "4.01"}
    ).status_code == 422
    refund_update = {**refund_payload, "refund_amount_usd": "5.00", "row_version": 1}
    updated_refund = client.put(f"/refunds/{refund_id}", headers=operations, json=refund_update)
    assert updated_refund.status_code == 200
    assert updated_refund.json()["row_version"] == 2
    assert client.put(f"/refunds/{refund_id}", headers=operations, json=refund_update).status_code == 409

    assert client.delete(f"/orders/{order_id}?row_version=2", headers=operations).status_code == 409
    assert client.delete(f"/refunds/{refund_id}?row_version=2", headers=operations).status_code == 200
    assert client.delete(f"/order-items/{item_id}?row_version=2", headers=operations).status_code == 200
    assert client.delete(f"/orders/{order_id}?row_version=2", headers=operations).status_code == 200
    assert client.delete(f"/products/{product_id}?row_version=2", headers=admin).status_code == 200
    assert canonical_counts(crud_context["settings"]) == crud_context["baseline"]


def test_migration002_rejects_inconsistent_omitted_or_explicit_origins(crud_context) -> None:
    if not migration002_is_applied(crud_context["settings"]):
        pytest.skip("Migration-002 trigger audit requires the migrated schema")

    conn = connect(crud_context["settings"])
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT app_user_id FROM public.app_users ORDER BY app_user_id LIMIT 1")
            staff_id = int(cur.fetchone()[0])
            with pytest.raises(psycopg2.errors.CheckViolation):
                cur.execute(
                    """INSERT INTO public.products
                       (created_at, product_name, created_by_app_user_id, record_origin)
                       VALUES (NOW(), 'Rejected imported application row', %s, 'imported')""",
                    (staff_id,),
                )
        conn.rollback()

        with conn.cursor() as cur:
            cur.execute("SELECT order_id FROM public.canonical_orders ORDER BY order_id LIMIT 1")
            imported_order_id = int(cur.fetchone()[0])
            cur.execute("SELECT product_id FROM public.canonical_products ORDER BY product_id LIMIT 1")
            product_id = int(cur.fetchone()[0])
            with pytest.raises(psycopg2.errors.CheckViolation):
                cur.execute(
                    """INSERT INTO public.order_items
                       (created_at, order_id, product_id, is_primary_item,
                        price_usd, cogs_usd, created_by_app_user_id)
                       VALUES (NOW(), %s, %s, 0, 1.00, 0.50, %s)""",
                    (imported_order_id, product_id, staff_id),
                )
        conn.rollback()
    finally:
        conn.close()
