from __future__ import annotations

import re

from email_validator import EmailNotValidError, validate_email
import streamlit as st

from frontend.api_client import APIClient, APIError
from frontend.ui import data_page_header, readiness_checklist, section_label, show_api_error, summary_strip


def valid_email_destination(value: str) -> bool:
    try:
        validate_email(value.strip(), check_deliverability=False)
        return True
    except EmailNotValidError:
        return False


def valid_sms_destination(value: str) -> bool:
    raw = value.strip()
    if re.search(r"[^+0-9 .()-]", raw) or raw.count("+") > 1 or ("+" in raw and not raw.startswith("+")):
        return False
    compact = re.sub(r"[ .()-]", "", raw)
    return bool(re.fullmatch(r"09\d{9}", compact) or re.fullmatch(r"639\d{9}", compact)
                or re.fullmatch(r"\+639\d{9}", compact))


def channel_ready(config: dict, channel: str) -> bool:
    if channel == "email":
        provider = config.get("email_provider", "mock")
        if provider == "mock":
            return True
        if provider == "smtp":
            return bool(config.get("email_live_enabled") and config.get("smtp_host_configured")
                        and config.get("smtp_port_configured") and config.get("smtp_username_configured")
                        and config.get("smtp_password_configured") and config.get("smtp_sender_configured"))
        return bool(config.get("email_live_enabled") and config.get("base_url_configured")
                    and config.get("email_api_key_configured") and config.get("email_sender_configured"))
    provider = config.get("sms_provider", "mock")
    if provider == "mock":
        return True
    if provider == "android_gateway":
        return bool(config.get("sms_live_enabled") and config.get("sms_gateway_url_configured")
                    and config.get("sms_gateway_username_configured")
                    and config.get("sms_gateway_password_configured"))
    return bool(config.get("sms_live_enabled") and config.get("brevo_api_key_configured")
                and config.get("brevo_sms_sender_configured"))


def send_disabled(config: dict, channel: str, recipient: str, confirmed: bool) -> bool:
    valid = valid_email_destination(recipient) if channel == "email" else valid_sms_destination(recipient)
    if not valid:
        return True
    mode = config.get("email_provider", "mock") if channel == "email" else config.get("sms_delivery_mode", "mock")
    return False if mode == "mock" else not (channel_ready(config, channel) and confirmed)


def _readiness(config: dict, channel: str) -> list[tuple[str, bool]]:
    if channel == "email":
        return [
            ("Live sending", bool(config.get("email_live_enabled"))),
            ("SMTP host and port", bool(config.get("smtp_host_configured") and config.get("smtp_port_configured"))),
            ("SMTP credentials", bool(config.get("smtp_username_configured") and config.get("smtp_password_configured"))),
            ("Sender address", bool(config.get("smtp_sender_configured"))),
        ]
    if config.get("sms_provider") == "android_gateway":
        return [
            ("Gateway URL", bool(config.get("sms_gateway_url_configured"))),
            ("Gateway username", bool(config.get("sms_gateway_username_configured"))),
            ("Gateway password", bool(config.get("sms_gateway_password_configured"))),
            ("Live sending", bool(config.get("sms_live_enabled"))),
        ]
    if config.get("sms_provider") == "brevo":
        return [
            ("API key", bool(config.get("brevo_api_key_configured"))),
            ("Sender", bool(config.get("brevo_sms_sender_configured"))),
            ("Live sending", bool(config.get("sms_live_enabled"))),
        ]
    return [("Simulation mode", True)]


def _test_panel(client: APIClient, config: dict, channel: str) -> None:
    is_email = channel == "email"
    provider = config.get("email_provider", "mock") if is_email else config.get("sms_provider", "mock")
    live_mode = (provider != "mock" and config.get("mode") != "mock") if is_email else config.get("sms_delivery_mode") in {"brevo", "android_gateway"}
    title = "Email delivery" if is_email else "SMS delivery"
    provider_label = "Android SMS Gateway" if provider == "android_gateway" else str(provider).upper()
    with st.container(border=True):
        st.subheader(title)
        st.caption(f"Provider · {provider_label}")
        readiness_checklist(tuple(_readiness(config, channel)))
        ready = channel_ready(config, channel)
        if ready:
            st.success("Ready for an intentional test.")
        else:
            st.warning("Configuration needs attention before a live test.")
        recipient = st.text_input("Test email address" if is_email else "Test mobile number",
                                  key=f"notification_recipient_{channel}")
        confirmed = st.checkbox(
            "I confirm this intentional live email send." if is_email else "I confirm this intentional live SMS send.",
            key=f"notification_live_confirm_{channel}",
        ) if live_mode else False
        if live_mode and not channel_ready(config, channel):
            st.warning(f"{channel.upper()} sending is not fully configured.")
        elif not live_mode:
            st.info("This test is simulated; no external message will be sent.")
        label = f"Send Test {'Email' if is_email else 'SMS'}" if live_mode else f"Simulate Test {'Email' if is_email else 'SMS'}"
        sent = st.button(label, key=f"notification_send_{channel}",
                         disabled=send_disabled(config, channel, recipient, confirmed),
                         type="primary", use_container_width=True)
    if not sent:
        return
    try:
        outcome = client.post("/admin/notifications/test", {
            "channel": channel, "recipient": recipient, "confirm_live": confirmed,
        })
        if outcome["status"] == "failed":
            st.warning(outcome["message"])
        else:
            st.success(outcome["message"])
    except APIError as exc:
        show_api_error(exc)


def render(client: APIClient) -> None:
    data_page_header("Notification Test", "Validate delivery configuration through explicit Admin-only test actions.",
                     "notification_test")
    try:
        config = client.get("/admin/notifications/config")
    except APIError as exc:
        show_api_error(exc)
        return
    email_provider = config.get("email_provider", "mock")
    sms_provider = config.get("sms_provider", "mock")
    summary_strip((("System mode", str(config.get("mode", "mock")).title()),
                   ("Email", str(email_provider).upper()),
                   ("SMS", "Android Gateway" if sms_provider == "android_gateway" else str(sms_provider).title())))
    section_label("Channel readiness and controlled tests")
    email_column, sms_column = st.columns(2, gap="large")
    with email_column:
        _test_panel(client, config, "email")
    with sms_column:
        _test_panel(client, config, "sms")
