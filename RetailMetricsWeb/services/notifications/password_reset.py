from __future__ import annotations

from html import escape
from urllib.parse import urlencode

from core.config import Settings
from services.notifications.providers import Message


def password_reset_message(
    recipient: str,
    reset_token: str,
    lifetime_minutes: int,
    account_domain: str,
    frontend_base_url: str = "http://localhost:8501",
) -> Message:
    reset_url = f"{frontend_base_url.rstrip('/')}?{urlencode({'reset_token': reset_token, 'account': account_domain})}"
    safe_url = escape(reset_url, quote=True)
    body = f"""<!doctype html>
<html>
<body style="margin:0;background:#edf3f1;font-family:Arial,sans-serif;color:#23313d;padding:28px 14px">
  <div style="max-width:600px;margin:auto;background:#fff;border:1px solid #d7e2df;border-radius:18px;overflow:hidden">
    <div style="background:#173c40;color:#fff;padding:26px 34px;font-size:24px;font-weight:800">
      <span style="display:inline-block;background:#e8bc62;color:#173c40;border-radius:10px;padding:8px;margin-right:10px">RM</span>
      RetailMetrics
    </div>
    <div style="padding:36px 34px 30px">
      <div style="color:#187a68;font-size:12px;font-weight:800;letter-spacing:2px;text-transform:uppercase">Account security</div>
      <h1 style="font-size:28px;margin:12px 0 24px">Reset your password</h1>
      <p style="line-height:1.65">We received a request to reset the password for your RetailMetrics account.</p>
      <p style="line-height:1.65">Select the button below to choose a new password.</p>
      <p style="margin:28px 0">
        <a href="{safe_url}" style="background:#bd492e;color:#fff;text-decoration:none;font-weight:800;border-radius:8px;padding:14px 22px;display:inline-block">Reset password</a>
      </p>
      <p style="color:#60758a;line-height:1.6">This link expires in {int(lifetime_minutes)} minutes. If you did not request a password reset, you can safely ignore this email.</p>
      <hr style="border:0;border-top:1px solid #d7e2df;margin:26px 0">
      <p style="color:#60758a;font-size:13px;line-height:1.6">If the button does not work, copy this link into your browser:<br>
        <a href="{safe_url}" style="color:#187a68;overflow-wrap:anywhere">{safe_url}</a>
      </p>
    </div>
  </div>
</body>
</html>"""
    return Message(
        event_type=f"{account_domain}_password_reset",
        channel="email",
        recipient=recipient,
        subject="Reset your RetailMetrics password",
        body=body,
    )


def reset_token_may_be_exposed(settings: Settings) -> bool:
    """Development escape hatch: only explicit mock mode may expose a token."""
    return settings.notification_mode == "mock" and settings.auth_expose_reset_token
