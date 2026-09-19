from __future__ import annotations

from datetime import datetime

from pydantic import EmailStr, Field

from api.schemas.auth import StrictRequest
from core.models import CustomerIdentity


class CustomerStatusUpdate(StrictRequest):
    is_active: bool
    row_version: int = Field(ge=1)


class CustomerUnlockRequest(StrictRequest):
    row_version: int = Field(ge=1)


class AdminCustomerResponse(StrictRequest):
    customer_account_id: int
    email: EmailStr
    dataset_user_id: int | None
    first_name: str
    last_name: str
    phone: str | None
    is_active: bool
    failed_login_attempts: int
    locked_until: datetime | None
    last_login_at: datetime | None
    account_row_version: int
    profile_row_version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_identity(cls, identity: CustomerIdentity) -> "AdminCustomerResponse":
        return cls(
            customer_account_id=identity.account.customer_account_id,
            email=identity.account.email,
            dataset_user_id=identity.account.dataset_user_id,
            first_name=identity.profile.first_name,
            last_name=identity.profile.last_name,
            phone=identity.profile.phone,
            is_active=identity.account.is_active,
            failed_login_attempts=identity.account.failed_login_attempts,
            locked_until=identity.account.locked_until,
            last_login_at=identity.account.last_login_at,
            account_row_version=identity.account.row_version,
            profile_row_version=identity.profile.row_version,
            created_at=identity.account.created_at,
            updated_at=max(identity.account.updated_at, identity.profile.updated_at),
        )
