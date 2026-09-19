from __future__ import annotations

import os
import secrets
import uuid
from contextlib import asynccontextmanager
from dataclasses import replace

import psycopg2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.auth import router as staff_auth_router
from api.routers.customer_auth import router as customer_auth_router
from api.routers.storefront import router as storefront_router
from core.config import Settings, get_settings
from core.security import hash_password
from db.connection import close_pool, initialize_pool


pytestmark = pytest.mark.integration
PASSWORD = "Storefront-integration-1!"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def catalog_payload(price="19.99", cogs="8.00", available=True, version=None) -> dict:
    return {
        "description": "A temporary integration-test storefront product.",
        "current_price_usd": price, "current_cogs_usd": cogs,
        "image_url": None, "is_available": available, "row_version": version,
    }


@pytest.fixture(scope="module")
def store_context():
    if os.getenv("RUN_DB_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_DB_INTEGRATION_TESTS=1 to use PostgreSQL")
    old_secret = os.environ.get("JWT_SECRET_KEY")
    os.environ["JWT_SECRET_KEY"] = secrets.token_urlsafe(48)
    get_settings.cache_clear()
    settings = replace(Settings.from_environment(), jwt_secret_key=os.environ["JWT_SECRET_KEY"])
    marker = f"rmitstore_{uuid.uuid4().hex[:12]}"
    tracked = ("app_users", "customer_accounts", "customer_profiles", "products", "product_catalog_details", "shopping_carts", "cart_items")
    setup = psycopg2.connect(**settings.database_kwargs())
    try:
        with setup:
            with setup.cursor() as cur:
                cur.execute("SELECT current_database()")
                assert cur.fetchone()[0] == os.getenv("DB_INTEGRATION_EXPECTED_DATABASE", "retailmetrics")
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
                    (f"{marker} Presentation Toy", staff_ids["admin"]),
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
    app.include_router(staff_auth_router)
    app.include_router(customer_auth_router)
    app.include_router(storefront_router)
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            staff_tokens = {}
            for suffix in ("admin", "ops", "analyst"):
                response = client.post("/auth/login", json={"identifier": f"{marker}_{suffix}", "password": PASSWORD})
                staff_tokens[suffix] = response.json()["access_token"]
            customer_tokens, customer_ids = [], []
            for number in (1, 2):
                email = f"{marker}_customer{number}@example.com"
                registered = client.post("/customer/auth/register", json={
                    "email": email, "password": PASSWORD, "first_name": "Store",
                    "last_name": f"Customer{number}", "phone": None,
                })
                customer_ids.append(registered.json()["customer_account_id"])
                login = client.post("/customer/auth/login", json={"email": email, "password": PASSWORD})
                customer_tokens.append(login.json()["access_token"])
            yield client, settings, marker, staff_tokens, customer_tokens, customer_ids, product_id
    finally:
        cleanup = psycopg2.connect(**settings.database_kwargs())
        try:
            with cleanup:
                with cleanup.cursor() as cur:
                    cur.execute("SELECT customer_account_id FROM public.customer_accounts WHERE email LIKE %s", (marker + "_%",))
                    customer_ids = [int(row[0]) for row in cur.fetchall()]
                    if customer_ids:
                        cur.execute("DELETE FROM public.cart_items WHERE shopping_cart_id IN (SELECT shopping_cart_id FROM public.shopping_carts WHERE customer_account_id=ANY(%s))", (customer_ids,))
                        cur.execute("DELETE FROM public.shopping_carts WHERE customer_account_id=ANY(%s)", (customer_ids,))
                        cur.execute("DELETE FROM public.customer_profiles WHERE customer_account_id=ANY(%s)", (customer_ids,))
                        cur.execute("DELETE FROM public.customer_accounts WHERE customer_account_id=ANY(%s)", (customer_ids,))
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


def test_admin_catalog_configuration_rbac_validation_and_customer_projection(store_context) -> None:
    client, _, _, staff, customers, _, product_id = store_context
    catalog = client.get("/admin/catalog", headers=bearer(staff["analyst"]))
    assert catalog.status_code == 200
    target = next(item for item in catalog.json() if item["product_id"] == product_id)
    assert not target["is_configured"]
    before_configuration = client.get("/customer/store/products", headers=bearer(customers[0])).json()
    assert all(item["product_id"] != product_id for item in before_configuration)
    assert client.get(f"/customer/store/products/{product_id}", headers=bearer(customers[0])).status_code == 404
    for role in ("ops", "analyst"):
        assert client.put(f"/admin/catalog/{product_id}", headers=bearer(staff[role]), json=catalog_payload()).status_code == 403
    for payload in (
        catalog_payload(price="0"), catalog_payload(cogs="-0.01"),
        catalog_payload(price="10", cogs="10.01"),
    ):
        assert client.put(f"/admin/catalog/{product_id}", headers=bearer(staff["admin"]), json=payload).status_code == 422
    created = client.put(f"/admin/catalog/{product_id}", headers=bearer(staff["admin"]), json=catalog_payload())
    assert created.status_code == 200 and created.json()["row_version"] == 1
    changed = client.put(f"/admin/catalog/{product_id}", headers=bearer(staff["admin"]), json=catalog_payload(version=1))
    assert changed.status_code == 200 and changed.json()["row_version"] == 2
    assert client.put(f"/admin/catalog/{product_id}", headers=bearer(staff["admin"]), json=catalog_payload(version=1)).status_code == 409
    visible = client.get("/customer/store/products", headers=bearer(customers[0]))
    assert visible.status_code == 200
    product = next(item for item in visible.json() if item["product_id"] == product_id)
    assert "current_cogs_usd" not in product and "row_version" not in product
    assert client.get("/customer/store/products", headers=bearer(customers[0]), params={"search": "no-match-value"}).json() == []


def test_cart_lifecycle_authoritative_price_ownership_and_concurrency(store_context) -> None:
    client, settings, _, staff, customers, customer_ids, product_id = store_context
    injected = client.post("/customer/cart/items", headers=bearer(customers[0]), json={"product_id": product_id, "quantity": 1, "unit_price_usd": "0.01"})
    assert injected.status_code == 422
    first = client.post("/customer/cart/items", headers=bearer(customers[0]), json={"product_id": product_id, "quantity": 2})
    assert first.status_code == 201
    assert first.json()["stored_unit_price_usd"] == "19.99" and first.json()["quantity"] == 2
    second = client.post("/customer/cart/items", headers=bearer(customers[0]), json={"product_id": product_id, "quantity": 3})
    assert second.status_code == 201 and second.json()["quantity"] == 5
    item_id, version = second.json()["cart_item_id"], second.json()["row_version"]
    db = psycopg2.connect(**settings.database_kwargs())
    try:
        with db.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM public.shopping_carts WHERE customer_account_id=%s AND cart_status='active'", (customer_ids[0],))
            assert int(cur.fetchone()[0]) == 1
            cur.execute("SELECT COUNT(*) FROM public.cart_items WHERE shopping_cart_id IN (SELECT shopping_cart_id FROM public.shopping_carts WHERE customer_account_id=%s) AND product_id=%s", (customer_ids[0], product_id))
            assert int(cur.fetchone()[0]) == 1
    finally:
        db.close()
    assert client.post("/customer/cart/items", headers=bearer(customers[0]), json={"product_id": product_id, "quantity": 95}).status_code == 422
    foreign = {"quantity": 1, "row_version": version}
    assert client.put(f"/customer/cart/items/{item_id}", headers=bearer(customers[1]), json=foreign).status_code == 404
    assert client.delete(f"/customer/cart/items/{item_id}", headers=bearer(customers[1]), params={"row_version": version}).status_code == 404
    updated = client.put(f"/customer/cart/items/{item_id}", headers=bearer(customers[0]), json={"quantity": 4, "row_version": version})
    assert updated.status_code == 200 and updated.json()["line_subtotal_usd"] == "79.96"
    assert client.put(f"/customer/cart/items/{item_id}", headers=bearer(customers[0]), json={"quantity": 3, "row_version": version}).status_code == 409

    catalog = client.get(f"/admin/catalog/{product_id}", headers=bearer(staff["admin"])).json()
    repriced = client.put(f"/admin/catalog/{product_id}", headers=bearer(staff["admin"]), json=catalog_payload(price="21.99", version=catalog["row_version"]))
    assert repriced.status_code == 200
    cart = client.get("/customer/cart", headers=bearer(customers[0])).json()
    assert cart["cart_subtotal_usd"] == "79.96" and cart["items"][0]["price_changed"] is True
    unavailable = client.put(f"/admin/catalog/{product_id}", headers=bearer(staff["admin"]), json=catalog_payload(price="21.99", available=False, version=repriced.json()["row_version"]))
    assert unavailable.status_code == 200
    assert client.get(f"/customer/store/products/{product_id}", headers=bearer(customers[0])).status_code == 404
    assert all(item["product_id"] != product_id for item in client.get("/customer/store/products", headers=bearer(customers[0])).json())
    assert client.post("/customer/cart/items", headers=bearer(customers[0]), json={"product_id": product_id, "quantity": 1}).status_code == 404
    cart = client.get("/customer/cart", headers=bearer(customers[0])).json()
    assert len(cart["items"]) == 1 and cart["items"][0]["is_available"] is False
    latest_version = cart["items"][0]["row_version"]
    removed = client.delete(f"/customer/cart/items/{item_id}", headers=bearer(customers[0]), params={"row_version": latest_version})
    assert removed.status_code == 204
    assert client.get("/customer/cart", headers=bearer(customers[0])).json()["items"] == []
