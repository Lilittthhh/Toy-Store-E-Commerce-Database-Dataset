from __future__ import annotations

import re

from email_validator import EmailNotValidError, validate_email
import streamlit as st

from frontend.api_client import APIClient, APIError
from frontend.ui import data_page_header, show_api_error


def valid_email_destination(value: str) -> bool:
    try:
        validate_email(value.strip(), check_deliverability=False)
        return True
    except EmailNotValidError:
        return False


def valid_sms_destination(value: str) -> bool:
    raw = value.strip()
    if re.search(r"[^+0-9 .()-]", raw) or raw.count("+") > 1 or (
        "+" in raw and not raw.startswith("+")
    ):
        return False
    compact = re.sub(r"[ .()-]", "", raw)
    return bool(
        re.fullmatch(r"09\d{9}", compact)
        or re.fullmatch(r"639\d{9}", compact)
        or re.fullmatch(r"\+639\d{9}", compact)
    )


def channel_ready(config: dict, channel: str) -> bool:
    if channel == "email":
        provider = config.get("email_provider", "mock")
        if provider == "mock":
            return True
        if provider == "smtp":
            return bool(
                config.get("email_live_enabled")
                and config.get("smtp_host_configured")
                and config.get("smtp_port_configured")
                and config.get("smtp_username_configured")
                and config.get("smtp_password_configured")
                and config.get("smtp_sender_configured")
            )
        return bool(
            config.get("email_live_enabled")
            and config.get("base_url_configured")
            and config.get("email_api_key_configured")
            and config.get("email_sender_configured")
        )
    provider = config.get("sms_provider", "mock")
    if provider == "mock":
        return True
    return bool(
        config.get("sms_live_enabled")
        and config.get("brevo_api_key_configured")
        and config.get("brevo_sms_sender_configured")
    )


def send_disabled(config: dict, channel: str, recipient: str, confirmed: bool) -> bool:
    destination_valid = (
        valid_email_destination(recipient)
        if channel == "email"
        else valid_sms_destination(recipient)
    )
    if not destination_valid:
        return True
    provider = config.get("email_provider", "mock") if channel == "email" else config.get("sms_delivery_mode", "mock")
    if provider == "mock":
        return False
    return not (channel_ready(config, channel) and confirmed)


def _yes_no(value: bool) -> str:
    return "Yes" if value else "No"


def render(client: APIClient) -> None:
    data_page_header(
        "Notification Test",
        "Admin-only, explicit email/SMS provider check.",
        "notification_test",
    )
    try:
        config = client.get("/admin/notifications/config")
    except APIError as exc:
        show_api_error(exc)
        return

    email_provider = config.get("email_provider", "mock")
    sms_provider = config.get("sms_provider", "mock")
    if config.get("mode") == "mock":
        st.info("Current delivery mode: Mock — no network message is sent.")
    else:
        email_state = "live enabled" if config.get("email_live_enabled") else "live disabled"
        st.info(f"Email provider: {email_provider.upper()} ({email_state})")
        if sms_provider == "mock":
            st.info("SMS provider: Mock — live SMS is currently unavailable/disabled.")
        else:
            sms_state = "live enabled" if config.get("sms_live_enabled") else "live disabled"
            st.info(f"SMS provider: {sms_provider.title()} ({sms_state})")

    readiness = {
        "SMTP email live enabled": config.get("email_live_enabled", False),
        "SMTP host configured": config.get("smtp_host_configured", False),
        "SMTP port configured": config.get("smtp_port_configured", False),
        "SMTP username configured": config.get("smtp_username_configured", False),
        "SMTP password configured": config.get("smtp_password_configured", False),
        "SMTP sender configured": config.get("smtp_sender_configured", False),
        "SMS provider: Brevo": sms_provider == "brevo",
        "Brevo API key configured": config.get("brevo_api_key_configured", False),
        "Brevo live sending enabled": config.get("sms_live_enabled", False),
        "Brevo sender configured": config.get("brevo_sms_sender_configured", False),
    }
    st.markdown("#### Configuration readiness")
    st.table(
        [{"Setting": label, "Ready": _yes_no(bool(value))} for label, value in readiness.items()]
    )

    for channel, label in (("email", "Send Test Email"), ("sms", "Send Test SMS")):
        provider = email_provider if channel == "email" else sms_provider
        if channel == "email":
            is_live = config.get("email_provider", "mock") != "mock" and config.get("mode") != "mock"
        else:
            is_live = config.get("sms_delivery_mode") == "brevo"
        with st.container(border=True):
            st.markdown(f"#### {'Email' if channel == 'email' else 'SMS'} test")
            recipient = st.text_input(
                "Test email address" if channel == "email" else "Test mobile number",
                key=f"notification_recipient_{channel}",
            )
            confirmed = (
                st.checkbox(
                    "I confirm this intentional live email send."
                    if channel == "email"
                    else "I confirm this intentional live SMS send.",
                    key=f"notification_live_confirm_{channel}",
                )
                if is_live
                else False
            )
            if is_live and not channel_ready(config, channel):
                st.caption(f"{channel.upper()} sending is not fully configured.")
            if channel == "sms" and provider == "mock":
                st.caption("Live SMS is disabled. This action remains a safe simulation.")
            sent = st.button(
                label if is_live else label.replace("Send", "Simulate"),
                key=f"notification_send_{channel}",
                disabled=send_disabled(config, channel, recipient, confirmed),
                type="primary",
            )
        if sent:
            try:
                outcome = client.post(
                    "/admin/notifications/test",
                    {
                        "channel": channel,
                        "recipient": recipient,
                        "confirm_live": confirmed,
                    },
                )
                if outcome["status"] == "failed":
                    st.warning(outcome["message"])
                else:
                    st.success(outcome["message"])
            except APIError as exc:
                show_api_error(exc)
