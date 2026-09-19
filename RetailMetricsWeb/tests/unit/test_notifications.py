from __future__ import annotations

from dataclasses import replace

import httpx
import jwt
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.auth import router as auth_router
from api.routers.notifications import notification_config, router as notification_router
from core.config import Settings, get_settings
from core.dependencies import get_user_repository
from core.models import Role
from services.notifications.phone import normalize_mobile
from services.notifications.providers import (
    InfobipNotificationProvider,
    Message,
    MockNotificationProvider,
    ProviderFailure,
    RoutedNotificationProvider,
    SmtpEmailProvider,
    delivery_mode,
    provider_for,
)
from tests.unit.fake_user_repository import FakeUserRepository


def test_phone_normalization_rejects_ambiguous_or_invalid_values():
    assert normalize_mobile("0917 123 4567") == "+639171234567"
    assert normalize_mobile("639171234567") == "+639171234567"
    assert normalize_mobile("+639171234567") == "+639171234567"
    for value in (None, "", "9171234567", "0917123456", "09abc123456", "+63+9171234567"):
        assert normalize_mobile(value) is None


def test_mock_provider_never_makes_network_request(monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("Network access is forbidden in mock mode")

    monkeypatch.setattr(httpx.Client, "post", no_network)
    provider = provider_for(Settings(notification_mode="mock"))
    assert isinstance(provider, MockNotificationProvider)
    email = Message("order_confirmation", "email", "test@example.com", "Order", "<p>Invoice</p>")
    sms = Message("order_processing", "sms", "+639171234567", None, "Processing")
    assert provider.send_email(email).message_id.startswith("mock-")
    assert provider.send_sms(sms).message_id.startswith("mock-")
    assert provider.messages == [email, sms]


class FakeSmtp:
    instances = []

    def __init__(self, host, port, timeout):
        self.host, self.port, self.timeout = host, port, timeout
        self.calls = []
        self.message = None
        FakeSmtp.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def ehlo(self):
        self.calls.append("ehlo")

    def starttls(self, *, context):
        assert context is not None
        self.calls.append("starttls")

    def login(self, username, password):
        self.calls.append(("login", username, password))

    def send_message(self, message):
        self.calls.append("send_message")
        self.message = message


def smtp_settings(**overrides):
    values = {
        "notification_mode": "live",
        "email_provider": "smtp",
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_username": "sender@example.invalid",
        "smtp_password": "unit-only-password",
        "smtp_from_email": "sender@example.invalid",
        "smtp_from_name": "RetailMetrics",
        "smtp_live_send_enabled": True,
        "sms_live_send_enabled": False,
    }
    values.update(overrides)
    return Settings(**values)


def test_smtp_email_uses_starttls_login_and_email_message_without_network():
    FakeSmtp.instances.clear()
    provider = SmtpEmailProvider(smtp_settings(), smtp_factory=FakeSmtp)
    result = provider.send_email(Message(
        "admin_test", "email", "recipient@example.invalid", "Test subject", "<p>Hello</p>"
    ))
    assert result.message_id == "smtp-accepted"
    smtp = FakeSmtp.instances[0]
    assert (smtp.host, smtp.port, smtp.timeout) == ("smtp.gmail.com", 587, 10)
    assert smtp.calls == ["ehlo", "starttls", "ehlo",
                          ("login", "sender@example.invalid", "unit-only-password"),
                          "send_message"]
    assert smtp.message["From"] == "RetailMetrics <sender@example.invalid>"
    assert smtp.message["To"] == "recipient@example.invalid"
    assert smtp.message["Subject"] == "Test subject"


def test_smtp_missing_configuration_and_transport_failure_are_sanitized():
    for settings in (
        smtp_settings(smtp_live_send_enabled=False),
        smtp_settings(smtp_password=""),
    ):
        try:
            SmtpEmailProvider(settings, smtp_factory=FakeSmtp).send_email(
                Message("admin_test", "email", "recipient@example.invalid", "Test", "<p>Hi</p>")
            )
        except ProviderFailure as exc:
            assert exc.code in {"EMAIL_LIVE_SEND_DISABLED", "EMAIL_PROVIDER_NOT_CONFIGURED"}
            assert "unit-only-password" not in str(exc)
        else:
            raise AssertionError("Unsafe SMTP configuration was accepted")

    class FailingSmtp(FakeSmtp):
        def login(self, username, password):
            raise OSError("response includes credentials and recipient PII")

    try:
        SmtpEmailProvider(smtp_settings(), smtp_factory=FailingSmtp).send_email(
            Message("admin_test", "email", "private@example.invalid", "Test", "<p>Hi</p>")
        )
    except ProviderFailure as exc:
        assert str(exc) == "EMAIL_PROVIDER_REQUEST_FAILED"
        assert "private" not in str(exc) and "password" not in str(exc)
    else:
        raise AssertionError("SMTP failure was not sanitized")


def test_live_email_routes_to_smtp_while_sms_remains_mock(monkeypatch):
    settings = smtp_settings()
    provider = provider_for(settings)
    assert isinstance(provider, RoutedNotificationProvider)
    assert delivery_mode(settings, "email") == "smtp"
    assert delivery_mode(settings, "sms") == "mock"

    email_calls = []

    class FakeEmailProvider:
        def __init__(self, routed_settings):
            assert routed_settings is settings

        def send_email(self, message):
            email_calls.append(message)
            return type("Result", (), {"message_id": "smtp-fake"})()

    import services.notifications.providers as providers
    monkeypatch.setattr(providers, "SmtpEmailProvider", FakeEmailProvider)
    email = Message("order_confirmation", "email", "test@example.invalid", "Order", "<p>Hi</p>")
    assert provider.send_email(email).message_id == "smtp-fake"
    assert email_calls == [email]

    def forbidden_infobip(*args, **kwargs):
        raise AssertionError("Infobip must not be constructed while SMS live sending is disabled")

    monkeypatch.setattr(providers, "InfobipNotificationProvider", forbidden_infobip)
    assert provider.send_sms(Message(
        "order_processing", "sms", "+639171234567", None, "Processing"
    )).message_id.startswith("mock-sms-")


def test_infobip_transport_shape_uses_only_in_memory_fake_transport():
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"messages": [{"messageId": "fake-id"}]})

    settings = Settings(notification_mode="infobip", infobip_live_send_enabled=True,
                        infobip_base_url="https://example.invalid",
                        infobip_email_api_key="email-unit-key",
                        infobip_sms_api_key="sms-unit-key",
                        infobip_email_from="noreply@example.invalid", infobip_sms_sender="RetailMetrics")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = InfobipNotificationProvider(settings, client)
        assert provider.send_email(Message("admin_test", "email", "recipient@example.invalid", "Test", "<p>Hi</p>")).message_id == "fake-id"
        assert provider.send_sms(Message("admin_test", "sms", "+639171234567", None, "Hi")).message_id == "fake-id"
    assert captured[0].url.path == "/email/3/send"
    assert captured[0].headers["content-type"].startswith("multipart/form-data;")
    assert captured[1].url.path == "/sms/3/messages"
    assert captured[1].headers["content-type"] == "application/json"
    assert captured[0].headers["authorization"] == "App email-unit-key"
    assert captured[1].headers["authorization"] == "App sms-unit-key"
    assert "sms-unit-key" not in captured[0].headers["authorization"]
    assert "email-unit-key" not in captured[1].headers["authorization"]


def test_channel_configuration_is_validated_only_when_that_channel_sends():
    email_only = Settings(
        notification_mode="infobip", infobip_live_send_enabled=True,
        infobip_base_url="https://example.invalid",
        infobip_email_api_key="email-only", infobip_email_from="noreply@example.invalid",
        infobip_sms_api_key="", infobip_sms_sender="RetailMetrics",
    )
    provider = InfobipNotificationProvider(email_only, httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"messages": [{"messageId": "email-fake"}]}))))
    try:
        assert provider.send_email(Message("admin_test", "email", "recipient@example.invalid",
                                           "Test", "<p>Hi</p>")).message_id == "email-fake"
        try:
            provider.send_sms(Message("admin_test", "sms", "+639171234567", None, "Hi"))
        except ProviderFailure as exc:
            assert exc.code == "SMS_PROVIDER_NOT_CONFIGURED"
        else:
            raise AssertionError("SMS unexpectedly accepted missing configuration")
    finally:
        provider.client.close()

    sms_only = Settings(
        notification_mode="infobip", infobip_live_send_enabled=True,
        infobip_base_url="https://example.invalid",
        infobip_email_api_key="", infobip_email_from="",
        infobip_sms_api_key="sms-only", infobip_sms_sender="RetailMetrics",
    )
    provider = InfobipNotificationProvider(sms_only, httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"messages": [{"messageId": "sms-fake"}]}))))
    try:
        assert provider.send_sms(Message("admin_test", "sms", "+639171234567", None, "Hi")).message_id == "sms-fake"
        try:
            provider.send_email(Message("admin_test", "email", "recipient@example.invalid",
                                         "Test", "<p>Hi</p>"))
        except ProviderFailure as exc:
            assert exc.code == "EMAIL_PROVIDER_NOT_CONFIGURED"
        else:
            raise AssertionError("Email unexpectedly accepted missing configuration")
    finally:
        provider.client.close()


def test_provider_request_failure_is_sanitized():
    settings = Settings(
        notification_mode="infobip", infobip_live_send_enabled=True,
        infobip_base_url="https://example.invalid",
        infobip_email_api_key="email-secret", infobip_email_from="noreply@example.invalid",
    )
    with httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(500, text="provider response containing private detail"))) as client:
        provider = InfobipNotificationProvider(settings, client)
        try:
            provider.send_email(Message("admin_test", "email", "private@example.invalid",
                                        "Test", "<p>Hi</p>"))
        except ProviderFailure as exc:
            assert exc.code == "PROVIDER_REQUEST_FAILED"
            assert str(exc) == "PROVIDER_REQUEST_FAILED"
            assert "private" not in str(exc) and "email-secret" not in str(exc)
        else:
            raise AssertionError("Provider failure was not reported")


def test_environment_maps_channel_specific_keys(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "unit-signing-key-longer-than-thirty-two-characters")
    monkeypatch.setenv("INFOBIP_EMAIL_API_KEY", "email-env-key")
    monkeypatch.setenv("INFOBIP_SMS_API_KEY", "sms-env-key")
    monkeypatch.setenv("INFOBIP_API_KEY", "obsolete-key-must-be-ignored")
    monkeypatch.setenv("EMAIL_PROVIDER", "smtp")
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-password")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "sender@example.invalid")
    settings = Settings.from_environment()
    assert settings.infobip_email_api_key == "email-env-key"
    assert settings.infobip_sms_api_key == "sms-env-key"
    assert not hasattr(settings, "infobip_api_key")
    assert settings.email_provider == "smtp"
    assert settings.smtp_host == "smtp.gmail.com" and settings.smtp_port == 587
    assert settings.smtp_username == "smtp-user"
    assert settings.smtp_password == "smtp-password"
    assert settings.smtp_from_email == "sender@example.invalid"


def test_admin_config_readiness_returns_booleans_only():
    settings = smtp_settings()
    result = notification_config(None, settings)
    assert result["mode"] == "live"
    assert result["email_provider"] == "smtp" and result["email_live_enabled"]
    assert result["smtp_host_configured"] and result["smtp_password_configured"]
    assert result["sms_provider"] == "brevo" and not result["sms_live_enabled"]
    assert result["sms_delivery_mode"] == "mock"
    assert not result["brevo_api_key_configured"]
    assert "unit-only-password" not in str(result)


def test_infobip_live_gate_prevents_any_transport_creation():
    try:
        InfobipNotificationProvider(Settings(notification_mode="infobip", infobip_live_send_enabled=False))
    except ProviderFailure as exc:
        assert exc.code == "LIVE_SEND_DISABLED"
    else:
        raise AssertionError("Live-send gate was bypassed")


def test_admin_test_endpoint_refuses_other_roles_and_never_returns_secrets(monkeypatch):
    settings = Settings(jwt_secret_key="unit-signing-key-longer-than-thirty-two-characters",
                        notification_mode="mock")
    users = FakeUserRepository()
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(notification_router)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_user_repository] = lambda: users

    import services.notifications.providers as providers
    monkeypatch.setattr(providers, "InfobipNotificationProvider",
                        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Live provider selected")))
    with TestClient(app) as client:
        tokens = {}
        for role in (Role.ADMIN, Role.OPERATIONS_STAFF, Role.ANALYST):
            name = role.value
            created = users.create_analyst(name, f"{name}@example.com", "unused")
            users._save(replace(created, role=role))
            # Reuse the tested staff signing/authentication path.
            from core.security import create_access_token
            tokens[role] = create_access_token(users.get_by_id(created.app_user_id), settings)[0]
        payload = {"channel": "email", "recipient": "test@example.com"}
        assert client.post("/admin/notifications/test", json=payload).status_code == 401
        customer_token = jwt.encode({"sub": "123", "type": "customer_access", "ver": 1},
                                    settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
        assert client.post("/admin/notifications/test",
                           headers={"Authorization": f"Bearer {customer_token}"}, json=payload).status_code == 401
        for role in (Role.OPERATIONS_STAFF, Role.ANALYST):
            assert client.post("/admin/notifications/test", headers={"Authorization": f"Bearer {tokens[role]}"}, json=payload).status_code == 403
        admin = {"Authorization": f"Bearer {tokens[Role.ADMIN]}"}
        response = client.post("/admin/notifications/test", headers=admin, json=payload)
        assert response.status_code == 200 and response.json()["status"] == "simulated_success"
        assert "unit-only" not in str(response.json())
        assert client.post("/admin/notifications/test", headers=admin,
                           json={"channel": "sms", "recipient": "09171234567"}).status_code == 200
        assert client.post("/admin/notifications/test", headers=admin,
                           json={"channel": "sms", "recipient": "bad"}).status_code == 422
