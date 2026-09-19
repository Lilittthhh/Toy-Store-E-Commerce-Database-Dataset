from __future__ import annotations

import re
from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    field_validator,
)

from core.models import AppUser, Role


def validate_password_strength(value: SecretStr) -> SecretStr:
    password = value.get_secret_value()
    requirements = (
        (len(password) >= 12, "at least 12 characters"),
        (bool(re.search(r"[A-Z]", password)), "an uppercase letter"),
        (bool(re.search(r"[a-z]", password)), "a lowercase letter"),
        (bool(re.search(r"\d", password)), "a number"),
        (bool(re.search(r"[^A-Za-z0-9]", password)), "a symbol"),
    )
    missing = [description for condition, description in requirements if not condition]
    if missing:
        raise ValueError("Password must contain " + ", ".join(missing) + ".")
    return value


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterRequest(StrictRequest):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    email: EmailStr
    password: SecretStr

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.strip().lower()

    _strong_password = field_validator("password")(validate_password_strength)


class LoginRequest(StrictRequest):
    identifier: str = Field(min_length=1, max_length=254)
    password: SecretStr


class ChangePasswordRequest(StrictRequest):
    current_password: SecretStr
    new_password: SecretStr

    _strong_password = field_validator("new_password")(validate_password_strength)


class ForgotPasswordRequest(StrictRequest):
    email: EmailStr


class ResetPasswordRequest(StrictRequest):
    reset_token: str = Field(min_length=32, max_length=512)
    new_password: SecretStr

    _strong_password = field_validator("new_password")(validate_password_strength)


class UserResponse(BaseModel):
    app_user_id: int
    username: str
    email: EmailStr
    role: Role
    is_active: bool
    locked_until: datetime | None
    last_login_at: datetime | None
    password_changed_at: datetime
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_user(cls, user: AppUser) -> "UserResponse":
        return cls(
            app_user_id=user.app_user_id,
            username=user.username,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            locked_until=user.locked_until,
            last_login_at=user.last_login_at,
            password_changed_at=user.password_changed_at,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class MessageResponse(BaseModel):
    message: str


class ForgotPasswordResponse(MessageResponse):
    reset_token: str | None = None
