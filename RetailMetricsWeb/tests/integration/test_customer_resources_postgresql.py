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

from api.routers.customer_auth import router as customer_auth_router
from api.routers.customer_resources import router as customer_resources_router
from core.config import Settings, get_settings
from db.connection import close_pool, initialize_pool


pytestmark = pytest.mark.integration
PASSWORD = "Customer-resource-1!"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def address(label: str) -> dict:
    return {
        "label": label, "recipient_first_name": "Demo", "recipient_last_name": "Customer",
        "phone": None, "address_line_1": "1 Test Street", "address_line_2": None,
        "city": "Manila", "province_region": "Metro Manila", "postal_code": "1000",
        "country_code": "PH", "is_default": False,
    }


@pytest.fixture(scope="module")
def resource_context():
    if os.getenv("RUN_DB_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_DB_INTEGRATION_TESTS=1 to use PostgreSQL")
    old_secret = os.environ.get("JWT_SECRET_KEY")
    os.environ["JWT_SECRET_KEY"] = secrets.token_urlsafe(48)
    get_settings.cache_clear()
    settings = replace(Settings.from_environment(), jwt_secret_key=os.environ["JWT_SECRET_KEY"])
    marker = f"rmitresource_{uuid.uuid4().hex[:12]}"
    db = psycopg2.connect(**settings.database_kwargs())
    try:
        with db.cursor() as cur:
            cur.execute("SELECT current_database(), COUNT(*) FROM public.customer_accounts")
            database, account_count = cur.fetchone()
            cur.execute("SELECT COUNT(*) FROM public.customer_addresses")
            address_count = int(cur.fetchone()[0])
            cur.execute("SELECT COUNT(*) FROM public.payment_methods")
            payment_count = int(cur.fetchone()[0])
        assert database == os.getenv("DB_INTEGRATION_EXPECTED_DATABASE", "retailmetrics")
    finally:
        db.close()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        initialize_pool(settings)
        try:
            yield
        finally:
            close_pool()

    app = FastAPI(lifespan=lifespan)
    app.include_router(customer_auth_router)
    app.include_router(customer_resources_router)
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            tokens, ids = [], []
            for number in (1, 2):
                email = f"{marker}_{number}@example.com"
                response = client.post("/customer/auth/register", json={
                    "email": email, "password": PASSWORD, "first_name": "Resource",
                    "last_name": f"Owner{number}", "phone": None,
                })
                assert response.status_code == 201
                ids.append(response.json()["customer_account_id"])
                login = client.post("/customer/auth/login", json={"email": email, "password": PASSWORD})
                tokens.append(login.json()["access_token"])
            yield client, settings, marker, tokens, ids
    finally:
        cleanup = psycopg2.connect(**settings.database_kwargs())
        try:
            with cleanup:
                with cleanup.cursor() as cur:
                    cur.execute("SELECT customer_account_id FROM public.customer_accounts WHERE email LIKE %s", (marker + "_%",))
                    ids = [int(row[0]) for row in cur.fetchall()]
                    if ids:
                        cur.execute("DELETE FROM public.payment_methods WHERE customer_account_id=ANY(%s)", (ids,))
                        cur.execute("DELETE FROM public.customer_addresses WHERE customer_account_id=ANY(%s)", (ids,))
                        cur.execute("DELETE FROM public.customer_profiles WHERE customer_account_id=ANY(%s)", (ids,))
                        cur.execute("DELETE FROM public.customer_accounts WHERE customer_account_id=ANY(%s)", (ids,))
                    cur.execute("SELECT COUNT(*) FROM public.customer_accounts")
                    assert int(cur.fetchone()[0]) == int(account_count)
                    cur.execute("SELECT COUNT(*) FROM public.customer_addresses")
                    assert int(cur.fetchone()[0]) == address_count
                    cur.execute("SELECT COUNT(*) FROM public.payment_methods")
                    assert int(cur.fetchone()[0]) == payment_count
        finally:
            cleanup.close()
            if old_secret is None:
                os.environ.pop("JWT_SECRET_KEY", None)
            else:
                os.environ["JWT_SECRET_KEY"] = old_secret
            get_settings.cache_clear()


def test_address_lifecycle_ownership_default_and_concurrency(resource_context) -> None:
    client, _, _, tokens, _ = resource_context
    first = client.post("/customer/addresses", headers=bearer(tokens[0]), json=address("Home"))
    assert first.status_code == 201
    first_data = first.json()
    assert first_data["is_default"] is True
    second = client.post("/customer/addresses", headers=bearer(tokens[0]), json=address("Office"))
    second_data = second.json()
    assert second.status_code == 201 and second_data["is_default"] is False
    address_id = second_data["customer_address_id"]
    assert client.get(f"/customer/addresses/{address_id}", headers=bearer(tokens[1])).status_code == 404
    foreign_update = {**address("Stolen"), "row_version": second_data["row_version"]}
    foreign_update.pop("is_default")
    assert client.put(f"/customer/addresses/{address_id}", headers=bearer(tokens[1]), json=foreign_update).status_code == 404
    update = {**foreign_update, "label": "Work"}
    changed = client.put(f"/customer/addresses/{address_id}", headers=bearer(tokens[0]), json=update)
    assert changed.status_code == 200 and changed.json()["row_version"] == 2
    assert client.put(f"/customer/addresses/{address_id}", headers=bearer(tokens[0]), json=update).status_code == 409
    selected = client.post(f"/customer/addresses/{address_id}/set-default", headers=bearer(tokens[0]), json={"row_version": 2})
    assert selected.status_code == 200 and selected.json()["is_default"]
    listed = client.get("/customer/addresses", headers=bearer(tokens[0])).json()
    assert sum(x["is_default"] and x["is_active"] for x in listed) == 1
    stopped = client.post(f"/customer/addresses/{address_id}/deactivate", headers=bearer(tokens[0]), json={"row_version": selected.json()["row_version"]})
    assert stopped.status_code == 200 and not stopped.json()["is_active"]
    listed = client.get("/customer/addresses", headers=bearer(tokens[0])).json()
    assert sum(x["is_default"] and x["is_active"] for x in listed) == 1


def test_simulated_payment_lifecycle_validation_and_ownership(resource_context) -> None:
    client, _, _, tokens, _ = resource_context
    payloads = [
        ({"method_type": "card", "card_brand": "Visa", "card_last_four": "1234", "is_default": False}, "Visa ending in 1234 — simulated"),
        ({"method_type": "gcash", "card_brand": None, "card_last_four": None, "is_default": False}, "GCash — simulated"),
        ({"method_type": "paypal", "card_brand": None, "card_last_four": None, "is_default": False}, "PayPal — simulated"),
        ({"method_type": "cash_on_delivery", "card_brand": None, "card_last_four": None, "is_default": False}, "Cash on Delivery"),
    ]
    created = []
    for payload, label in payloads:
        response = client.post("/customer/payment-methods", headers=bearer(tokens[0]), json=payload)
        assert response.status_code == 201 and response.json()["display_label"] == label
        created.append(response.json())
    assert created[0]["is_default"] is True
    method_id = created[2]["payment_method_id"]
    assert client.get(f"/customer/payment-methods/{method_id}", headers=bearer(tokens[1])).status_code == 404
    assert client.post(f"/customer/payment-methods/{method_id}/deactivate", headers=bearer(tokens[1]), json={"row_version": 1}).status_code == 404
    update = {"method_type": "card", "card_brand": "Mastercard", "card_last_four": "5678", "row_version": 1}
    changed = client.put(f"/customer/payment-methods/{method_id}", headers=bearer(tokens[0]), json=update)
    assert changed.status_code == 200 and changed.json()["display_label"] == "Mastercard ending in 5678 — simulated"
    assert client.put(f"/customer/payment-methods/{method_id}", headers=bearer(tokens[0]), json=update).status_code == 409
    selected = client.post(f"/customer/payment-methods/{method_id}/set-default", headers=bearer(tokens[0]), json={"row_version": 2})
    assert selected.status_code == 200
    listed = client.get("/customer/payment-methods", headers=bearer(tokens[0])).json()
    assert sum(x["is_default"] and x["is_active"] for x in listed) == 1
    stopped = client.post(f"/customer/payment-methods/{method_id}/deactivate", headers=bearer(tokens[0]), json={"row_version": selected.json()["row_version"]})
    assert stopped.status_code == 200 and not stopped.json()["is_active"]
    listed = client.get("/customer/payment-methods", headers=bearer(tokens[0])).json()
    assert sum(x["is_default"] and x["is_active"] for x in listed) == 1


def test_sensitive_payment_fields_and_invalid_metadata_are_rejected(resource_context) -> None:
    client, _, _, tokens, _ = resource_context
    base = {"method_type": "card", "card_brand": "Visa", "card_last_four": "1234"}
    for field in ("full_card_number", "card_number", "cvv", "gcash_number", "paypal_email", "password", "otp", "access_token", "customer_account_id", "display_label"):
        response = client.post("/customer/payment-methods", headers=bearer(tokens[0]), json={**base, field: "forbidden"})
        assert response.status_code == 422, field
    assert client.post("/customer/payment-methods", headers=bearer(tokens[0]), json={"method_type": "card", "card_brand": "Visa"}).status_code == 422
    assert client.post("/customer/payment-methods", headers=bearer(tokens[0]), json={"method_type": "gcash", "card_brand": "Visa", "card_last_four": "1234"}).status_code == 422


def test_inactive_customer_cannot_mutate_saved_resources(resource_context) -> None:
    client, settings, _, tokens, ids = resource_context
    db = psycopg2.connect(**settings.database_kwargs())
    try:
        with db:
            with db.cursor() as cur:
                cur.execute("UPDATE public.customer_accounts SET is_active=FALSE WHERE customer_account_id=%s", (ids[1],))
        response = client.post("/customer/addresses", headers=bearer(tokens[1]), json=address("Denied"))
        assert response.status_code == 403
    finally:
        with db:
            with db.cursor() as cur:
                cur.execute("UPDATE public.customer_accounts SET is_active=TRUE WHERE customer_account_id=%s", (ids[1],))
        db.close()
