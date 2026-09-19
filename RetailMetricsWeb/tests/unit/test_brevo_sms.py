from __future__ import annotations

from dataclasses import replace

import httpx
import pytest

from core.config import Settings
from services.notifications.outbox import render_message
from services.notifications.phone import normalize_ph_mobile
from services.notifications.providers import (
    BrevoSmsProvider, Message, ProviderFailure, delivery_mode, provider_for,
)
from tests.unit.test_order_confirmation_email import OrderCursor, RefundCursor


def settings(**changes):
    base = Settings(notification_mode="live", sms_provider="brevo",
                    brevo_api_key="test-only-secret", brevo_sms_sender="RetailMetrics",
                    brevo_sms_live_send_enabled=True)
    return replace(base, **changes)


def test_brevo_settings_load_from_environment(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "unit-signing-key-longer-than-thirty-two-characters")
    monkeypatch.setenv("SMS_PROVIDER", "brevo")
    monkeypatch.setenv("BREVO_API_KEY", "test-only-secret")
    monkeypatch.setenv("BREVO_SMS_SENDER", "RetailMetrics")
    monkeypatch.setenv("BREVO_SMS_LIVE_SEND_ENABLED", "true")
    loaded = Settings.from_environment()
    assert (loaded.sms_provider, loaded.brevo_api_key, loaded.brevo_sms_sender,
            loaded.brevo_sms_live_send_enabled) == ("brevo", "test-only-secret", "RetailMetrics", True)
    assert "test-only-secret" not in repr(loaded)


@pytest.mark.parametrize("phone", ["09171234567", "639171234567", "+639171234567"])
def test_brevo_payload_and_ph_normalization_use_mock_transport(phone):
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(201, json={"messageId": 123})

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result = BrevoSmsProvider(settings(), client).send_sms(
            Message("order_confirmation", "sms", phone, None, "RetailMetrics test"))
    assert result.message_id == "123"
    request = requests[0]
    assert str(request.url) == "https://api.brevo.com/v3/transactionalSMS/send"
    assert request.headers["api-key"] == "test-only-secret"
    assert request.headers["content-type"] == "application/json"
    assert request.headers["accept"] == "application/json"
    assert request.content == b'{"sender":"RetailMetrics","recipient":"+639171234567","content":"RetailMetrics test","type":"transactional"}'


def test_invalid_ph_numbers_fail_without_network():
    for number in ("9171234567", "+14155550123", "0917123456", "+63+9171234567"):
        assert normalize_ph_mobile(number) is None
        with httpx.Client(transport=httpx.MockTransport(
            lambda request: (_ for _ in ()).throw(AssertionError("network called")))) as client:
            with pytest.raises(ProviderFailure, match="INVALID_SMS_RECIPIENT"):
                BrevoSmsProvider(settings(), client).send_sms(Message("admin_test", "sms", number, None, "Hi"))


def test_brevo_two_gates_and_provider_selection_are_safe(monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("No HTTP request expected")

    monkeypatch.setattr(httpx.Client, "post", no_network)
    message = Message("admin_test", "sms", "09171234567", None, "Hi")
    for options in (dict(notification_mode="mock"), dict(brevo_sms_live_send_enabled=False),
                    dict(sms_provider="mock")):
        current = settings(**options)
        assert delivery_mode(current, "sms") == "mock"
        assert provider_for(current).send_sms(message).message_id.startswith("mock-sms-")
    with pytest.raises(ProviderFailure, match="SMS_LIVE_SEND_DISABLED"):
        BrevoSmsProvider(settings(brevo_sms_live_send_enabled=False)).send_sms(message)


def test_brevo_missing_config_and_provider_errors_are_sanitized(caplog):
    message = Message("admin_test", "sms", "09171234567", None, "Hi")
    for changes in (dict(brevo_api_key=""), dict(brevo_sms_sender="")):
        with pytest.raises(ProviderFailure, match="SMS_PROVIDER_NOT_CONFIGURED"):
            BrevoSmsProvider(settings(**changes)).send_sms(message)
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(401, text="secret test-only-secret recipient 09171234567"))) as client:
        with pytest.raises(ProviderFailure) as failure:
            BrevoSmsProvider(settings(), client).send_sms(message)
    assert str(failure.value) == "SMS_PROVIDER_REQUEST_FAILED"
    assert failure.value.__cause__ is None
    assert "test-only-secret" not in caplog.text


def test_brevo_order_and_refund_sms_wording():
    expected = {
        "order_confirmation": "received and is Pending",
        "order_processing": "being processed",
        "order_ready_shipped": "Ready / Shipped",
        "order_delivered": "marked Delivered",
        "order_cancelled": "was cancelled",
    }
    for event, phrase in expected.items():
        row = {"event_type": event, "channel": "sms", "order_id": 4312,
               "recipient_address": "+639171234567"}
        assert phrase in render_message(OrderCursor(), row).body
    for event in ("refund_request_submitted", "refund_rejected", "refund_processed"):
        row = {"event_type": event, "channel": "sms", "refund_request_id": 77,
               "recipient_address": "+639171234567"}
        body = render_message(RefundCursor(event), row).body
        assert "Refund request #77" in body
        if event == "refund_processed":
            assert "has been Refunded" in body and "processed" not in body.lower()
