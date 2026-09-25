from __future__ import annotations

import base64
import json
from dataclasses import replace

import httpx
import pytest

from api.routers.notifications import notification_config
from core.config import Settings
from services.notifications.providers import (
    AndroidSmsGatewayProvider, DeliveryResult, Message, ProviderFailure,
    delivery_mode, gateway_url_ready, provider_for,
)


def gateway_settings(**changes):
    values = Settings(
        notification_mode="live", sms_provider="android_gateway",
        sms_gateway_url="https://api.sms-gate.app/3rdparty/v1/message",
        sms_gateway_username="unit-user", sms_gateway_password="unit-secret",
        sms_gateway_live_send_enabled=True,
    )
    return replace(values, **changes)


def sms(recipient="09171234567"):
    return Message("admin_test", "sms", recipient, None, "RetailMetrics test")


def test_gateway_settings_load_and_hide_credentials(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "unit-signing-key-longer-than-thirty-two-characters")
    monkeypatch.setenv("SMS_PROVIDER", "android_gateway")
    monkeypatch.setenv("SMS_GATEWAY_URL", "https://api.sms-gate.app/3rdparty/v1/message")
    monkeypatch.setenv("SMS_GATEWAY_USERNAME", "unit-user")
    monkeypatch.setenv("SMS_GATEWAY_PASSWORD", "unit-secret")
    monkeypatch.setenv("SMS_GATEWAY_LIVE_SEND_ENABLED", "true")
    result = Settings.from_environment()
    assert result.sms_provider == "android_gateway"
    assert result.sms_gateway_username == "unit-user"
    assert result.sms_gateway_password == "unit-secret"
    assert result.sms_gateway_live_send_enabled
    assert "unit-user" not in repr(result) and "unit-secret" not in repr(result)


@pytest.mark.parametrize("number", ["09171234567", "639171234567", "+639171234567"])
def test_gateway_url_basic_auth_payload_and_phone_normalization(number):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(202, json={"id": "gateway-unit-id"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = AndroidSmsGatewayProvider(gateway_settings(), client).send_sms(sms(number))
    assert result.message_id == "gateway-unit-id"
    request = seen[0]
    assert request.method == "POST"
    assert str(request.url) == "https://api.sms-gate.app/3rdparty/v1/message"
    assert request.headers["authorization"] == "Basic " + base64.b64encode(b"unit-user:unit-secret").decode("ascii")
    assert json.loads(request.content) == {
        "textMessage": {"text": "RetailMetrics test"},
        "phoneNumbers": ["+639171234567"],
    }


def test_gateway_disabled_and_mock_routes_never_open_transport(monkeypatch):
    monkeypatch.setattr(httpx.Client, "post", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("network call")))
    for changes in (
        {"notification_mode": "mock"},
        {"sms_gateway_live_send_enabled": False},
        {"sms_provider": "mock"},
    ):
        settings = gateway_settings(**changes)
        assert delivery_mode(settings, "sms") == "mock"
        assert provider_for(settings).send_sms(sms()).message_id.startswith("mock-sms-")
    with pytest.raises(ProviderFailure, match="SMS_LIVE_SEND_DISABLED"):
        AndroidSmsGatewayProvider(gateway_settings(sms_gateway_live_send_enabled=False)).send_sms(sms())


def test_live_provider_routing_preserves_brevo_option(monkeypatch):
    import services.notifications.providers as providers

    calls = []

    class FakeGateway:
        def __init__(self, settings):
            calls.append(("gateway", settings.sms_provider))

        def send_sms(self, message):
            return DeliveryResult("gateway-fake")

    class FakeBrevo:
        def __init__(self, settings):
            calls.append(("brevo", settings.sms_provider))

        def send_sms(self, message):
            return DeliveryResult("brevo-fake")

    monkeypatch.setattr(providers, "AndroidSmsGatewayProvider", FakeGateway)
    monkeypatch.setattr(providers, "BrevoSmsProvider", FakeBrevo)
    assert provider_for(gateway_settings()).send_sms(sms()).message_id == "gateway-fake"
    brevo = gateway_settings(sms_provider="brevo", brevo_sms_live_send_enabled=True)
    assert provider_for(brevo).send_sms(sms()).message_id == "brevo-fake"
    assert calls == [("gateway", "android_gateway"), ("brevo", "brevo")]


def test_gateway_missing_credentials_invalid_phone_and_errors_are_sanitized(caplog):
    for changes in ({"sms_gateway_username": ""}, {"sms_gateway_password": ""}):
        with pytest.raises(ProviderFailure, match="SMS_PROVIDER_NOT_CONFIGURED"):
            AndroidSmsGatewayProvider(gateway_settings(**changes)).send_sms(sms())
    with pytest.raises(ProviderFailure, match="INVALID_SMS_RECIPIENT"):
        AndroidSmsGatewayProvider(gateway_settings()).send_sms(sms("123"))
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(
        403, text="unit-secret and recipient 09171234567"))) as client:
        with pytest.raises(ProviderFailure) as failure:
            AndroidSmsGatewayProvider(gateway_settings(), client).send_sms(sms())
    assert str(failure.value) == "SMS_PROVIDER_REQUEST_FAILED"
    assert failure.value.__cause__ is None
    assert "unit-secret" not in caplog.text


def test_gateway_refuses_unexpected_hosts_before_basic_auth_is_sent():
    assert gateway_url_ready("https://api.sms-gate.app/3rdparty/v1/message")
    assert not gateway_url_ready("https://api.sms-gate.app.evil/3rdparty/v1/message")
    with pytest.raises(ProviderFailure, match="INVALID_SMS_GATEWAY_URL"):
        AndroidSmsGatewayProvider(gateway_settings(
            sms_gateway_url="https://api.sms-gate.app.evil/3rdparty/v1/message"
        )).send_sms(sms())


def test_gateway_config_is_admin_safe_projection():
    config = notification_config(None, gateway_settings())
    assert config["sms_provider"] == config["sms_delivery_mode"] == "android_gateway"
    assert config["sms_live_enabled"]
    assert config["sms_gateway_url_configured"]
    assert config["sms_gateway_username_configured"]
    assert config["sms_gateway_password_configured"]
    assert "unit-user" not in str(config) and "unit-secret" not in str(config)
