from __future__ import annotations

import os
import secrets
import uuid
from contextlib import asynccontextmanager
from dataclasses import replace
from decimal import Decimal

import psycopg2
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from api.routers.auth import router as staff_auth_router
from api.routers.business import router as business_router
from api.routers.customer_auth import router as customer_auth_router
from api.routers.refund_workflow import router as refund_router
from api.schemas.refund_workflow import RefundProcessRequest
from core.config import Settings, get_settings
from core.dependencies import get_refund_workflow_service, require_roles
from core.models import AppUser, Role
from core.security import hash_password
from db.connection import close_pool, initialize_pool
from services.refund_workflow_service import RefundWorkflowService


pytestmark = pytest.mark.integration
PASSWORD = "Refund-integration-1!"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def refund_context():
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
    marker = f"rmitrefund_{uuid.uuid4().hex[:10]}"
    tracked = (
        "app_users", "customer_accounts", "customer_profiles", "orders", "order_items",
        "order_payments", "refund_requests", "order_item_refunds",
    )
    conn = psycopg2.connect(**settings.database_kwargs())
    state: dict = {"marker": marker}
    try:
        with conn:
            with conn.cursor() as cur:
                baseline = {}
                for table in tracked:
                    cur.execute(f"SELECT COUNT(*) FROM public.{table}")
                    baseline[table] = int(cur.fetchone()[0])
                cur.execute("SELECT product_id FROM public.canonical_products ORDER BY product_id LIMIT 1")
                product_id = int(cur.fetchone()[0])
                cur.execute("SELECT order_item_id FROM public.canonical_order_items ORDER BY order_item_id LIMIT 1")
                canonical_item = int(cur.fetchone()[0])
                staff_ids = {}
                for label, role in (("admin", "admin"), ("ops", "operations_staff"), ("analyst", "analyst")):
                    username = f"{marker}_{label}"
                    cur.execute(
                        "INSERT INTO public.app_users(username,email,password_hash,role) VALUES(%s,%s,%s,%s) RETURNING app_user_id",
                        (username, f"{username}@example.com", hash_password(PASSWORD), role),
                    )
                    staff_ids[label] = int(cur.fetchone()[0])
                customer_ids = []
                for number in (1, 2):
                    email = f"{marker}_customer{number}@example.com"
                    cur.execute(
                        "INSERT INTO public.customer_accounts(email,password_hash) VALUES(%s,%s) RETURNING customer_account_id",
                        (email, hash_password(PASSWORD)),
                    )
                    customer_id = int(cur.fetchone()[0])
                    customer_ids.append(customer_id)
                    cur.execute(
                        "INSERT INTO public.customer_profiles(customer_account_id,first_name,last_name,phone) VALUES(%s,'Refund','Tester','09171234567')",
                        (customer_id,),
                    )

                def make_order(customer_id: int, status: str, payment_status: str, prices: tuple[str, ...]):
                    total = sum((Decimal(value) for value in prices), Decimal("0.00"))
                    cur.execute(
                        """INSERT INTO public.orders
                           (created_at,website_session_id,user_id,primary_product_id,items_purchased,
                            price_usd,cogs_usd,record_origin,customer_account_id,order_status)
                           VALUES(NOW(),NULL,NULL,%s,%s,%s,0,'customer',%s,%s) RETURNING order_id""",
                        (product_id, len(prices), total, customer_id, status),
                    )
                    order_id = int(cur.fetchone()[0])
                    item_ids = []
                    for index, price in enumerate(prices):
                        cur.execute(
                            """INSERT INTO public.order_items
                               (created_at,order_id,product_id,is_primary_item,price_usd,cogs_usd,record_origin)
                               VALUES(NOW(),%s,%s,%s,%s,0,'customer') RETURNING order_item_id""",
                            (order_id, product_id, 1 if index == 0 else 0, Decimal(price)),
                        )
                        item_ids.append(int(cur.fetchone()[0]))
                    method = "cash_on_delivery" if payment_status == "pending" else "card"
                    cur.execute(
                        """INSERT INTO public.order_payments
                           (order_id,customer_account_id,method_type,payment_display_snapshot,payment_status,amount_usd)
                           VALUES(%s,%s,%s,%s,%s,%s)""",
                        (order_id, customer_id, method, "Classroom simulation", payment_status, total),
                    )
                    return order_id, item_ids

                completed_order, completed_items = make_order(customer_ids[0], "ready_shipped", "paid", ("20.00", "20.00"))
                second_order, second_items = make_order(customer_ids[0], "ready_shipped", "paid", ("12.00",))
                pending_order, pending_items = make_order(customer_ids[0], "pending", "paid", ("8.00",))
                foreign_order, foreign_items = make_order(customer_ids[1], "ready_shipped", "paid", ("9.00",))
                cod_order, cod_items = make_order(customer_ids[0], "ready_shipped", "pending", ("11.00",))
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
                       VALUES(NOW(),%s,%s,%s,1,7,0,%s,'staff','ready_shipped') RETURNING order_id""",
                    (session_id, dataset_user_id, product_id, staff_ids["admin"]),
                )
                staff_order = int(cur.fetchone()[0])
                cur.execute(
                    """INSERT INTO public.order_items
                       (created_at,order_id,product_id,is_primary_item,price_usd,cogs_usd,
                        created_by_app_user_id,record_origin)
                       VALUES(NOW(),%s,%s,1,7,0,%s,'staff') RETURNING order_item_id""",
                    (staff_order, product_id, staff_ids["admin"]),
                )
                staff_item = int(cur.fetchone()[0])
                state.update(locals())
    finally:
        conn.close()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        initialize_pool(settings)
        try:
            yield
        finally:
            close_pool()

    app = FastAPI(lifespan=lifespan)
    for router in (staff_auth_router, business_router, customer_auth_router, refund_router):
        app.include_router(router)
    app.dependency_overrides[get_settings] = lambda: settings

    @app.post("/test/injected-refund-processing-failure")
    def injected_failure(request_id: int, request: RefundProcessRequest, user: AppUser = Depends(require_roles(Role.ADMIN)), service: RefundWorkflowService = Depends(get_refund_workflow_service)):
        service.process(request_id, request.row_version, user)
        raise RuntimeError("Injected failure before request commit")

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            staff_tokens = {
                label: client.post("/auth/login", json={"identifier": f"{marker}_{label}", "password": PASSWORD}).json()["access_token"]
                for label in ("admin", "ops", "analyst")
            }
            customer_tokens = [
                client.post("/customer/auth/login", json={"email": f"{marker}_customer{number}@example.com", "password": PASSWORD}).json()["access_token"]
                for number in (1, 2)
            ]
            state.update({"client": client, "staff": staff_tokens, "customers": customer_tokens, "settings": settings})
            yield state
    finally:
        cleanup = psycopg2.connect(**settings.database_kwargs())
        try:
            with cleanup:
                with cleanup.cursor() as cur:
                    order_ids = [state[key] for key in ("completed_order", "second_order", "pending_order", "foreign_order", "cod_order", "staff_order")]
                    cur.execute("DELETE FROM public.notification_outbox WHERE customer_account_id=ANY(%s)", (state["customer_ids"],))
                    cur.execute("DELETE FROM public.order_item_refunds WHERE order_id=ANY(%s)", (order_ids,))
                    cur.execute("DELETE FROM public.refund_requests WHERE customer_account_id=ANY(%s)", (state["customer_ids"],))
                    cur.execute("DELETE FROM public.order_payments WHERE customer_account_id=ANY(%s)", (state["customer_ids"],))
                    cur.execute("DELETE FROM public.order_items WHERE order_id=ANY(%s)", (order_ids,))
                    cur.execute("DELETE FROM public.orders WHERE customer_account_id=ANY(%s)", (state["customer_ids"],))
                    cur.execute("DELETE FROM public.orders WHERE order_id=%s", (state["staff_order"],))
                    cur.execute("DELETE FROM public.customer_profiles WHERE customer_account_id=ANY(%s)", (state["customer_ids"],))
                    cur.execute("DELETE FROM public.customer_accounts WHERE customer_account_id=ANY(%s)", (state["customer_ids"],))
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


def test_customer_request_eligibility_privacy_and_safe_projection(refund_context) -> None:
    c = refund_context["client"]
    owner, other = map(bearer, refund_context["customers"])
    completed_item = refund_context["completed_items"][0]
    assert c.post("/customer/refund-requests", headers=owner, json={"order_item_id": refund_context["pending_items"][0], "requested_amount": "1.00", "reason": "Not eligible"}).status_code == 409
    assert c.post("/customer/refund-requests", headers=owner, json={"order_item_id": refund_context["cod_items"][0], "requested_amount": "1.00", "reason": "Unpaid COD"}).status_code == 409
    assert c.post("/customer/refund-requests", headers=owner, json={"order_item_id": refund_context["foreign_items"][0], "requested_amount": "1.00", "reason": "Foreign"}).status_code == 404
    assert c.post("/customer/refund-requests", headers=other, json={"order_item_id": completed_item, "requested_amount": "1.00", "reason": "Foreign"}).status_code == 404
    assert c.post("/customer/refund-requests", headers=owner, json={"order_item_id": refund_context["staff_item"], "requested_amount": "1.00", "reason": "Staff origin"}).status_code == 404
    assert c.post("/customer/refund-requests", headers=owner, json={"order_item_id": refund_context["canonical_item"], "requested_amount": "1.00", "reason": "Imported origin"}).status_code == 404
    assert c.post("/customer/refund-requests", headers=owner, json={"order_item_id": completed_item, "requested_amount": "20.01", "reason": "Too high"}).status_code == 409
    assert c.post("/customer/refund-requests", headers=owner, json={"order_item_id": completed_item, "requested_amount": "0.00", "reason": "Zero"}).status_code == 422
    created = c.post("/customer/refund-requests", headers=owner, json={"order_item_id": completed_item, "requested_amount": "5.00", "reason": "Damaged packaging"})
    assert created.status_code == 201
    request = created.json()
    refund_context["first_request"] = request
    assert request["status"] == "pending" and request["requested_amount"] == "5.00"
    with psycopg2.connect(**refund_context["settings"].database_kwargs()) as db:
        with db.cursor() as cur:
            cur.execute("""SELECT event_type,channel,delivery_status,recipient_address
                           FROM public.notification_outbox WHERE refund_request_id=%s""",
                        (request["refund_request_id"],))
            assert cur.fetchall() == [("refund_request_submitted", "sms", "sent", "+639171234567")]
    assert "cogs" not in str(request).lower() and "reviewed_by_app_user_id" not in request
    assert c.post("/customer/refund-requests", headers=owner, json={"order_item_id": completed_item, "requested_amount": "1.00", "reason": "Duplicate"}).status_code == 409
    own = c.get("/customer/refund-requests", headers=owner).json()
    assert [value["refund_request_id"] for value in own] == [request["refund_request_id"]]
    assert c.get(f"/customer/refund-requests/{request['refund_request_id']}", headers=other).status_code == 404
    eligibility = c.get(f"/customer/orders/{refund_context['completed_order']}/refund-eligibility", headers=owner).json()
    selected = next(value for value in eligibility if value["order_item_id"] == completed_item)
    assert selected["eligible"] is False and selected["current_request_status"] == "pending"


def test_staff_review_processing_concurrency_statuses_and_atomicity(refund_context) -> None:
    c = refund_context["client"]
    owner = bearer(refund_context["customers"][0])
    admin, ops, analyst = (bearer(refund_context["staff"][key]) for key in ("admin", "ops", "analyst"))
    request = refund_context["first_request"]
    request_id = request["refund_request_id"]
    staff_row = c.get(f"/refund-requests/{request_id}", headers=admin).json()
    assert c.post(f"/refund-requests/{request_id}/approve", headers=analyst, json={"row_version": staff_row["row_version"]}).status_code == 403
    approved = c.post(f"/refund-requests/{request_id}/approve", headers=ops, json={"row_version": staff_row["row_version"], "resolution_note": "Approved after review"})
    assert approved.status_code == 200 and approved.json()["status"] == "approved"
    assert c.post(f"/refund-requests/{request_id}/reject", headers=admin, json={"row_version": staff_row["row_version"], "resolution_note": "Racing review"}).status_code == 409
    approved_row = approved.json()
    injected = c.post("/test/injected-refund-processing-failure", headers=admin, params={"request_id": request_id}, json={"row_version": approved_row["row_version"]})
    assert injected.status_code == 500
    assert c.get(f"/refund-requests/{request_id}", headers=admin).json()["status"] == "approved"
    processed = c.post(f"/refund-requests/{request_id}/process", headers=admin, json={"row_version": approved_row["row_version"]})
    assert processed.status_code == 200 and processed.json()["status"] == "processed"
    assert c.post(f"/refund-requests/{request_id}/process", headers=ops, json={"row_version": processed.json()["row_version"]}).status_code == 409

    reject_created = c.post("/customer/refund-requests", headers=owner, json={"order_item_id": refund_context["second_items"][0], "requested_amount": "2.00", "reason": "Changed mind"}).json()
    rejected = c.post(f"/refund-requests/{reject_created['refund_request_id']}/reject", headers=admin, json={"row_version": 1, "resolution_note": "Not covered"})
    assert rejected.status_code == 200 and rejected.json()["status"] == "rejected"
    with psycopg2.connect(**refund_context["settings"].database_kwargs()) as db:
        with db.cursor() as cur:
            cur.execute("""SELECT event_type,channel,delivery_status FROM public.notification_outbox
                           WHERE refund_request_id=%s ORDER BY event_type,channel""",
                        (reject_created["refund_request_id"],))
            assert cur.fetchall() == [
                ("refund_rejected", "email", "sent"), ("refund_rejected", "sms", "sent"),
                ("refund_request_submitted", "sms", "sent")]
    assert c.post(f"/refund-requests/{reject_created['refund_request_id']}/process", headers=ops, json={"row_version": rejected.json()["row_version"]}).status_code == 409
    ops_reject_created = c.post("/customer/refund-requests", headers=owner, json={"order_item_id": refund_context["second_items"][0], "requested_amount": "1.00", "reason": "Second review"}).json()
    assert c.post(f"/refund-requests/{ops_reject_created['refund_request_id']}/reject", headers=ops, json={"row_version": 999, "resolution_note": "Stale"}).status_code == 409
    ops_rejected = c.post(f"/refund-requests/{ops_reject_created['refund_request_id']}/reject", headers=ops, json={"row_version": 1, "resolution_note": "Operations review rejection"})
    assert ops_rejected.status_code == 200 and ops_rejected.json()["status"] == "rejected"

    def request_approve_process(item_id: int, amount: str):
        made = c.post("/customer/refund-requests", headers=owner, json={"order_item_id": item_id, "requested_amount": amount, "reason": "Approved cumulative refund"}).json()
        accepted = c.post(f"/refund-requests/{made['refund_request_id']}/approve", headers=admin, json={"row_version": 1}).json()
        return c.post(f"/refund-requests/{made['refund_request_id']}/process", headers=ops, json={"row_version": accepted["row_version"]})

    assert request_approve_process(refund_context["completed_items"][1], "20.00").status_code == 200
    assert c.post("/customer/refund-requests", headers=owner, json={"order_item_id": refund_context["completed_items"][0], "requested_amount": "15.01", "reason": "Exceeds remaining"}).status_code == 409
    db = psycopg2.connect(**refund_context["settings"].database_kwargs())
    try:
        with db.cursor() as cur:
            cur.execute("SELECT payment_status FROM public.order_payments WHERE order_id=%s", (refund_context["completed_order"],))
            assert cur.fetchone()[0] == "partially_refunded"
            cur.execute("SELECT order_status FROM public.orders WHERE order_id=%s", (refund_context["completed_order"],))
            assert cur.fetchone()[0] == "ready_shipped"
            cur.execute("SELECT record_origin,refund_request_id,created_by_app_user_id,order_id,order_item_id,refund_amount_usd FROM public.order_item_refunds WHERE refund_request_id=%s", (request_id,))
            actual = cur.fetchone()
            assert actual[0] == "customer" and actual[1] == request_id and actual[2] == refund_context["staff_ids"]["admin"]
            assert actual[3:] == (refund_context["completed_order"], refund_context["completed_items"][0], Decimal("5.00"))
            cur.execute("SELECT order_item_refund_id,row_version FROM public.order_item_refunds WHERE refund_request_id=%s", (request_id,))
            actual_refund_id, actual_refund_version = cur.fetchone()
    finally:
        db.close()
    assert c.delete(f"/refunds/{actual_refund_id}", headers=admin, params={"row_version": actual_refund_version}).status_code == 403
    assert request_approve_process(refund_context["completed_items"][0], "15.00").status_code == 200
    db = psycopg2.connect(**refund_context["settings"].database_kwargs())
    try:
        with db.cursor() as cur:
            cur.execute("SELECT payment_status FROM public.order_payments WHERE order_id=%s", (refund_context["completed_order"],))
            assert cur.fetchone()[0] == "refunded"
            cur.execute("SELECT order_status FROM public.orders WHERE order_id=%s", (refund_context["completed_order"],))
            assert cur.fetchone()[0] == "refunded"
            cur.execute("SELECT COUNT(*) FROM public.canonical_order_item_refunds")
            assert cur.fetchone()[0] == 1731
            cur.execute("""SELECT event_type,channel,delivery_status FROM public.notification_outbox
                           WHERE refund_request_id=%s ORDER BY event_type,channel""", (request_id,))
            assert cur.fetchall() == [
                ("refund_processed", "email", "sent"), ("refund_processed", "sms", "sent"),
                ("refund_request_submitted", "sms", "sent")]
            cur.execute("""SELECT COUNT(*) FROM public.notification_outbox
                           WHERE order_id=%s OR refund_request_id IN
                           (SELECT refund_request_id FROM public.refund_requests WHERE order_id=%s)""",
                        (refund_context["staff_order"], refund_context["staff_order"]))
            assert cur.fetchone()[0] == 0
    finally:
        db.close()
