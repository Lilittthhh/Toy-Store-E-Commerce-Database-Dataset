from __future__ import annotations

from datetime import datetime

from pydantic import EmailStr, Field, SecretStr, field_validator

from api.schemas.auth import StrictRequest, validate_password_strength
from core.models import AppUser, Role


class AdminUserCreate(StrictRequest):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    email: EmailStr
    password: SecretStr
    role: Role

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.strip().lower()

    _strong_password = field_validator("password")(validate_password_strength)


class UserRoleUpdate(StrictRequest):
    role: Role
    row_version: int = Field(ge=1)


class UserStatusUpdate(StrictRequest):
    is_active: bool
    row_version: int = Field(ge=1)


class UserUnlockRequest(StrictRequest):
    row_version: int = Field(ge=1)


class AdminUserResponse(StrictRequest):
    app_user_id: int
    username: str
    email: EmailStr
    role: Role
    is_active: bool
    failed_login_attempts: int
    locked_until: datetime | None
    last_login_at: datetime | None
    password_changed_at: datetime
    token_version: int
    row_version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_user(cls, user: AppUser) -> "AdminUserResponse":
        return cls(
            app_user_id=user.app_user_id,
            username=user.username,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            failed_login_attempts=user.failed_login_attempts,
            locked_until=user.locked_until,
            last_login_at=user.last_login_at,
            password_changed_at=user.password_changed_at,
            token_version=user.token_version,
            row_version=user.row_version,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )
