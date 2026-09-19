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

from api.routers.admin_customers import router as admin_customers_router
from api.routers.auth import router as staff_auth_router
from api.routers.business import router as business_router
from api.routers.customer_auth import router as customer_auth_router
from api.routers.customer_profile import router as customer_profile_router
from core.config import Settings, get_settings
from core.security import hash_password
from db.connection import close_pool, initialize_pool


pytestmark = pytest.mark.integration
PASSWORD = "Customer-integration-1!"
CHANGED_PASSWORD = "Customer-integration-2!"
RESET_PASSWORD = "Customer-integration-3!"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def customer_payload(email: str) -> dict:
    return {
        "email": email,
        "password": PASSWORD,
        "first_name": "Customer",
        "last_name": "Tester",
        "phone": None,
    }


@pytest.fixture(scope="module")
def customer_context():
    if os.getenv("RUN_DB_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_DB_INTEGRATION_TESTS=1 to use PostgreSQL")
    previous_secret = os.environ.get("JWT_SECRET_KEY")
    os.environ["JWT_SECRET_KEY"] = secrets.token_urlsafe(48)
    get_settings.cache_clear()
    settings = replace(
        Settings.from_environment(), auth_lockout_attempts=3,
        auth_lockout_minutes=1, auth_reset_token_minutes=5,
        auth_expose_reset_token=True,
    )
    marker = f"rmitcustomer_{uuid.uuid4().hex[:12]}"
    expected_database = os.getenv("DB_INTEGRATION_EXPECTED_DATABASE", "retailmetrics")
    conn = psycopg2.connect(**settings.database_kwargs())
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), to_regclass('public.customer_accounts')")
            database, relation = cur.fetchone()
            cur.execute("SELECT COUNT(*) FROM public.app_users")
            staff_count = int(cur.fetchone()[0])
            cur.execute("SELECT COUNT(*) FROM public.customer_accounts")
            customer_count = int(cur.fetchone()[0])
        assert database == expected_database
        assert relation == "customer_accounts"
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
    app.include_router(staff_auth_router)
    app.include_router(business_router)
    app.include_router(customer_auth_router)
    app.include_router(customer_profile_router)
    app.include_router(admin_customers_router)
    app.dependency_overrides[get_settings] = lambda: settings

    def insert_staff(username: str, role: str) -> None:
        db = psycopg2.connect(**settings.database_kwargs())
        try:
            with db:
                with db.cursor() as cur:
                    cur.execute(
                        """INSERT INTO public.app_users (username,email,password_hash,role)
                           VALUES (%s,%s,%s,%s)""",
                        (username, f"{username}@example.com", hash_password(PASSWORD), role),
                    )
        finally:
            db.close()

    for suffix, role in (("admin", "admin"), ("ops", "operations_staff"), ("analyst", "analyst")):
        insert_staff(f"{marker}_{suffix}", role)

    try:
        with TestClient(app) as client:
            tokens = {}
            for suffix in ("admin", "ops", "analyst"):
                response = client.post("/auth/login", json={"identifier": f"{marker}_{suffix}", "password": PASSWORD})
                assert response.status_code == 200
                tokens[suffix] = response.json()["access_token"]
            yield client, settings, marker, tokens, staff_count, customer_count
    finally:
        cleanup = psycopg2.connect(**settings.database_kwargs())
        try:
            with cleanup:
                with cleanup.cursor() as cur:
                    cur.execute("SELECT customer_account_id FROM public.customer_accounts WHERE email LIKE %s", (marker + "%",))
                    customer_ids = [int(row[0]) for row in cur.fetchall()]
                    if customer_ids:
                        cur.execute("DELETE FROM public.customer_profiles WHERE customer_account_id=ANY(%s)", (customer_ids,))
                        cur.execute("DELETE FROM public.customer_accounts WHERE customer_account_id=ANY(%s)", (customer_ids,))
                    cur.execute("DELETE FROM public.app_users WHERE username LIKE %s", (marker + "_%",))
                    cur.execute("SELECT COUNT(*) FROM public.app_users")
                    assert int(cur.fetchone()[0]) == staff_count
                    cur.execute("SELECT COUNT(*) FROM public.customer_accounts")
                    assert int(cur.fetchone()[0]) == customer_count
        finally:
            cleanup.close()
            if previous_secret is None:
                os.environ.pop("JWT_SECRET_KEY", None)
            else:
                os.environ["JWT_SECRET_KEY"] = previous_secret
            get_settings.cache_clear()


def register(client: TestClient, email: str):
    return client.post("/customer/auth/register", json=customer_payload(email))


def login(client: TestClient, email: str, password: str = PASSWORD):
    return client.post("/customer/auth/login", json={"email": email, "password": password})


def test_registration_validation_atomicity_and_identity_separation(customer_context) -> None:
    client, settings, marker, tokens, staff_count, _ = customer_context
    email = f"{marker}_registration@example.com"
    created = register(client, email)
    assert created.status_code == 201
    body = created.json()
    assert body["email"] == email
    assert body["first_name"] == "Customer"
    assert "password_hash" not in body and "token_version" not in body
    assert register(client, email.upper()).status_code == 409

    weak = {**customer_payload(f"{marker}_weak@example.com"), "password": "weak"}
    assert client.post("/customer/auth/register", json=weak).status_code == 422
    invalid = {**customer_payload("not-an-email")}
    assert client.post("/customer/auth/register", json=invalid).status_code == 422
    forbidden = {**customer_payload(f"{marker}_claim@example.com"), "dataset_user_id": 1}
    assert client.post("/customer/auth/register", json=forbidden).status_code == 422

    db = psycopg2.connect(**settings.database_kwargs())
    try:
        with db.cursor() as cur:
            cur.execute("SELECT dataset_user_id FROM public.customer_accounts WHERE email=%s", (email,))
            assert cur.fetchone()[0] is None
            cur.execute("SELECT COUNT(*) FROM public.app_users")
            assert int(cur.fetchone()[0]) == staff_count + 3
    finally:
        db.close()

    customer_token = login(client, email.upper()).json()["access_token"]
    assert client.get("/customer/auth/me", headers=bearer(customer_token)).status_code == 200
    assert client.get("/auth/me", headers=bearer(customer_token)).status_code == 401
    assert client.get("/products", headers=bearer(customer_token)).status_code == 401
    assert client.get("/customer/auth/me", headers=bearer(tokens["analyst"])).status_code == 401


def test_customer_profile_password_reset_and_token_invalidation(customer_context) -> None:
    client, settings, marker, _, _, _ = customer_context
    email = f"{marker}_security@example.com"
    assert register(client, email).status_code == 201
    old_token = login(client, email).json()["access_token"]
    me = client.get("/customer/auth/me", headers=bearer(old_token)).json()
    profile = client.get("/customer/profile", headers=bearer(old_token))
    assert profile.status_code == 200
    version = profile.json()["row_version"]
    updated = client.put("/customer/profile", headers=bearer(old_token), json={
        "first_name": "Updated", "last_name": "Customer", "phone": "+63 900 000 0000", "row_version": version,
    })
    assert updated.status_code == 200 and updated.json()["row_version"] == version + 1
    assert client.put("/customer/profile", headers=bearer(old_token), json={
        "first_name": "Stale", "last_name": "Customer", "phone": None, "row_version": version,
    }).status_code == 409
    protected = {"first_name": "Bad", "last_name": "Input", "phone": None, "row_version": version + 1, "email": "other@example.com", "customer_account_id": me["customer_account_id"] + 1}
    assert client.put("/customer/profile", headers=bearer(old_token), json=protected).status_code == 422

    changed = client.post("/customer/auth/change-password", headers=bearer(old_token), json={"current_password": PASSWORD, "new_password": CHANGED_PASSWORD})
    assert changed.status_code == 200
    assert client.get("/customer/auth/me", headers=bearer(old_token)).status_code == 401
    assert login(client, email).status_code == 401
    changed_token = login(client, email, CHANGED_PASSWORD).json()["access_token"]

    forgot = client.post("/customer/auth/forgot-password", json={"email": email})
    reset_token = forgot.json()["reset_token"]
    db = psycopg2.connect(**settings.database_kwargs())
    try:
        with db.cursor() as cur:
            cur.execute("SELECT password_reset_token_hash FROM public.customer_accounts WHERE email=%s", (email,))
            stored = cur.fetchone()[0]
        assert stored and stored != reset_token
    finally:
        db.close()
    assert client.post("/customer/auth/reset-password", json={"reset_token": reset_token, "new_password": RESET_PASSWORD}).status_code == 200
    assert client.get("/customer/auth/me", headers=bearer(changed_token)).status_code == 401
    reset_login = login(client, email, RESET_PASSWORD)
    assert reset_login.status_code == 200
    reset_access = reset_login.json()["access_token"]
    assert client.post("/customer/auth/logout", headers=bearer(reset_access)).status_code == 200
    assert client.get("/customer/auth/me", headers=bearer(reset_access)).status_code == 401


def test_customer_lockout_expiry_and_admin_controls(customer_context) -> None:
    client, settings, marker, tokens, _, _ = customer_context
    email = f"{marker}_managed@example.com"
    assert register(client, email).status_code == 201
    for expected in (401, 401, 423):
        assert login(client, email, "wrong-password").status_code == expected
    assert login(client, email).status_code == 423

    admin = bearer(tokens["admin"])
    listed = client.get("/admin/customers", headers=admin, params={"search": email})
    assert listed.status_code == 200 and listed.json()["total"] == 1
    managed = listed.json()["items"][0]
    assert "password_hash" not in managed and "token_version" not in managed
    customer_id = managed["customer_account_id"]
    assert client.get(f"/admin/customers/{customer_id}", headers=admin).status_code == 200
    assert client.get("/admin/customers", headers=bearer(tokens["ops"])).status_code == 403
    assert client.get("/admin/customers", headers=bearer(tokens["analyst"])).status_code == 403

    unlocked = client.post(f"/admin/customers/{customer_id}/unlock", headers=admin, json={"row_version": managed["account_row_version"]})
    assert unlocked.status_code == 200 and unlocked.json()["locked_until"] is None
    customer_token = login(client, email).json()["access_token"]
    current = client.get(f"/admin/customers/{customer_id}", headers=admin).json()
    deactivated = client.put(f"/admin/customers/{customer_id}/status", headers=admin, json={"is_active": False, "row_version": current["account_row_version"]})
    assert deactivated.status_code == 200
    assert client.get("/customer/auth/me", headers=bearer(customer_token)).status_code == 401
    assert login(client, email).status_code == 403
    assert client.put(f"/admin/customers/{customer_id}/status", headers=admin, json={"is_active": True, "row_version": current["account_row_version"]}).status_code == 409
    reactivated = client.put(f"/admin/customers/{customer_id}/status", headers=admin, json={"is_active": True, "row_version": deactivated.json()["account_row_version"]})
    assert reactivated.status_code == 200

    db = psycopg2.connect(**settings.database_kwargs())
    try:
        with db:
            with db.cursor() as cur:
                cur.execute("UPDATE public.customer_accounts SET locked_until=NOW()-INTERVAL '1 second', failed_login_attempts=3 WHERE customer_account_id=%s", (customer_id,))
    finally:
        db.close()
    assert login(client, email).status_code == 200


def test_forgot_password_does_not_disclose_missing_customer(customer_context) -> None:
    client, _, marker, _, _, _ = customer_context
    response = client.post("/customer/auth/forgot-password", json={"email": f"{marker}_missing@example.com"})
    assert response.status_code == 200
    assert "reset_token" not in response.json()
