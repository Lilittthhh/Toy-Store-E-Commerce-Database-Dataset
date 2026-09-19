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
from api.routers.checkout import router as checkout_router
from api.routers.customer_auth import router as customer_auth_router
from api.routers.customer_resources import router as customer_resources_router
from api.routers.storefront import router as storefront_router
from api.schemas.checkout import CheckoutRequest
from core.config import Settings, get_settings
from core.dependencies import get_checkout_service, require_customer
from core.models import CustomerAccount
from core.security import hash_password
from db.connection import close_pool, initialize_pool
from services.checkout_service import CheckoutService
from services.notifications.outbox import NotificationOutbox
from services.notifications.providers import ProviderFailure


pytestmark = pytest.mark.integration
PASSWORD = "Checkout-integration-1!"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def address(label: str) -> dict:
    return {
        "label": label, "recipient_first_name": "Original", "recipient_last_name": "Recipient",
        "phone": None, "address_line_1": "1 Snapshot Street", "address_line_2": None,
        "city": "Manila", "province_region": "Metro Manila", "postal_code": "1000",
        "country_code": "PH", "is_default": False,
    }


@pytest.fixture(scope="module")
def checkout_context():
    if os.getenv("RUN_DB_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_DB_INTEGRATION_TESTS=1 to use PostgreSQL")
    old_secret = os.environ.get("JWT_SECRET_KEY")
    os.environ["JWT_SECRET_KEY"] = secrets.token_urlsafe(48)
    get_settings.cache_clear()
    settings = replace(Settings.from_environment(), jwt_secret_key=os.environ["JWT_SECRET_KEY"])
    marker = f"rmitcheckout_{uuid.uuid4().hex[:10]}"
    tracked = (
        "app_users", "customer_accounts", "customer_profiles", "customer_addresses",
        "payment_methods", "products", "product_catalog_details", "shopping_carts",
        "cart_items", "orders", "order_items", "order_shipping_addresses", "order_payments",
    )
    setup = psycopg2.connect(**settings.database_kwargs())
    try:
        with setup:
            with setup.cursor() as cur:
                baseline = {}
                for table in tracked:
                    cur.execute(f"SELECT COUNT(*) FROM public.{table}")
                    baseline[table] = int(cur.fetchone()[0])
                staff_ids = {}
                for suffix, role in (("admin", "admin"), ("ops", "operations_staff"), ("analyst", "analyst")):
                    username = f"{marker}_{suffix}"
                    cur.execute(
                        "INSERT INTO public.app_users (username,email,password_hash,role) VALUES (%s,%s,%s,%s) RETURNING app_user_id",
                        (username, f"{username}@example.com", hash_password(PASSWORD), role),
                    )
                    staff_ids[suffix] = int(cur.fetchone()[0])
                cur.execute(
                    "INSERT INTO public.products (created_at,product_name,created_by_app_user_id,record_origin) VALUES (NOW(),%s,%s,'staff') RETURNING product_id",
                    (f"{marker} Checkout Toy", staff_ids["admin"]),
                )
                product_id = int(cur.fetchone()[0])
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
    for router in (staff_auth_router, business_router, customer_auth_router, customer_resources_router, storefront_router, checkout_router):
        app.include_router(router)
    app.dependency_overrides[get_settings] = lambda: settings

    @app.post("/test/injected-checkout-failure")
    def injected_failure(request: CheckoutRequest, customer: CustomerAccount = Depends(require_customer), service: CheckoutService = Depends(get_checkout_service)):
        service.checkout(customer, request.address_id, request.payment_method_id, request.cart_row_version)
        raise RuntimeError("Injected failure before request commit")

    state: dict = {}
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            staff_tokens = {}
            for suffix in ("admin", "ops", "analyst"):
                login = client.post("/auth/login", json={"identifier": f"{marker}_{suffix}", "password": PASSWORD})
                staff_tokens[suffix] = login.json()["access_token"]
            customers, customer_ids = [], []
            for number in (1, 2):
                email = f"{marker}_customer{number}@example.com"
                registered = client.post("/customer/auth/register", json={
                    "email": email, "password": PASSWORD, "first_name": "Checkout",
                    "last_name": f"Customer{number}", "phone": None,
                })
                customer_ids.append(registered.json()["customer_account_id"])
                login = client.post("/customer/auth/login", json={"email": email, "password": PASSWORD})
                customers.append(login.json()["access_token"])
            configured = client.put(f"/admin/catalog/{product_id}", headers=bearer(staff_tokens["admin"]), json={
                "description": "Checkout integration product.", "current_price_usd": "19.99",
                "current_cogs_usd": "8.25", "image_url": None, "is_available": True,
                "row_version": None,
            })
            assert configured.status_code == 200
            yield client, settings, marker, staff_tokens, customers, customer_ids, product_id, state
    finally:
        cleanup = psycopg2.connect(**settings.database_kwargs())
        try:
            with cleanup:
                with cleanup.cursor() as cur:
                    cur.execute("SELECT customer_account_id FROM public.customer_accounts WHERE email LIKE %s", (marker + "_%",))
                    ids = [int(row[0]) for row in cur.fetchall()]
                    if ids:
                        cur.execute("DELETE FROM public.notification_outbox WHERE customer_account_id=ANY(%s)", (ids,))
                        cur.execute("DELETE FROM public.cart_items WHERE shopping_cart_id IN (SELECT shopping_cart_id FROM public.shopping_carts WHERE customer_account_id=ANY(%s))", (ids,))
                        cur.execute("DELETE FROM public.shopping_carts WHERE customer_account_id=ANY(%s)", (ids,))
                        cur.execute("DELETE FROM public.order_payments WHERE customer_account_id=ANY(%s)", (ids,))
                        cur.execute("DELETE FROM public.order_shipping_addresses WHERE customer_account_id=ANY(%s)", (ids,))
                        cur.execute("DELETE FROM public.order_items WHERE order_id IN (SELECT order_id FROM public.orders WHERE customer_account_id=ANY(%s))", (ids,))
                        cur.execute("DELETE FROM public.orders WHERE customer_account_id=ANY(%s)", (ids,))
                        cur.execute("DELETE FROM public.payment_methods WHERE customer_account_id=ANY(%s)", (ids,))
                        cur.execute("DELETE FROM public.customer_addresses WHERE customer_account_id=ANY(%s)", (ids,))
                        cur.execute("DELETE FROM public.customer_profiles WHERE customer_account_id=ANY(%s)", (ids,))
                        cur.execute("DELETE FROM public.customer_accounts WHERE customer_account_id=ANY(%s)", (ids,))
                    cur.execute("DELETE FROM public.product_catalog_details WHERE product_id=%s", (product_id,))
                    cur.execute("DELETE FROM public.products WHERE product_id=%s", (product_id,))
                    cur.execute("DELETE FROM public.app_users WHERE username LIKE %s", (marker + "_%",))
                    for table in tracked:
                        cur.execute(f"SELECT COUNT(*) FROM public.{table}")
                        assert int(cur.fetchone()[0]) == baseline[table], table
        finally:
            cleanup.close()
            if old_secret is None:
                os.environ.pop("JWT_SECRET_KEY", None)
            else:
                os.environ["JWT_SECRET_KEY"] = old_secret
            get_settings.cache_clear()


def test_checkout_validation_atomicity_snapshots_and_duplicate_protection(checkout_context) -> None:
    client, _, _, staff, customers, _, product_id, state = checkout_context
    owner, other = bearer(customers[0]), bearer(customers[1])
    assert client.post("/customer/checkout", headers=owner, json={"address_id": 1, "payment_method_id": 1, "cart_row_version": 1}).status_code == 409
    own_address = client.post("/customer/addresses", headers=owner, json=address("Home")).json()
    foreign_address = client.post("/customer/addresses", headers=other, json=address("Other")).json()
    own_payment = client.post("/customer/payment-methods", headers=owner, json={"method_type": "card", "card_brand": "Visa", "card_last_four": "1234", "is_default": False}).json()
    foreign_payment = client.post("/customer/payment-methods", headers=other, json={"method_type": "paypal", "card_brand": None, "card_last_four": None, "is_default": False}).json()
    inactive_address = client.post("/customer/addresses", headers=owner, json=address("Inactive")).json()
    inactive_address = client.post(f"/customer/addresses/{inactive_address['customer_address_id']}/deactivate", headers=owner, json={"row_version": inactive_address["row_version"]}).json()
    inactive_payment = client.post("/customer/payment-methods", headers=owner, json={"method_type": "gcash", "card_brand": None, "card_last_four": None, "is_default": False}).json()
    inactive_payment = client.post(f"/customer/payment-methods/{inactive_payment['payment_method_id']}/deactivate", headers=owner, json={"row_version": inactive_payment["row_version"]}).json()
    client.post("/customer/cart/items", headers=owner, json={"product_id": product_id, "quantity": 2})
    cart = client.get("/customer/cart", headers=owner).json()
    base = {"address_id": own_address["customer_address_id"], "payment_method_id": own_payment["payment_method_id"], "cart_row_version": cart["row_version"]}
    for changes in (
        {"address_id": foreign_address["customer_address_id"]},
        {"payment_method_id": foreign_payment["payment_method_id"]},
        {"address_id": inactive_address["customer_address_id"]},
        {"payment_method_id": inactive_payment["payment_method_id"]},
    ):
        assert client.post("/customer/checkout", headers=owner, json={**base, **changes}).status_code == 404
    assert client.post("/customer/checkout", headers=owner, json={**base, "total": "0.01"}).status_code == 422

    catalog = client.get(f"/admin/catalog/{product_id}", headers=bearer(staff["admin"])).json()
    changed = client.put(f"/admin/catalog/{product_id}", headers=bearer(staff["admin"]), json={
        "description": catalog["description"], "current_price_usd": "20.99", "current_cogs_usd": "8.25",
        "image_url": None, "is_available": True, "row_version": catalog["row_version"],
    }).json()
    assert client.post("/customer/checkout", headers=owner, json=base).status_code == 409
    restored = client.put(f"/admin/catalog/{product_id}", headers=bearer(staff["admin"]), json={
        "description": changed["description"], "current_price_usd": "19.99", "current_cogs_usd": "8.25",
        "image_url": None, "is_available": True, "row_version": changed["row_version"],
    }).json()
    unavailable = client.put(f"/admin/catalog/{product_id}", headers=bearer(staff["admin"]), json={
        "description": restored["description"], "current_price_usd": "19.99", "current_cogs_usd": "8.25",
        "image_url": None, "is_available": False, "row_version": restored["row_version"],
    }).json()
    assert client.post("/customer/checkout", headers=owner, json=base).status_code == 409
    client.put(f"/admin/catalog/{product_id}", headers=bearer(staff["admin"]), json={
        "description": unavailable["description"], "current_price_usd": "19.99", "current_cogs_usd": "8.25",
        "image_url": None, "is_available": True, "row_version": unavailable["row_version"],
    })

    injected = client.post("/test/injected-checkout-failure", headers=owner, json=base)
    assert injected.status_code == 500
    assert client.get("/customer/orders", headers=owner).json() == []
    assert client.get("/customer/cart", headers=owner).json()["shopping_cart_id"] == cart["shopping_cart_id"]

    placed = client.post("/customer/checkout", headers=owner, json=base)
    assert placed.status_code == 201
    order = placed.json()
    assert order["order_status"] == "pending" and order["total_usd"] == "39.98"
    assert order["payment"]["payment_status"] == "paid"
    assert order["shipping"]["recipient_first_name"] == "Original"
    assert order["items"][0]["quantity"] == 2 and order["items"][0]["unit_price_usd"] == "19.99"
    serialized = str(order)
    assert all(field not in serialized for field in ("cogs_usd", "record_origin", "created_by_app_user_id"))
    assert client.post("/customer/checkout", headers=owner, json=base).status_code == 409
    assert client.get("/customer/cart", headers=owner).json()["shopping_cart_id"] is None
    next_add = client.post("/customer/cart/items", headers=owner, json={"product_id": product_id, "quantity": 1})
    assert next_add.status_code == 201
    assert client.get("/customer/cart", headers=owner).json()["shopping_cart_id"] != cart["shopping_cart_id"]
    state.update({"order": order, "address": own_address, "payment": own_payment})

    # No profile phone was supplied: checkout commits one mock email, not SMS.
    with psycopg2.connect(**checkout_context[1].database_kwargs()) as db:
        with db.cursor() as cur:
            cur.execute("""SELECT event_type,channel,delivery_status,recipient_address
                           FROM public.notification_outbox WHERE order_id=%s""", (order["order_id"],))
            assert cur.fetchall() == [("order_confirmation", "email", "sent",
                                       f"{checkout_context[2]}_customer1@example.com")]


def test_order_history_snapshot_immutability_staff_visibility_and_cancellation(checkout_context) -> None:
    client, settings, _, staff, customers, customer_ids, _, state = checkout_context
    owner, other = bearer(customers[0]), bearer(customers[1])
    order = state["order"]
    order_id = order["order_id"]
    own_list = client.get("/customer/orders", headers=owner).json()
    assert [item["order_id"] for item in own_list] == [order_id]
    assert client.get("/customer/orders", headers=other).json() == []
    assert client.get(f"/customer/orders/{order_id}", headers=other).status_code == 404

    address_value = state["address"]
    update_address = address("Changed")
    update_address.update({"recipient_first_name": "Changed", "address_line_1": "99 New Street", "row_version": address_value["row_version"]})
    update_address.pop("is_default")
    assert client.put(f"/customer/addresses/{address_value['customer_address_id']}", headers=owner, json=update_address).status_code == 200
    payment_value = state["payment"]
    assert client.put(f"/customer/payment-methods/{payment_value['payment_method_id']}", headers=owner, json={"method_type": "paypal", "card_brand": None, "card_last_four": None, "row_version": payment_value["row_version"]}).status_code == 200
    unchanged = client.get(f"/customer/orders/{order_id}", headers=owner).json()
    assert unchanged["shipping"]["recipient_first_name"] == "Original"
    assert unchanged["shipping"]["address_line_1"] == "1 Snapshot Street"
    assert unchanged["payment"]["display_label"] == "Visa ending in 1234 — simulated"

    for role in ("admin", "ops", "analyst"):
        response = client.get("/orders", headers=bearer(staff[role]), params={"origin": "customer", "limit": 100})
        assert response.status_code == 200
        visible = next(item for item in response.json()["items"] if item["order_id"] == order_id)
        assert visible["origin"] == "customer" and visible["website_session_id"] is None and visible["user_id"] is None

    assert client.post(f"/customer/orders/{order_id}/cancel", headers=other, json={"row_version": order["row_version"]}).status_code == 404
    assert client.post(f"/customer/orders/{order_id}/cancel", headers=owner, json={"row_version": 999999}).status_code == 409
    cancelled = client.post(f"/customer/orders/{order_id}/cancel", headers=owner, json={"row_version": order["row_version"]})
    assert cancelled.status_code == 200
    assert cancelled.json()["order_status"] == "cancelled"
    assert cancelled.json()["payment"]["payment_status"] == "refunded"
    assert client.post(f"/customer/orders/{order_id}/cancel", headers=owner, json={"row_version": cancelled.json()["row_version"]}).status_code == 409
    assert any(item["order_status"] == "cancelled" for item in client.get("/customer/orders", headers=owner).json())

    # A later profile change must not rewrite the already-queued email destination.
    with psycopg2.connect(**settings.database_kwargs()) as db:
        with db.cursor() as cur:
            cur.execute("UPDATE public.customer_profiles SET phone=%s WHERE customer_account_id=%s",
                        ("09171234567", customer_ids[0]))
            cur.execute("""SELECT recipient_address FROM public.notification_outbox
                           WHERE order_id=%s AND event_type='order_confirmation' AND channel='email'""", (order_id,))
            assert cur.fetchone()[0] == f"{checkout_context[2]}_customer1@example.com"

    cod = client.post("/customer/payment-methods", headers=owner, json={
        "method_type": "cash_on_delivery", "card_brand": None,
        "card_last_four": None, "is_default": False,
    }).json()
    active_cart = client.get("/customer/cart", headers=owner).json()
    cod_order = client.post("/customer/checkout", headers=owner, json={
        "address_id": address_value["customer_address_id"],
        "payment_method_id": cod["payment_method_id"],
        "cart_row_version": active_cart["row_version"],
    }).json()
    cod_cancelled = client.post(f"/customer/orders/{cod_order['order_id']}/cancel", headers=owner, json={"row_version": cod_order["row_version"]})
    assert cod_cancelled.status_code == 200
    assert cod_cancelled.json()["payment"]["payment_status"] == "pending"
    with psycopg2.connect(**settings.database_kwargs()) as db:
        with db.cursor() as cur:
            cur.execute("""SELECT event_type,channel,delivery_status,recipient_address
                           FROM public.notification_outbox WHERE order_id=%s
                           ORDER BY event_type,channel""", (cod_order["order_id"],))
            rows = cur.fetchall()
            assert [(event, channel, status) for event, channel, status, _ in rows] == [
                ("order_cancelled", "email", "sent"), ("order_cancelled", "sms", "sent"),
                ("order_confirmation", "email", "sent"), ("order_confirmation", "sms", "sent")]
            assert all(recipient == "+639171234567" for _, channel, _, recipient in rows if channel == "sms")

    client.post("/customer/cart/items", headers=owner, json={"product_id": state["order"]["items"][0]["product_id"], "quantity": 1})
    processing_cart = client.get("/customer/cart", headers=owner).json()
    processing_order = client.post("/customer/checkout", headers=owner, json={
        "address_id": address_value["customer_address_id"],
        "payment_method_id": payment_value["payment_method_id"],
        "cart_row_version": processing_cart["row_version"],
    }).json()
    transition = psycopg2.connect(**settings.database_kwargs())
    try:
        with transition:
            with transition.cursor() as cur:
                cur.execute("UPDATE public.orders SET order_status='processing',row_version=row_version+1 WHERE order_id=%s", (processing_order["order_id"],))
    finally:
        transition.close()
    refreshed_processing = client.get(f"/customer/orders/{processing_order['order_id']}", headers=owner).json()
    assert client.post(f"/customer/orders/{processing_order['order_id']}/cancel", headers=owner, json={"row_version": refreshed_processing["row_version"]}).status_code == 409

    db = psycopg2.connect(**settings.database_kwargs())
    try:
        with db.cursor() as cur:
            cur.execute("SELECT record_origin,customer_account_id,website_session_id,user_id,order_status,price_usd,cogs_usd,items_purchased FROM public.orders WHERE order_id=%s", (order_id,))
            saved = cur.fetchone()
            assert saved[:5] == ("customer", customer_ids[0], None, None, "cancelled")
            assert saved[5:] == (Decimal("39.98"), Decimal("16.50"), 2)
            cur.execute("SELECT COUNT(*),MIN(record_origin),MAX(record_origin),COUNT(created_by_app_user_id) FROM public.order_items WHERE order_id=%s", (order_id,))
            assert cur.fetchone() == (2, "customer", "customer", 0)
    finally:
        db.close()


def test_notification_outbox_constraints_and_duplicate_enqueue(checkout_context) -> None:
    _, settings, _, _, _, customer_ids, _, state = checkout_context
    order_id = state["order"]["order_id"]
    conn = psycopg2.connect(**settings.database_kwargs())
    try:
        queued: list[int] = []
        NotificationOutbox(conn, queued).queue_order("order_confirmation", order_id)
        assert len(queued) == 1  # A newly added phone permits one new SMS channel.
        NotificationOutbox(conn, queued).queue_order("order_confirmation", order_id)
        assert len(queued) == 1  # Repeating cannot duplicate either channel.
        conn.rollback()
        with conn.cursor() as cur:
            for event in ("order_processing", "order_completed", "order_ready_shipped", "order_delivered", "order_cancelled"):
                cur.execute("SAVEPOINT allowed_notification_rule_check")
                cur.execute("""INSERT INTO public.notification_outbox
                               (customer_account_id,order_id,refund_request_id,event_type,channel,recipient_address)
                               VALUES (%s,%s,NULL,%s,'email',%s) ON CONFLICT DO NOTHING""",
                            (customer_ids[0], order_id, event, "test@example.com"))
                cur.execute("ROLLBACK TO SAVEPOINT allowed_notification_rule_check")
            attempts = (
                ("invalid_event", "email", order_id, None, "test@example.com", "23514"),
                ("order_processing", "fax", order_id, None, "test@example.com", "23514"),
                ("refund_request_submitted", "email", order_id, None, "test@example.com", "23514"),
                ("order_processing", "sms", None, None, "+639171234567", "23514"),
                ("order_confirmation", "email", order_id, None, "test@example.com", "23505"),
            )
            for event, channel, target_order, refund_id, recipient, sqlstate in attempts:
                cur.execute("SAVEPOINT notification_rule_check")
                try:
                    cur.execute("""INSERT INTO public.notification_outbox
                                   (customer_account_id,order_id,refund_request_id,event_type,channel,recipient_address)
                                   VALUES (%s,%s,%s,%s,%s,%s)""",
                                (customer_ids[0], target_order, refund_id, event, channel, recipient))
                    raise AssertionError(f"Unexpectedly accepted invalid notification: {event}/{channel}")
                except psycopg2.Error as exc:
                    assert exc.pgcode == sqlstate
                finally:
                    cur.execute("ROLLBACK TO SAVEPOINT notification_rule_check")
            cur.execute("SAVEPOINT notification_status_check")
            try:
                cur.execute("""UPDATE public.notification_outbox SET delivery_status='unknown'
                               WHERE order_id=%s AND event_type='order_confirmation'""", (order_id,))
                raise AssertionError("Invalid delivery status was accepted")
            except psycopg2.Error as exc:
                assert exc.pgcode == "23514"
            finally:
                cur.execute("ROLLBACK TO SAVEPOINT notification_status_check")
        conn.rollback()
    finally:
        conn.close()


def test_provider_failure_does_not_rollback_checkout(checkout_context, monkeypatch) -> None:
    import services.notifications.outbox as outbox_module

    class FailingProvider:
        def send_email(self, message):
            raise ProviderFailure("PROVIDER_REQUEST_FAILED")

        def send_sms(self, message):
            raise ProviderFailure("PROVIDER_REQUEST_FAILED")

    monkeypatch.setattr(outbox_module, "provider_for", lambda settings: FailingProvider())
    client, settings, _, _, customers, _, product_id, state = checkout_context
    owner = bearer(customers[0])
    assert client.post("/customer/cart/items", headers=owner,
                       json={"product_id": product_id, "quantity": 1}).status_code == 201
    cart = client.get("/customer/cart", headers=owner).json()
    response = client.post("/customer/checkout", headers=owner, json={
        "address_id": state["address"]["customer_address_id"],
        "payment_method_id": state["payment"]["payment_method_id"],
        "cart_row_version": cart["row_version"],
    })
    assert response.status_code == 201
    order_id = response.json()["order_id"]
    assert any(order["order_id"] == order_id for order in client.get("/customer/orders", headers=owner).json())
    with psycopg2.connect(**settings.database_kwargs()) as db:
        with db.cursor() as cur:
            cur.execute("""SELECT channel,delivery_status,error_code FROM public.notification_outbox
                           WHERE order_id=%s ORDER BY channel""", (order_id,))
            assert cur.fetchall() == [
                ("email", "failed", "PROVIDER_REQUEST_FAILED"),
                ("sms", "failed", "PROVIDER_REQUEST_FAILED")]
