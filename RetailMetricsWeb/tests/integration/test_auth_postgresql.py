from __future__ import annotations

import os
import secrets
import uuid
from contextlib import asynccontextmanager
from dataclasses import replace

import psycopg2
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from api.routers.auth import router as auth_router
from api.routers.admin_users import router as admin_users_router
from core.config import Settings, get_settings
from core.dependencies import get_current_user, require_roles
from core.models import AppUser, Role
from core.security import hash_password
from db.connection import close_pool, initialize_pool


pytestmark = pytest.mark.integration
PASSWORD = "Integration-password-1!"
CHANGED_PASSWORD = "Integration-password-2!"
RESET_PASSWORD = "Integration-password-3!"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def integration_context():
    if os.getenv("RUN_DB_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_DB_INTEGRATION_TESTS=1 to use the real database")

    previous_jwt_secret = os.environ.get("JWT_SECRET_KEY")
    os.environ["JWT_SECRET_KEY"] = secrets.token_urlsafe(48)
    get_settings.cache_clear()
    settings = replace(
        Settings.from_environment(),
        auth_lockout_attempts=3,
        auth_lockout_minutes=1,
        auth_reset_token_minutes=5,
        auth_expose_reset_token=True,
    )
    prefix = f"rmit_{uuid.uuid4().hex[:16]}_"
    expected_database = os.getenv("DB_INTEGRATION_EXPECTED_DATABASE", "retailmetrics")

    probe = psycopg2.connect(**settings.database_kwargs())
    try:
        with probe.cursor() as cur:
            cur.execute("SELECT current_database(), to_regclass('public.app_users')")
            database_name, app_users = cur.fetchone()
        assert database_name == expected_database
        assert app_users == "app_users"
    finally:
        probe.close()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        initialize_pool(settings)
        try:
            yield
        finally:
            close_pool()

    app = FastAPI(lifespan=lifespan)
    app.include_router(auth_router)
    app.include_router(admin_users_router)

    @app.get("/integration/admin-only")
    def admin_only(_: AppUser = Depends(require_roles(Role.ADMIN))):
        return {"allowed": True}

    @app.get("/integration/authenticated")
    def authenticated(user: AppUser = Depends(get_current_user)):
        return {"app_user_id": user.app_user_id}

    app.dependency_overrides[get_settings] = lambda: settings

    try:
        with TestClient(app) as client:
            yield client, settings, prefix
    finally:
        cleanup = psycopg2.connect(**settings.database_kwargs())
        try:
            with cleanup:
                with cleanup.cursor() as cur:
                    cur.execute(
                        """
                        SELECT app_user_id
                        FROM public.app_users
                        WHERE username LIKE %s
                        """,
                        (prefix + "%",),
                    )
                    user_ids = [int(row[0]) for row in cur.fetchall()]
                    if user_ids:
                        for table_name in (
                            "products",
                            "orders",
                            "order_items",
                            "order_item_refunds",
                        ):
                            cur.execute(
                                f"""
                                SELECT COUNT(*)
                                FROM public.{table_name}
                                WHERE created_by_app_user_id = ANY(%s)
                                """,
                                (user_ids,),
                            )
                            assert cur.fetchone()[0] == 0, (
                                f"Refusing test cleanup: public.{table_name} "
                                "references a disposable authentication user"
                            )
                        cur.execute(
                            "DELETE FROM public.app_users WHERE app_user_id = ANY(%s)",
                            (user_ids,),
                        )
        finally:
            cleanup.close()
            if previous_jwt_secret is None:
                os.environ.pop("JWT_SECRET_KEY", None)
            else:
                os.environ["JWT_SECRET_KEY"] = previous_jwt_secret
            get_settings.cache_clear()


def register(client: TestClient, username: str, password: str = PASSWORD):
    return client.post(
        "/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": password,
        },
    )


def login(client: TestClient, username: str, password: str = PASSWORD):
    return client.post(
        "/auth/login",
        json={"identifier": username, "password": password},
    )


def insert_test_admin(settings: Settings, username: str) -> int:
    conn = psycopg2.connect(**settings.database_kwargs())
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO public.app_users
                        (username, email, password_hash, role)
                    VALUES (%s, %s, %s, 'admin')
                    RETURNING app_user_id
                    """,
                    (
                        username,
                        f"{username}@example.com",
                        hash_password(PASSWORD),
                    ),
                )
                return int(cur.fetchone()[0])
    finally:
        conn.close()


def test_registration_login_me_and_admin_authorization(integration_context) -> None:
    client, settings, prefix = integration_context
    analyst = prefix + "analyst"
    admin = prefix + "admin"

    registration = register(client, analyst)
    assert registration.status_code == 201
    assert registration.json()["role"] == "analyst"
    assert "password_hash" not in registration.json()

    analyst_login = login(client, analyst)
    assert analyst_login.status_code == 200
    analyst_token = analyst_login.json()["access_token"]
    assert client.get("/auth/me", headers=bearer(analyst_token)).json()["role"] == "analyst"
    assert client.get(
        "/integration/admin-only", headers=bearer(analyst_token)
    ).status_code == 403

    insert_test_admin(settings, admin)
    admin_login = login(client, admin)
    assert admin_login.status_code == 200
    assert client.get(
        "/integration/admin-only",
        headers=bearer(admin_login.json()["access_token"]),
    ).status_code == 200


def test_password_change_and_logout_invalidate_tokens(integration_context) -> None:
    client, _, prefix = integration_context
    username = prefix + "password"
    assert register(client, username).status_code == 201
    old_token = login(client, username).json()["access_token"]

    changed = client.post(
        "/auth/change-password",
        headers=bearer(old_token),
        json={"current_password": PASSWORD, "new_password": CHANGED_PASSWORD},
    )
    assert changed.status_code == 200
    assert client.get("/auth/me", headers=bearer(old_token)).status_code == 401
    assert login(client, username).status_code == 401

    new_login = login(client, username, CHANGED_PASSWORD)
    assert new_login.status_code == 200
    new_token = new_login.json()["access_token"]
    assert client.post("/auth/logout", headers=bearer(new_token)).status_code == 200
    assert client.get("/auth/me", headers=bearer(new_token)).status_code == 401


def test_reset_password_is_hashed_and_invalidates_token(integration_context) -> None:
    client, settings, prefix = integration_context
    username = prefix + "reset"
    assert register(client, username).status_code == 201
    old_token = login(client, username).json()["access_token"]

    forgot = client.post(
        "/auth/forgot-password",
        json={"email": f"{username}@example.com"},
    )
    assert forgot.status_code == 200
    reset_token = forgot.json()["reset_token"]

    conn = psycopg2.connect(**settings.database_kwargs())
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT password_reset_token_hash
                FROM public.app_users
                WHERE username = %s
                """,
                (username,),
            )
            stored_hash = cur.fetchone()[0]
        assert stored_hash
        assert stored_hash != reset_token
    finally:
        conn.close()

    reset = client.post(
        "/auth/reset-password",
        json={"reset_token": reset_token, "new_password": RESET_PASSWORD},
    )
    assert reset.status_code == 200
    assert client.get("/auth/me", headers=bearer(old_token)).status_code == 401
    assert login(client, username).status_code == 401
    assert login(client, username, RESET_PASSWORD).status_code == 200


def test_lockout_is_persisted_in_postgresql(integration_context) -> None:
    client, settings, prefix = integration_context
    username = prefix + "lockout"
    assert register(client, username).status_code == 201
    assert login(client, username, "wrong-password-1").status_code == 401
    assert login(client, username, "wrong-password-2").status_code == 401
    assert login(client, username, "wrong-password-3").status_code == 423
    assert login(client, username).status_code == 423

    conn = psycopg2.connect(**settings.database_kwargs())
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT failed_login_attempts, locked_until > NOW()
                FROM public.app_users
                WHERE username = %s
                """,
                (username,),
            )
            attempts, currently_locked = cur.fetchone()
        assert attempts == 3
        assert currently_locked is True
    finally:
        conn.close()


def test_admin_user_management_lifecycle(integration_context) -> None:
    client, settings, prefix = integration_context
    admin_name = prefix + "manager"
    insert_test_admin(settings, admin_name)
    admin_token = login(client, admin_name).json()["access_token"]
    admin_headers = bearer(admin_token)

    managed_name = prefix + "managed"
    created = client.post(
        "/admin/users",
        headers=admin_headers,
        json={
            "username": managed_name,
            "email": f"{managed_name}@example.com",
            "password": PASSWORD,
            "role": "operations_staff",
        },
    )
    assert created.status_code == 201
    managed = created.json()
    managed_id = managed["app_user_id"]
    assert managed["role"] == "operations_staff"
    assert "password_hash" not in managed

    operations_token = login(client, managed_name).json()["access_token"]
    assert client.get("/admin/users", headers=bearer(operations_token)).status_code == 403
    listed = client.get(
        "/admin/users", headers=admin_headers, params={"search": managed_name}
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    managed = listed.json()["items"][0]
    assert client.get(f"/admin/users/{managed_id}", headers=admin_headers).status_code == 200
    assert client.delete(f"/admin/users/{managed_id}", headers=admin_headers).status_code == 405

    role_change = client.put(
        f"/admin/users/{managed_id}/role",
        headers=admin_headers,
        json={"role": "analyst", "row_version": managed["row_version"]},
    )
    assert role_change.status_code == 200
    assert role_change.json()["role"] == "analyst"
    assert client.get("/auth/me", headers=bearer(operations_token)).status_code == 401
    assert client.put(
        f"/admin/users/{managed_id}/role",
        headers=admin_headers,
        json={"role": "operations_staff", "row_version": managed["row_version"]},
    ).status_code == 409

    current = role_change.json()
    deactivated = client.put(
        f"/admin/users/{managed_id}/status",
        headers=admin_headers,
        json={"is_active": False, "row_version": current["row_version"]},
    )
    assert deactivated.status_code == 200
    assert login(client, managed_name).status_code == 403
    reactivated = client.put(
        f"/admin/users/{managed_id}/status",
        headers=admin_headers,
        json={"is_active": True, "row_version": deactivated.json()["row_version"]},
    )
    assert reactivated.status_code == 200

    assert login(client, managed_name, "wrong-password-1").status_code == 401
    assert login(client, managed_name, "wrong-password-2").status_code == 401
    assert login(client, managed_name, "wrong-password-3").status_code == 423
    locked = client.get(f"/admin/users/{managed_id}", headers=admin_headers).json()
    unlocked = client.post(
        f"/admin/users/{managed_id}/unlock",
        headers=admin_headers,
        json={"row_version": locked["row_version"]},
    )
    assert unlocked.status_code == 200
    assert unlocked.json()["locked_until"] is None
    assert unlocked.json()["failed_login_attempts"] == 0
    assert login(client, managed_name).status_code == 200

    admin_self = client.get("/auth/me", headers=admin_headers).json()
    admin_detail = client.get(
        f"/admin/users/{admin_self['app_user_id']}", headers=admin_headers
    ).json()
    assert client.put(
        f"/admin/users/{admin_self['app_user_id']}/status",
        headers=admin_headers,
        json={"is_active": False, "row_version": admin_detail["row_version"]},
    ).status_code == 409
