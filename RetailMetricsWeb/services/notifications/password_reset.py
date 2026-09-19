from __future__ import annotations

from html import escape

from core.config import Settings
from services.notifications.providers import Message


def password_reset_message(
    recipient: str,
    reset_token: str,
    lifetime_minutes: int,
    account_domain: str,
) -> Message:
    safe_token = escape(reset_token)
    safe_domain = escape(account_domain)
    body = f"""<!doctype html>
<html><body style="font-family:Arial,sans-serif;color:#0b2746;background:#f6f8f8;padding:24px">
  <div style="max-width:560px;margin:auto;background:#fff;border:1px solid #dce5e5;border-radius:12px;padding:28px">
    <div style="color:#0f766e;font-weight:700;font-size:20px">RetailMetrics</div>
    <div style="color:#60758a;margin-bottom:24px">Toy Store Intelligence</div>
    <h1 style="font-size:24px;margin:0 0 12px">Password reset</h1>
    <p>A password reset was requested for your RetailMetrics {safe_domain} account.</p>
    <p>Enter this temporary reset code in the Reset Password form:</p>
    <div style="font-family:monospace;overflow-wrap:anywhere;background:#eef7f6;border:1px solid #b9ded9;border-radius:8px;padding:14px">{safe_token}</div>
    <p>This code expires in {int(lifetime_minutes)} minutes. If you did not request a reset, you can ignore this email.</p>
    <p>RetailMetrics will never ask you to send your password by email.</p>
  </div>
</body></html>"""
    return Message(
        event_type=f"{account_domain}_password_reset",
        channel="email",
        recipient=recipient,
        subject="RetailMetrics Password Reset",
        body=body,
    )


def reset_token_may_be_exposed(settings: Settings) -> bool:
    """Development escape hatch: only explicit mock mode may expose a token."""
    return settings.notification_mode == "mock" and settings.auth_expose_reset_token
