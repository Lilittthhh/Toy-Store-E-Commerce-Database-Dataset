from __future__ import annotations

import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from typing import Protocol

import httpx

from core.config import Settings
from services.notifications.phone import normalize_ph_mobile


@dataclass(frozen=True)
class Message:
    event_type: str
    channel: str
    recipient: str
    subject: str | None
    body: str
    plain_body: str | None = None


@dataclass(frozen=True)
class DeliveryResult:
    message_id: str


class NotificationProvider(Protocol):
    def send_email(self, message: Message) -> DeliveryResult: ...
    def send_sms(self, message: Message) -> DeliveryResult: ...


class MockNotificationProvider:
    def __init__(self) -> None:
        self.messages: list[Message] = []

    def send_email(self, message: Message) -> DeliveryResult:
        self.messages.append(message)
        return DeliveryResult(f"mock-email-{len(self.messages)}")

    def send_sms(self, message: Message) -> DeliveryResult:
        self.messages.append(message)
        return DeliveryResult(f"mock-sms-{len(self.messages)}")


class ProviderFailure(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class SmtpEmailProvider:
    """STARTTLS SMTP transport. Configuration and provider errors stay sanitized."""

    def __init__(self, settings: Settings, smtp_factory=None) -> None:
        self.settings = settings
        self.smtp_factory = smtp_factory or smtplib.SMTP

    def send_email(self, message: Message) -> DeliveryResult:
        if not self.settings.smtp_live_send_enabled:
            raise ProviderFailure("EMAIL_LIVE_SEND_DISABLED")
        if not all((self.settings.smtp_host, self.settings.smtp_port,
                    self.settings.smtp_username, self.settings.smtp_password,
                    self.settings.smtp_from_email)):
            raise ProviderFailure("EMAIL_PROVIDER_NOT_CONFIGURED")

        email = EmailMessage()
        email["From"] = formataddr((self.settings.smtp_from_name,
                                    self.settings.smtp_from_email))
        email["To"] = message.recipient
        email["Subject"] = message.subject or "RetailMetrics update"
        email.set_content(message.plain_body or "This RetailMetrics notification requires an HTML-capable email client.")
        email.add_alternative(message.body, subtype="html")
        try:
            with self.smtp_factory(
                self.settings.smtp_host, self.settings.smtp_port, timeout=10
            ) as smtp:
                smtp.ehlo()
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
                smtp.login(self.settings.smtp_username, self.settings.smtp_password)
                smtp.send_message(email)
        except (smtplib.SMTPException, OSError) as exc:
            raise ProviderFailure("EMAIL_PROVIDER_REQUEST_FAILED") from exc
        return DeliveryResult("smtp-accepted")

    def send_sms(self, message: Message) -> DeliveryResult:
        raise ProviderFailure("SMS_PROVIDER_NOT_CONFIGURED")


class InfobipNotificationProvider:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        if not settings.infobip_live_send_enabled:
            raise ProviderFailure("LIVE_SEND_DISABLED")
        if not settings.infobip_base_url:
            raise ProviderFailure("PROVIDER_NOT_CONFIGURED")
        if not settings.infobip_base_url.startswith("https://"):
            raise ProviderFailure("INVALID_BASE_URL")
        self.settings = settings
        self.client = client

    def _post(self, path: str, api_key: str, **kwargs) -> DeliveryResult:
        try:
            url = self.settings.infobip_base_url.rstrip("/") + path
            headers = {"Authorization": f"App {api_key}", "Accept": "application/json"}
            if self.client is None:
                with httpx.Client(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
                    response = client.post(url, headers=headers, **kwargs)
            else:
                response = self.client.post(url, headers=headers, **kwargs)
            response.raise_for_status()
            data = response.json()
            messages = data.get("messages") or []
            identifier = messages[0].get("messageId") if messages else data.get("bulkId")
            return DeliveryResult(str(identifier or "accepted"))
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            # Raw provider responses can contain PII and are never propagated.
            raise ProviderFailure("PROVIDER_REQUEST_FAILED") from exc

    def send_email(self, message: Message) -> DeliveryResult:
        if not self.settings.infobip_email_api_key or not self.settings.infobip_email_from:
            raise ProviderFailure("EMAIL_PROVIDER_NOT_CONFIGURED")
        # Infobip's Email v3 endpoint expects multipart/form-data, even without attachments.
        fields = {
            "from": self.settings.infobip_email_from,
            "fromName": self.settings.infobip_email_from_name,
            "to": message.recipient,
            "subject": message.subject or "RetailMetrics update",
            "html": message.body,
        }
        return self._post(
            "/email/3/send",
            api_key=self.settings.infobip_email_api_key,
            files={key: (None, value) for key, value in fields.items()},
        )

    def send_sms(self, message: Message) -> DeliveryResult:
        if not self.settings.infobip_sms_api_key or not self.settings.infobip_sms_sender:
            raise ProviderFailure("SMS_PROVIDER_NOT_CONFIGURED")
        return self._post("/sms/3/messages", api_key=self.settings.infobip_sms_api_key, json={"messages": [{
            "sender": self.settings.infobip_sms_sender,
            "destinations": [{"to": message.recipient}],
            "content": {"text": message.body},
        }]})


class BrevoSmsProvider:
    """Transactional SMS transport; direct use is guarded as well as routed use."""

    URL = "https://api.brevo.com/v3/transactionalSMS/send"

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.client = client

    def send_sms(self, message: Message) -> DeliveryResult:
        if self.settings.notification_mode != "live" or not self.settings.brevo_sms_live_send_enabled:
            raise ProviderFailure("SMS_LIVE_SEND_DISABLED")
        if not self.settings.brevo_api_key or not self.settings.brevo_sms_sender:
            raise ProviderFailure("SMS_PROVIDER_NOT_CONFIGURED")
        recipient = normalize_ph_mobile(message.recipient)
        if not recipient:
            raise ProviderFailure("INVALID_SMS_RECIPIENT")
        headers = {
            "api-key": self.settings.brevo_api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {
            "sender": self.settings.brevo_sms_sender,
            "recipient": recipient,
            "content": message.body,
            "type": "transactional",
        }
        try:
            if self.client is None:
                with httpx.Client(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
                    response = client.post(self.URL, headers=headers, json=payload)
            else:
                response = self.client.post(self.URL, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            identifier = data.get("messageId") if isinstance(data, dict) else None
            return DeliveryResult(str(identifier or "accepted"))
        except (httpx.HTTPError, ValueError, TypeError):
            # Never chain provider errors: responses may contain recipient PII or secrets.
            raise ProviderFailure("SMS_PROVIDER_REQUEST_FAILED") from None


class RoutedNotificationProvider:
    """Route channels independently while retaining one outbox provider interface."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.mock = MockNotificationProvider()

    def send_email(self, message: Message) -> DeliveryResult:
        if self.settings.email_provider == "mock":
            return self.mock.send_email(message)
        if self.settings.email_provider == "smtp":
            return SmtpEmailProvider(self.settings).send_email(message)
        return InfobipNotificationProvider(self.settings).send_email(message)

    def send_sms(self, message: Message) -> DeliveryResult:
        if delivery_mode(self.settings, "sms") == "mock":
            return self.mock.send_sms(message)
        return BrevoSmsProvider(self.settings).send_sms(message)


def delivery_mode(settings: Settings, channel: str) -> str:
    if settings.notification_mode == "mock":
        return "mock"
    if channel == "email":
        return settings.email_provider
    return "brevo" if (settings.notification_mode == "live"
                       and settings.sms_provider == "brevo"
                       and settings.brevo_sms_live_send_enabled) else "mock"


def provider_for(settings: Settings) -> NotificationProvider:
    if settings.notification_mode == "mock":
        return MockNotificationProvider()
    if settings.notification_mode in {"live", "infobip"}:
        return RoutedNotificationProvider(settings)
    raise RuntimeError("Unsupported notification mode")
