from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
import pytest

from api.routers.auth import router as auth_router
from core.config import Settings, get_settings
from core.dependencies import get_user_repository, require_roles
from core.models import AppUser, Role
from core.security import hash_reset_token
from tests.unit.fake_user_repository import FakeUserRepository


PASSWORD = "Strong-password-1!"
NEW_PASSWORD = "Different-password-2!"


@pytest.fixture
def api_context():
    repository = FakeUserRepository()
    settings = Settings(
        jwt_secret_key="test-only-signing-secret-which-is-at-least-32-characters",
        jwt_access_token_minutes=10,
        auth_lockout_attempts=3,
        auth_lockout_minutes=5,
        auth_reset_token_minutes=5,
        auth_expose_reset_token=True,
    )
    app = FastAPI()
    app.include_router(auth_router)

    @app.get("/test/admin")
    def admin_only(_: AppUser = Depends(require_roles(Role.ADMIN))):
        return {"allowed": True}

    @app.get("/test/operations")
    def operations_or_admin(
        _: AppUser = Depends(
            require_roles(Role.ADMIN, Role.OPERATIONS_STAFF)
        ),
    ):
        return {"allowed": True}

    app.dependency_overrides[get_user_repository] = lambda: repository
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as client:
        yield client, repository


def register(client: TestClient, username: str = "student"):
    return client.post(
        "/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": PASSWORD,
        },
    )


def login(client: TestClient, identifier: str = "student", password: str = PASSWORD):
    return client.post(
        "/auth/login",
        json={"identifier": identifier, "password": password},
    )


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_registration_forces_analyst_and_never_returns_hashes(api_context) -> None:
    client, _ = api_context
    rejected = client.post(
        "/auth/register",
        json={
            "username": "attacker",
            "email": "attacker@example.com",
            "password": PASSWORD,
            "role": "admin",
        },
    )
    assert rejected.status_code == 422

    response = register(client)
    assert response.status_code == 201
    body = response.json()
    assert body["role"] == "analyst"
    assert "password_hash" not in body
    assert "password_reset_token_hash" not in body


def test_login_me_and_role_are_reloaded_from_repository(api_context) -> None:
    client, repository = api_context
    user_id = register(client).json()["app_user_id"]
    token = login(client).json()["access_token"]

    assert client.get("/auth/me", headers=bearer(token)).json()["role"] == "analyst"
    assert client.get("/test/admin", headers=bearer(token)).status_code == 403
    assert client.get("/test/operations", headers=bearer(token)).status_code == 403

    repository.set_role(user_id, Role.OPERATIONS_STAFF)
    assert client.get("/auth/me", headers=bearer(token)).json()["role"] == "operations_staff"
    assert client.get("/test/operations", headers=bearer(token)).status_code == 200
    assert client.get("/test/admin", headers=bearer(token)).status_code == 403

    repository.set_role(user_id, Role.ADMIN)
    assert client.get("/test/admin", headers=bearer(token)).status_code == 200


def test_logout_invalidates_existing_token(api_context) -> None:
    client, _ = api_context
    register(client)
    token = login(client).json()["access_token"]
    assert client.post("/auth/logout", headers=bearer(token)).status_code == 200
    assert client.get("/auth/me", headers=bearer(token)).status_code == 401


def test_temporary_lockout_refuses_correct_password(api_context) -> None:
    client, _ = api_context
    register(client)
    assert login(client, password="wrong-1").status_code == 401
    assert login(client, password="wrong-2").status_code == 401
    assert login(client, password="wrong-3").status_code == 423
    assert login(client).status_code == 423


def test_inactive_account_is_refused_for_login_and_existing_token(api_context) -> None:
    client, repository = api_context
    user_id = register(client).json()["app_user_id"]
    token = login(client).json()["access_token"]
    repository.set_active(user_id, False)
    assert login(client).status_code == 403
    assert client.get("/auth/me", headers=bearer(token)).status_code == 403


def test_change_password_invalidates_tokens_and_old_password(api_context) -> None:
    client, _ = api_context
    register(client)
    token = login(client).json()["access_token"]
    response = client.post(
        "/auth/change-password",
        headers=bearer(token),
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 200
    assert client.get("/auth/me", headers=bearer(token)).status_code == 401
    assert login(client).status_code == 401
    assert login(client, password=NEW_PASSWORD).status_code == 200


def test_local_forgot_and_reset_flow_stores_only_token_hash(api_context) -> None:
    client, repository = api_context
    user_id = register(client).json()["app_user_id"]
    response = client.post(
        "/auth/forgot-password",
        json={"email": "student@example.com"},
    )
    assert response.status_code == 200
    raw_token = response.json()["reset_token"]
    assert raw_token
    assert repository.reset_hashes[hash_reset_token(raw_token)] == user_id
    assert raw_token not in repository.reset_hashes
    assert "password_reset_token_hash" not in response.json()

    reset = client.post(
        "/auth/reset-password",
        json={"reset_token": raw_token, "new_password": NEW_PASSWORD},
    )
    assert reset.status_code == 200
    assert login(client).status_code == 401
    assert login(client, password=NEW_PASSWORD).status_code == 200


def test_forgot_password_does_not_disclose_unknown_email(api_context) -> None:
    client, _ = api_context
    response = client.post(
        "/auth/forgot-password",
        json={"email": "unknown@example.com"},
    )
    assert response.status_code == 200
    assert "reset_token" not in response.json()
