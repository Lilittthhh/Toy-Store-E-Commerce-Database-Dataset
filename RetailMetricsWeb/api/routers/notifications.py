"""Safe delivery-status projection and explicit Admin-only test sends."""
from __future__ import annotations

from typing import Literal

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from psycopg2.extras import RealDictCursor

from api.schemas.auth import StrictRequest
from core.config import Settings, get_settings
from core.dependencies import require_customer, require_roles
from core.models import AppUser, CustomerAccount, Role
from db.connection import get_db_connection
from services.notifications.phone import normalize_ph_mobile
from services.notifications.providers import Message, ProviderFailure, delivery_mode, provider_for


router = APIRouter(tags=["Notifications"])


class TestNotificationRequest(StrictRequest):
    channel: Literal["email", "sms"]
    recipient: str = Field(min_length=3, max_length=254)
    confirm_live: bool = False


@router.get("/admin/notifications/config")
def notification_config(_: AppUser = Depends(require_roles(Role.ADMIN)), settings: Settings = Depends(get_settings)):
    master_live = settings.notification_mode != "mock"
    email_mode = delivery_mode(settings, "email")
    sms_mode = delivery_mode(settings, "sms")
    email_live = master_live and (
        (email_mode == "smtp" and settings.smtp_live_send_enabled)
        or (email_mode == "infobip" and settings.infobip_live_send_enabled)
    )
    sms_live = sms_mode == "brevo"
    return {
        "mode": settings.notification_mode,
        "email_provider": email_mode,
        "email_live_enabled": email_live,
        "smtp_host_configured": bool(settings.smtp_host),
        "smtp_port_configured": bool(settings.smtp_port),
        "smtp_username_configured": bool(settings.smtp_username),
        "smtp_password_configured": bool(settings.smtp_password),
        "smtp_sender_configured": bool(settings.smtp_from_email),
        "sms_provider": settings.sms_provider,
        "sms_delivery_mode": sms_mode,
        "sms_live_enabled": sms_live,
        "brevo_api_key_configured": bool(settings.brevo_api_key),
        "brevo_sms_sender_configured": bool(settings.brevo_sms_sender),
    }


@router.post("/admin/notifications/test")
def test_notification(request: TestNotificationRequest, _: AppUser = Depends(require_roles(Role.ADMIN)),
                      settings: Settings = Depends(get_settings)):
    channel_mode = delivery_mode(settings, request.channel)
    if channel_mode != "mock" and not request.confirm_live:
        raise HTTPException(status_code=400, detail="Confirm the live notification send explicitly.")
    try:
        if request.channel == "email":
            recipient = validate_email(request.recipient.strip(), check_deliverability=False).normalized
            message = Message("admin_test", "email", recipient, "RetailMetrics Test Email",
                              "<html><body><h1>RetailMetrics</h1><p>This is an intentional test notification.</p></body></html>")
        else:
            recipient = normalize_ph_mobile(request.recipient)
            if not recipient:
                raise HTTPException(status_code=422, detail="Enter a valid mobile number.")
            message = Message("admin_test", "sms", recipient, None,
                              "RetailMetrics: This is an intentional test notification.")
        provider = provider_for(settings)
        if request.channel == "email":
            provider.send_email(message)
        else:
            provider.send_sms(message)
    except EmailNotValidError as exc:
        raise HTTPException(status_code=422, detail="Enter a valid email address.") from exc
    except ProviderFailure:
        return {"status": "failed", "mode": channel_mode,
                "message": "The test notification could not be sent."}
    simulated = channel_mode == "mock"
    return {"status": "simulated_success" if simulated else "sent",
            "mode": channel_mode,
            "message": "Test notification prepared." if simulated else "Test notification submitted."}


@router.get("/customer/orders/{order_id}/notifications")
def customer_order_notification_status(order_id: int, customer: CustomerAccount = Depends(require_customer),
                                       conn=Depends(get_db_connection), settings: Settings = Depends(get_settings)):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""SELECT 1 FROM public.orders WHERE order_id=%s AND customer_account_id=%s
                       AND record_origin='customer'""", (order_id, customer.customer_account_id))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Order not found.")
        cur.execute("""SELECT event_type,channel,delivery_status FROM public.notification_outbox
                       WHERE order_id=%s AND customer_account_id=%s ORDER BY notification_id""",
                    (order_id, customer.customer_account_id))
        return {"mode": settings.notification_mode,
                "email_mode": delivery_mode(settings, "email"),
                "sms_mode": delivery_mode(settings, "sms"),
                "items": [dict(row) for row in cur.fetchall()]}
