from __future__ import annotations

import html
import re
from types import SimpleNamespace

from fastapi import HTTPException
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api.routers.customer_auth import router as customer_auth_router
from core.config import Settings
from core.dependencies import get_customer_repository
from core.config import get_settings
from core.security import hash_password
import db.connection as connection_module
from frontend.views import unified_auth
from services.auth_service import AuthService
from services.customer_auth_service import CustomerAuthService
from services.notifications.providers import SmtpEmailProvider
from tests.unit.fake_customer_repository import FakeCustomerRepository
from tests.unit.fake_user_repository import FakeUserRepository


PASSWORD = "Customer-password-1!"
NEW_PASSWORD = "Customer-password-2!"


def live_settings() -> Settings:
    return Settings(
        jwt_secret_key="s" * 64,
        auth_reset_token_minutes=5,
        auth_expose_reset_token=True,
        notification_mode="live",
        email_provider="smtp",
        smtp_host="smtp.gmail.com",
        smtp_port=587,
        smtp_username="sender@example.invalid",
        smtp_password="unit-only-password",
        smtp_from_email="sender@example.invalid",
        smtp_live_send_enabled=True,
        sms_live_send_enabled=False,
    )


def token_from_message(message) -> str:
    match = re.search(r'padding:14px">([^<]+)</div>', message.body)
    assert match
    return html.unescape(match.group(1))


class FakeSmtp:
    sent = []

    def __init__(self, host, port, timeout):
        assert (host, port, timeout) == ("smtp.gmail.com", 587, 10)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def ehlo(self):
        pass

    def starttls(self, *, context):
        assert context is not None

    def login(self, username, password):
        assert username == "sender@example.invalid"
        assert password == "unit-only-password"

    def send_message(self, message):
        self.sent.append(message)


def test_registered_customer_reset_is_queued_emailed_and_token_still_resets_password():
    repository = FakeCustomerRepository()
    identity = repository.create_with_profile(
        "customer@example.com", hash_password(PASSWORD), "Ada", "Lovelace", None
    )
    queued = []
    service = CustomerAuthService(repository, live_settings(), queued.append)

    assert service.forgot_password(identity.account.email) is None
    assert len(queued) == 1
    message = queued[0]
    assert message.event_type == "customer_password_reset"
    assert message.subject == "RetailMetrics Password Reset"
    assert "temporary reset code" in message.body
    raw_token = token_from_message(message)

    FakeSmtp.sent.clear()
    SmtpEmailProvider(live_settings(), smtp_factory=FakeSmtp).send_email(message)
    assert len(FakeSmtp.sent) == 1

    service.reset_password(raw_token, NEW_PASSWORD)
    token, _ = service.login(identity.account.email, NEW_PASSWORD)
    assert token


def test_unknown_customer_keeps_generic_behavior_and_queues_nothing():
    queued = []
    service = CustomerAuthService(FakeCustomerRepository(), live_settings(), queued.append)
    assert service.forgot_password("missing@example.com") is None
    assert queued == []


def test_live_customer_api_response_is_generic_and_never_contains_token():
    repository = FakeCustomerRepository()
    repository.create_with_profile(
        "customer@example.com", hash_password(PASSWORD), "Ada", "Lovelace", None
    )
    app = FastAPI()
    app.include_router(customer_auth_router)
    app.dependency_overrides[get_customer_repository] = lambda: repository
    app.dependency_overrides[get_settings] = live_settings
    with TestClient(app) as client:
        response = client.post(
            "/customer/auth/forgot-password", json={"email": "customer@example.com"}
        )
    assert response.status_code == 200
    assert response.json() == {
        "message": "If the email is registered, password-reset instructions have been sent."
    }


def test_queued_authentication_email_dispatches_after_commit(monkeypatch):
    queued = []
    repository = FakeCustomerRepository()
    identity = repository.create_with_profile(
        "customer@example.com", hash_password(PASSWORD), "Ada", "Lovelace", None
    )
    CustomerAuthService(repository, live_settings(), queued.append).forgot_password(
        identity.account.email
    )
    message = queued[0]

    class FakeConnection:
        def __init__(self):
            self.commits = 0

        def commit(self):
            self.commits += 1

        def rollback(self):
            pass

    class FakePool:
        def __init__(self, conn):
            self.conn = conn

        def getconn(self):
            return self.conn

        def putconn(self, conn):
            assert conn is self.conn

    class FakeProvider:
        def send_email(self, delivered):
            assert conn.commits == 1
            delivered_messages.append(delivered)

    conn = FakeConnection()
    delivered_messages = []
    monkeypatch.setattr(connection_module, "_pool", FakePool(conn))
    import services.notifications.providers as providers
    monkeypatch.setattr(providers, "provider_for", lambda settings: FakeProvider())
    request = SimpleNamespace(
        state=SimpleNamespace(post_commit_notification_messages=[message])
    )
    dependency = connection_module.get_db_connection(request, live_settings())
    assert next(dependency) is conn
    with pytest.raises(StopIteration):
        next(dependency)
    assert delivered_messages == [message]
    assert conn.commits == 1


def test_staff_and_customer_reset_domains_remain_separate():
    settings = live_settings()
    staff_repository = FakeUserRepository()
    staff = staff_repository.create_analyst(
        "staff", "staff@example.com", hash_password(PASSWORD)
    )
    customer_repository = FakeCustomerRepository()
    customer = customer_repository.create_with_profile(
        "customer@example.com", hash_password(PASSWORD), "Ada", "Lovelace", None
    )
    staff_messages, customer_messages = [], []
    staff_service = AuthService(staff_repository, settings, staff_messages.append)
    customer_service = CustomerAuthService(customer_repository, settings, customer_messages.append)

    assert staff_service.forgot_password(staff.email) is None
    assert customer_service.forgot_password(customer.account.email) is None
    assert staff_messages[0].event_type == "staff_password_reset"
    assert customer_messages[0].event_type == "customer_password_reset"
    assert token_from_message(staff_messages[0]) != token_from_message(customer_messages[0])


def test_invalid_or_expired_reset_tokens_keep_existing_generic_failure():
    staff = AuthService(FakeUserRepository(), live_settings())
    customer = CustomerAuthService(FakeCustomerRepository(), live_settings())
    for service in (staff, customer):
        with pytest.raises(HTTPException) as raised:
            service.reset_password("invalid-or-expired-token-value-000", NEW_PASSWORD)
        assert raised.value.status_code == 400
        assert raised.value.detail == "Reset token is invalid or expired."


def test_live_frontend_never_renders_reset_token(monkeypatch):
    class FakeClient:
        def post(self, path, payload):
            assert path in {"/auth/forgot-password", "/customer/auth/forgot-password"}
            return {"message": "If the email is registered, password-reset instructions have been sent."}

    successes = []
    monkeypatch.setattr(unified_auth.st, "success", successes.append)
    monkeypatch.setattr(
        unified_auth.st, "warning",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Token warning rendered")),
    )
    monkeypatch.setattr(
        unified_auth.st, "code",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Token rendered")),
    )
    unified_auth._request_reset(FakeClient(), "customer@example.com")
    assert successes == ["If the email is registered, password-reset instructions have been sent."]
