from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from api.schemas.auth import StrictRequest
from api.schemas.customer_auth import _normalize_name, _normalize_phone
from core.models import CustomerProfile


class CustomerProfileUpdate(StrictRequest):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=32)
    row_version: int = Field(ge=1)

    _first_name = field_validator("first_name")(_normalize_name)
    _last_name = field_validator("last_name")(_normalize_name)
    _phone = field_validator("phone")(_normalize_phone)


class CustomerProfileResponse(StrictRequest):
    customer_account_id: int
    first_name: str
    last_name: str
    phone: str | None
    row_version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_profile(cls, profile: CustomerProfile) -> "CustomerProfileResponse":
        return cls(**profile.__dict__)
