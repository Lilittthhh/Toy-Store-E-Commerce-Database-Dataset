from __future__ import annotations

import os
import secrets
import uuid
from contextlib import asynccontextmanager
from dataclasses import replace
from decimal import Decimal

import psycopg2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.auth import router as staff_auth_router
from api.routers.business import router as business_router
from api.routers.checkout import router as checkout_router
from api.routers.customer_auth import router as customer_auth_router
from api.routers.order_workflow import router as workflow_router
from api.routers.refund_workflow import router as refund_router
from core.config import Settings, get_settings
from core.security import hash_password
from db.connection import close_pool, initialize_pool
from services.notifications.outbox import NotificationOutbox


pytestmark = pytest.mark.integration
PASSWORD = "Order-workflow-1!"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def workflow_context():
    if os.getenv("RUN_DB_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_DB_INTEGRATION_TESTS=1 to use PostgreSQL")
    old_secret = os.environ.get("JWT_SECRET_KEY")
    os.environ["JWT_SECRET_KEY"] = secrets.token_urlsafe(48)
    get_settings.cache_clear()
    settings = replace(
        Settings.from_environment(), jwt_secret_key=os.environ["JWT_SECRET_KEY"],
        notification_mode="mock", smtp_live_send_enabled=False,
        sms_live_send_enabled=False, infobip_live_send_enabled=False,
    )
    marker = f"rmitworkflow_{uuid.uuid4().hex[:10]}"
    tracked = ("app_users", "customer_accounts", "customer_profiles", "orders", "order_items", "order_shipping_addresses", "order_payments")
    setup = psycopg2.connect(**settings.database_kwargs())
    state: dict = {"settings": settings, "marker": marker}
    try:
        with setup:
            with setup.cursor() as cur:
                baseline = {}
                for table in tracked:
                    cur.execute(f"SELECT COUNT(*) FROM public.{table}")
                    baseline[table] = int(cur.fetchone()[0])
                cur.execute("SELECT product_id FROM public.canonical_products ORDER BY product_id LIMIT 1")
                product_id = int(cur.fetchone()[0])
                cur.execute("SELECT order_id FROM public.canonical_orders ORDER BY order_id LIMIT 1")
                imported_order = int(cur.fetchone()[0])
                staff_ids = {}
                for label, role in (("admin", "admin"), ("ops", "operations_staff"), ("analyst", "analyst")):
                    username = f"{marker}_{label}"
                    cur.execute(
                        "INSERT INTO public.app_users(username,email,password_hash,role) VALUES(%s,%s,%s,%s) RETURNING app_user_id",
                        (username, f"{username}@example.com", hash_password(PASSWORD), role),
                    )
                    staff_ids[label] = int(cur.fetchone()[0])
                customer_email = f"{marker}_customer@example.com"
                cur.execute(
                    "INSERT INTO public.customer_accounts(email,password_hash) VALUES(%s,%s) RETURNING customer_account_id",
                    (customer_email, hash_password(PASSWORD)),
                )
                customer_id = int(cur.fetchone()[0])
                cur.execute("INSERT INTO public.customer_profiles(customer_account_id,first_name,last_name,phone) VALUES(%s,'Workflow','Customer','09171234567')", (customer_id,))
                other_email = f"{marker}_other@example.com"
                cur.execute(
                    "INSERT INTO public.customer_accounts(email,password_hash) VALUES(%s,%s) RETURNING customer_account_id",
                    (other_email, hash_password(PASSWORD)),
                )
                other_customer_id = int(cur.fetchone()[0])
                cur.execute("INSERT INTO public.customer_profiles(customer_account_id,first_name,last_name,phone) VALUES(%s,'Other','Customer','09171234568')", (other_customer_id,))

                def customer_order(method: str = "card") -> tuple[int, int]:
                    cur.execute(
                        """INSERT INTO public.orders
                           (created_at,website_session_id,user_id,primary_product_id,items_purchased,
                            price_usd,cogs_usd,record_origin,customer_account_id,order_status)
                           VALUES(NOW(),NULL,NULL,%s,1,10,4,'customer',%s,'pending') RETURNING order_id""",
                        (product_id, customer_id),
                    )
                    order_id = int(cur.fetchone()[0])
                    cur.execute(
                        """INSERT INTO public.order_items
                           (created_at,order_id,product_id,is_primary_item,price_usd,cogs_usd,record_origin)
                           VALUES(NOW(),%s,%s,1,10,4,'customer') RETURNING order_item_id""",
                        (order_id, product_id),
                    )
                    item_id = int(cur.fetchone()[0])
                    cur.execute(
                        """INSERT INTO public.order_shipping_addresses
                           (order_id,customer_account_id,recipient_first_name,recipient_last_name,
                            address_line_1,city,province_region,postal_code,country_code)
                           VALUES(%s,%s,'Workflow','Customer','1 Test Lane','Manila','Metro Manila','1000','PH')""",
                        (order_id, customer_id),
                    )
                    payment_status = "pending" if method == "cash_on_delivery" else "paid"
                    cur.execute(
                        """INSERT INTO public.order_payments
                           (order_id,customer_account_id,method_type,payment_display_snapshot,payment_status,amount_usd)
                           VALUES(%s,%s,%s,'Classroom simulation',%s,10)""",
                        (order_id, customer_id, method, payment_status),
                    )
                    return order_id, item_id

                admin_order, admin_item = customer_order()
                ops_order, ops_item = customer_order()
                cancel_order, cancel_item = customer_order()
                race_order, race_item = customer_order()
                cod_order, cod_item = customer_order("cash_on_delivery")
                cur.execute(
                    """SELECT ws.website_session_id,ws.user_id FROM public.website_sessions ws
                       WHERE NOT EXISTS (SELECT 1 FROM public.orders o WHERE o.website_session_id=ws.website_session_id)
                       ORDER BY ws.website_session_id LIMIT 1"""
                )
                session_id, dataset_user_id = cur.fetchone()
                cur.execute(
                    """INSERT INTO public.orders
                       (created_at,website_session_id,user_id,primary_product_id,items_purchased,
                        price_usd,cogs_usd,created_by_app_user_id,record_origin,order_status)
                       VALUES(NOW(),%s,%s,%s,1,10,4,%s,'staff','ready_shipped') RETURNING order_id""",
                    (session_id, dataset_user_id, product_id, staff_ids["admin"]),
                )
                staff_order = int(cur.fetchone()[0])
                state.update(locals())
    finally:
        setup.close()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        initialize_pool(settings)
        try:
            yield
        finally:
            close_pool()

    app = FastAPI(lifespan=lifespan)
    for router in (staff_auth_router, business_router, customer_auth_router, checkout_router, workflow_router, refund_router):
        app.include_router(router)
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            staff = {
                label: client.post("/auth/login", json={"identifier": f"{marker}_{label}", "password": PASSWORD}).json()["access_token"]
                for label in ("admin", "ops", "analyst")
            }
            customer = client.post("/customer/auth/login", json={"email": customer_email, "password": PASSWORD}).json()["access_token"]
            other_customer = client.post("/customer/auth/login", json={"email": other_email, "password": PASSWORD}).json()["access_token"]
            state.update({"client": client, "staff": staff, "customer": customer, "other_customer": other_customer})
            yield state
    finally:
        cleanup = psycopg2.connect(**settings.database_kwargs())
        try:
            with cleanup:
                with cleanup.cursor() as cur:
                    customer_orders = [state[key] for key in ("admin_order", "ops_order", "cancel_order", "race_order", "cod_order")]
                    cur.execute("DELETE FROM public.notification_outbox WHERE order_id=ANY(%s)", (customer_orders,))
                    cur.execute("DELETE FROM public.order_shipping_addresses WHERE order_id=ANY(%s)", (customer_orders,))
                    cur.execute("DELETE FROM public.order_payments WHERE order_id=ANY(%s)", (customer_orders,))
                    cur.execute("DELETE FROM public.order_items WHERE order_id=ANY(%s)", (customer_orders,))
                    cur.execute("DELETE FROM public.orders WHERE order_id=ANY(%s)", (customer_orders,))
                    cur.execute("DELETE FROM public.orders WHERE order_id=%s", (state["staff_order"],))
                    cur.execute("DELETE FROM public.customer_profiles WHERE customer_account_id=ANY(%s)", ([state["customer_id"], state["other_customer_id"]],))
                    cur.execute("DELETE FROM public.customer_accounts WHERE customer_account_id=ANY(%s)", ([state["customer_id"], state["other_customer_id"]],))
                    cur.execute("DELETE FROM public.app_users WHERE username LIKE %s", (marker + "_%",))
                    for table in tracked:
                        cur.execute(f"SELECT COUNT(*) FROM public.{table}")
                        assert int(cur.fetchone()[0]) == state["baseline"][table], table
        finally:
            cleanup.close()
            if old_secret is None:
                os.environ.pop("JWT_SECRET_KEY", None)
            else:
                os.environ["JWT_SECRET_KEY"] = old_secret
            get_settings.cache_clear()


def test_authorization_origin_protection_and_pending_transitions(workflow_context) -> None:
    c = workflow_context["client"]
    admin, ops, analyst = (bearer(workflow_context["staff"][key]) for key in ("admin", "ops", "analyst"))
    customer = bearer(workflow_context["customer"])
    other_customer = bearer(workflow_context["other_customer"])
    listed = c.get("/order-workflow/orders", headers=analyst)
    assert listed.status_code == 200
    visible = next(row for row in listed.json()["items"] if row["order_id"] == workflow_context["admin_order"])
    assert visible["customer_account_id"] == workflow_context["customer_id"] and visible["origin"] == "customer"
    assert "email" not in str(visible).lower()
    payload = {"row_version": 1}
    assert c.post(f"/orders/{workflow_context['admin_order']}/start-processing", headers=analyst, json=payload).status_code == 403
    assert c.post(f"/orders/{workflow_context['admin_order']}/start-processing", headers=customer, json=payload).status_code == 401
    assert c.post(f"/orders/{workflow_context['imported_order']}/start-processing", headers=admin, json=payload).status_code == 409
    assert c.post(f"/orders/{workflow_context['staff_order']}/start-processing", headers=admin, json=payload).status_code == 409
    assert c.post(f"/customer/orders/{workflow_context['admin_order']}/confirm-delivery", headers=customer, json=payload).status_code == 409
    assert c.post(f"/customer/orders/{workflow_context['admin_order']}/confirm-delivery", headers=other_customer, json=payload).status_code == 404
    assert c.post(f"/customer/orders/{workflow_context['admin_order']}/confirm-delivery", headers=admin, json=payload).status_code == 401

    started = c.post(f"/orders/{workflow_context['admin_order']}/start-processing", headers=admin, json=payload)
    assert started.status_code == 200 and started.json()["order_status"] == "processing" and started.json()["row_version"] == 2
    assert c.post(f"/customer/orders/{workflow_context['admin_order']}/confirm-delivery", headers=customer, json={"row_version": 2}).status_code == 409
    assert c.post(f"/orders/{workflow_context['admin_order']}/start-processing", headers=ops, json=payload).status_code == 409
    assert c.post(f"/orders/{workflow_context['admin_order']}/cancel", headers=ops, json=payload).status_code == 409
    completed = c.post(f"/orders/{workflow_context['admin_order']}/ready-shipped", headers=ops, json={"row_version": 2})
    assert completed.status_code == 200 and completed.json()["order_status"] == "ready_shipped"
    assert completed.json()["payment_status"] == "paid"
    assert c.post(f"/orders/{workflow_context['admin_order']}/ready-shipped", headers=admin, json={"row_version": 2}).status_code == 409
    assert c.post(f"/orders/{workflow_context['admin_order']}/start-processing", headers=admin, json={"row_version": 3}).status_code == 409
    assert c.post(f"/customer/orders/{workflow_context['admin_order']}/confirm-delivery", headers=other_customer, json={"row_version": 3}).status_code == 404
    assert c.post(f"/customer/orders/{workflow_context['admin_order']}/confirm-delivery", headers=customer, json={"row_version": 2}).status_code == 409
    received = c.post(f"/customer/orders/{workflow_context['admin_order']}/confirm-delivery", headers=customer, json={"row_version": 3})
    assert received.status_code == 200 and received.json()["order_status"] == "delivered"
    assert received.json()["delivered_at"] is not None
    assert received.json()["delivered_confirmed_by_customer"] is True
    assert received.json()["row_version"] == 4
    detail = c.get(f"/customer/orders/{workflow_context['admin_order']}", headers=customer)
    assert detail.status_code == 200
    assert detail.json()["order_status"] == "delivered"
    assert detail.json()["delivered_confirmed_by_customer"] is True
    assert detail.json()["delivered_at"] is not None
    assert detail.json()["row_version"] == 4
    delivered_eligibility = c.get(
        f"/customer/orders/{workflow_context['admin_order']}/refund-eligibility", headers=customer
    )
    assert delivered_eligibility.status_code == 200
    assert delivered_eligibility.json() and all(item["eligible"] for item in delivered_eligibility.json())
    assert c.post(f"/customer/orders/{workflow_context['admin_order']}/confirm-delivery", headers=customer, json={"row_version": 4}).status_code == 409

    cancelled = c.post(f"/orders/{workflow_context['cancel_order']}/cancel", headers=ops, json=payload)
    assert cancelled.status_code == 200 and cancelled.json()["order_status"] == "cancelled"
    assert cancelled.json()["payment_status"] == "refunded"
    assert c.post(f"/orders/{workflow_context['cancel_order']}/start-processing", headers=admin, json={"row_version": 2}).status_code == 409
    assert c.delete(f"/orders/{workflow_context['ops_order']}", headers=admin, params={"row_version": 1}).status_code == 403
    with psycopg2.connect(**workflow_context["settings"].database_kwargs()) as db:
        with db.cursor() as cur:
            cur.execute("""SELECT order_id,event_type,channel,delivery_status FROM public.notification_outbox
                           WHERE order_id=ANY(%s) ORDER BY order_id,event_type,channel""",
                        ([workflow_context["admin_order"], workflow_context["cancel_order"]],))
            rows = cur.fetchall()
            expected = {
                (workflow_context["admin_order"], "order_processing", "email", "sent"),
                (workflow_context["admin_order"], "order_processing", "sms", "sent"),
                (workflow_context["admin_order"], "order_ready_shipped", "email", "sent"),
                (workflow_context["admin_order"], "order_ready_shipped", "sms", "sent"),
                (workflow_context["admin_order"], "order_delivered", "email", "sent"),
                (workflow_context["admin_order"], "order_delivered", "sms", "sent"),
                (workflow_context["cancel_order"], "order_cancelled", "email", "sent"),
                (workflow_context["cancel_order"], "order_cancelled", "sms", "sent"),
            }
            assert set(rows) == expected


def test_operations_completion_cod_collection_refund_eligibility_and_races(workflow_context) -> None:
    c = workflow_context["client"]
    admin, ops = (bearer(workflow_context["staff"][key]) for key in ("admin", "ops"))
    customer = bearer(workflow_context["customer"])
    started = c.post(f"/orders/{workflow_context['ops_order']}/start-processing", headers=ops, json={"row_version": 1})
    assert started.status_code == 200
    ineligible = c.get(f"/customer/orders/{workflow_context['ops_order']}/refund-eligibility", headers=customer).json()
    assert ineligible and all(not row["eligible"] for row in ineligible)
    completed = c.post(f"/orders/{workflow_context['ops_order']}/ready-shipped", headers=admin, json={"row_version": 2})
    assert completed.status_code == 200
    eligible = c.get(f"/customer/orders/{workflow_context['ops_order']}/refund-eligibility", headers=customer).json()
    assert eligible and all(row["eligible"] for row in eligible)

    race_started = c.post(f"/orders/{workflow_context['race_order']}/start-processing", headers=admin, json={"row_version": 1})
    assert race_started.status_code == 200
    assert c.post(f"/orders/{workflow_context['race_order']}/cancel", headers=ops, json={"row_version": 1}).status_code == 409

    cod_started = c.post(f"/orders/{workflow_context['cod_order']}/start-processing", headers=ops, json={"row_version": 1})
    assert cod_started.status_code == 200 and cod_started.json()["payment_status"] == "pending"
    cod_completed = c.post(f"/orders/{workflow_context['cod_order']}/ready-shipped", headers=admin, json={"row_version": 2})
    assert cod_completed.status_code == 200 and cod_completed.json()["payment_status"] == "paid"
    cod_eligible = c.get(f"/customer/orders/{workflow_context['cod_order']}/refund-eligibility", headers=customer).json()
    assert cod_eligible and cod_eligible[0]["eligible"] is True

    customer_history = c.get("/customer/orders", headers=customer).json()
    reflected = {row["order_id"]: row["order_status"] for row in customer_history}
    assert reflected[workflow_context["admin_order"]] == "delivered"
    assert reflected[workflow_context["cancel_order"]] == "cancelled"
    assert reflected[workflow_context["race_order"]] == "processing"

    for order_id, expected in (
        (workflow_context["admin_order"], "delivered"),
        (workflow_context["ops_order"], "ready_shipped"),
        (workflow_context["cancel_order"], "cancelled"),
        (workflow_context["race_order"], "processing"),
        (workflow_context["cod_order"], "ready_shipped"),
    ):
        customer_orders = c.get("/order-workflow/orders", headers=admin).json()["items"]
        assert next(row for row in customer_orders if row["order_id"] == order_id)["order_status"] == expected


def test_imported_and_staff_orders_never_queue_customer_notifications(workflow_context) -> None:
    conn = psycopg2.connect(**workflow_context["settings"].database_kwargs())
    try:
        pending: list[int] = []
        outbox = NotificationOutbox(conn, pending)
        outbox.queue_order("order_confirmation", workflow_context["imported_order"])
        outbox.queue_order("order_confirmation", workflow_context["staff_order"])
        assert pending == []
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM public.notification_outbox WHERE order_id=ANY(%s)",
                        ([workflow_context["imported_order"], workflow_context["staff_order"]],))
            assert cur.fetchone()[0] == 0
        conn.rollback()
    finally:
        conn.close()
