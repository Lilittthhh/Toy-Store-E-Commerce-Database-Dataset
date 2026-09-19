from __future__ import annotations

from datetime import datetime

from pydantic import EmailStr, Field, SecretStr, field_validator

from api.schemas.auth import StrictRequest, validate_password_strength
from core.models import CustomerIdentity


def _normalize_name(value: str) -> str:
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise ValueError("Name must not be blank.")
    return normalized


def _normalize_phone(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


class CustomerRegisterRequest(StrictRequest):
    email: EmailStr
    password: SecretStr
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=32)

    _strong_password = field_validator("password")(validate_password_strength)
    _first_name = field_validator("first_name")(_normalize_name)
    _last_name = field_validator("last_name")(_normalize_name)
    _phone = field_validator("phone")(_normalize_phone)


class CustomerLoginRequest(StrictRequest):
    email: EmailStr
    password: SecretStr


class CustomerChangePasswordRequest(StrictRequest):
    current_password: SecretStr
    new_password: SecretStr

    _strong_password = field_validator("new_password")(validate_password_strength)


class CustomerForgotPasswordRequest(StrictRequest):
    email: EmailStr


class CustomerResetPasswordRequest(StrictRequest):
    reset_token: str = Field(min_length=32, max_length=512)
    new_password: SecretStr

    _strong_password = field_validator("new_password")(validate_password_strength)


class CustomerResponse(StrictRequest):
    customer_account_id: int
    email: EmailStr
    is_active: bool
    first_name: str
    last_name: str
    phone: str | None
    profile_row_version: int
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None

    @classmethod
    def from_identity(cls, identity: CustomerIdentity) -> "CustomerResponse":
        return cls(
            customer_account_id=identity.account.customer_account_id,
            email=identity.account.email,
            is_active=identity.account.is_active,
            first_name=identity.profile.first_name,
            last_name=identity.profile.last_name,
            phone=identity.profile.phone,
            profile_row_version=identity.profile.row_version,
            created_at=identity.account.created_at,
            updated_at=max(identity.account.updated_at, identity.profile.updated_at),
            last_login_at=identity.account.last_login_at,
        )
