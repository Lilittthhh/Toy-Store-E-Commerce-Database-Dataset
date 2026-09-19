from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


APP_ROOT = Path(__file__).resolve().parents[1]


def _positive_int(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value < 1:
        raise RuntimeError(f"{name} must be a positive integer")
    return value


def _boolean(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} must be true or false")


@dataclass(frozen=True)
class Settings:
    pg_host: str = "localhost"
    pg_port: int = 5432
    pg_database: str = "retailmetrics"
    pg_user: str = "postgres"
    pg_password: str | None = field(default=None, repr=False)
    pg_sslmode: str = "prefer"
    pg_connect_timeout: int = 10
    db_pool_min: int = 1
    db_pool_max: int = 8
    jwt_secret_key: str = field(default="", repr=False)
    jwt_algorithm: str = "HS256"
    jwt_access_token_minutes: int = 30
    auth_lockout_attempts: int = 5
    auth_lockout_minutes: int = 15
    auth_reset_token_minutes: int = 15
    auth_expose_reset_token: bool = False
    audit_trail_enabled: bool = False
    notification_mode: str = "mock"
    email_provider: str = "smtp"
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = field(default="", repr=False)
    smtp_from_email: str = ""
    smtp_from_name: str = "RetailMetrics"
    smtp_live_send_enabled: bool = False
    sms_provider: str = "brevo"
    brevo_api_key: str = field(default="", repr=False)
    brevo_sms_sender: str = "RetailMetrics"
    brevo_sms_live_send_enabled: bool = False
    sms_live_send_enabled: bool = False
    infobip_base_url: str = ""
    infobip_email_api_key: str = field(default="", repr=False)
    infobip_sms_api_key: str = field(default="", repr=False)
    infobip_email_from: str = ""
    infobip_email_from_name: str = "RetailMetrics"
    infobip_sms_sender: str = "RetailMetrics"
    infobip_live_send_enabled: bool = False

    @classmethod
    def from_environment(cls) -> "Settings":
        load_dotenv(APP_ROOT / ".env", override=False)
        secret = os.getenv("JWT_SECRET_KEY", "")
        if len(secret) < 32 or secret.startswith("replace_with_"):
            raise RuntimeError(
                "JWT_SECRET_KEY must be a private value of at least 32 characters"
            )

        notification_mode = os.getenv("NOTIFICATION_MODE", "mock").strip().lower()
        if notification_mode not in {"mock", "live", "infobip"}:
            raise RuntimeError("NOTIFICATION_MODE must be mock, live, or infobip")
        email_provider = os.getenv("EMAIL_PROVIDER", "smtp").strip().lower()
        if email_provider not in {"mock", "smtp", "infobip"}:
            raise RuntimeError("EMAIL_PROVIDER must be mock, smtp, or infobip")
        sms_provider = os.getenv("SMS_PROVIDER", "brevo").strip().lower()
        if sms_provider not in {"mock", "brevo"}:
            raise RuntimeError("SMS_PROVIDER must be mock or brevo")

        pool_min = _positive_int("DB_POOL_MIN", 1)
        pool_max = _positive_int("DB_POOL_MAX", 8)
        if pool_max < pool_min:
            raise RuntimeError("DB_POOL_MAX must be greater than or equal to DB_POOL_MIN")

        return cls(
            pg_host=os.getenv("PGHOST", "localhost"),
            pg_port=_positive_int("PGPORT", 5432),
            pg_database=os.getenv("PGDATABASE", "retailmetrics"),
            pg_user=os.getenv("PGUSER", "postgres"),
            pg_password=os.getenv("PGPASSWORD") or None,
            pg_sslmode=os.getenv("PGSSLMODE", "prefer"),
            pg_connect_timeout=_positive_int("PGCONNECT_TIMEOUT", 10),
            db_pool_min=pool_min,
            db_pool_max=pool_max,
            jwt_secret_key=secret,
            jwt_access_token_minutes=_positive_int("JWT_ACCESS_TOKEN_MINUTES", 30),
            auth_lockout_attempts=_positive_int("AUTH_LOCKOUT_ATTEMPTS", 5),
            auth_lockout_minutes=_positive_int("AUTH_LOCKOUT_MINUTES", 15),
            auth_reset_token_minutes=_positive_int("AUTH_RESET_TOKEN_MINUTES", 15),
            auth_expose_reset_token=_boolean("AUTH_EXPOSE_RESET_TOKEN", False),
            audit_trail_enabled=_boolean("AUDIT_TRAIL_ENABLED", False),
            notification_mode=notification_mode,
            email_provider=email_provider,
            smtp_host=os.getenv("SMTP_HOST", "smtp.gmail.com").strip(),
            smtp_port=_positive_int("SMTP_PORT", 587),
            smtp_username=os.getenv("SMTP_USERNAME", "").strip(),
            smtp_password=os.getenv("SMTP_PASSWORD", ""),
            smtp_from_email=os.getenv("SMTP_FROM_EMAIL", "").strip(),
            smtp_from_name=os.getenv("SMTP_FROM_NAME", "RetailMetrics").strip(),
            smtp_live_send_enabled=_boolean("SMTP_LIVE_SEND_ENABLED", False),
            sms_provider=sms_provider,
            brevo_api_key=os.getenv("BREVO_API_KEY", "").strip(),
            brevo_sms_sender=os.getenv("BREVO_SMS_SENDER", "RetailMetrics").strip(),
            brevo_sms_live_send_enabled=_boolean("BREVO_SMS_LIVE_SEND_ENABLED", False),
            sms_live_send_enabled=_boolean("SMS_LIVE_SEND_ENABLED", False),
            infobip_base_url=os.getenv("INFOBIP_BASE_URL", "").strip(),
            infobip_email_api_key=os.getenv("INFOBIP_EMAIL_API_KEY", "").strip(),
            infobip_sms_api_key=os.getenv("INFOBIP_SMS_API_KEY", "").strip(),
            infobip_email_from=os.getenv("INFOBIP_EMAIL_FROM", "").strip(),
            infobip_email_from_name=os.getenv("INFOBIP_EMAIL_FROM_NAME", "RetailMetrics").strip(),
            infobip_sms_sender=os.getenv("INFOBIP_SMS_SENDER", "RetailMetrics").strip(),
            infobip_live_send_enabled=_boolean("INFOBIP_LIVE_SEND_ENABLED", False),
        )

    def database_kwargs(self) -> dict[str, Any]:
        values: dict[str, Any] = {
            "host": self.pg_host,
            "port": self.pg_port,
            "dbname": self.pg_database,
            "user": self.pg_user,
            "sslmode": self.pg_sslmode,
            "connect_timeout": self.pg_connect_timeout,
            "application_name": "retailmetrics_web_api",
        }
        if self.pg_password:
            values["password"] = self.pg_password
        return values


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_environment()
