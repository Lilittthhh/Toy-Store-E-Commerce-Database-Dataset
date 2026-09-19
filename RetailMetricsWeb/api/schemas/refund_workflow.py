from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field, field_validator

from api.schemas.auth import StrictRequest


class RefundRequestStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    PROCESSED = "processed"


class CustomerRefundRequestCreate(StrictRequest):
    order_item_id: int = Field(gt=0)
    requested_amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def reason_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("reason must not be blank")
        return value


class RefundReviewRequest(StrictRequest):
    row_version: int = Field(ge=1)
    resolution_note: str | None = Field(default=None, max_length=1000)

    @field_validator("resolution_note")
    @classmethod
    def optional_note_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("resolution_note must not be blank")
        return value


class RefundRejectRequest(StrictRequest):
    row_version: int = Field(ge=1)
    resolution_note: str = Field(min_length=1, max_length=1000)

    @field_validator("resolution_note")
    @classmethod
    def note_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("resolution_note must not be blank")
        return value


class RefundProcessRequest(StrictRequest):
    row_version: int = Field(ge=1)


class CustomerRefundRequestResponse(BaseModel):
    refund_request_id: int
    order_id: int
    order_item_id: int
    product_id: int
    product_name: str
    requested_amount: Decimal
    reason: str
    status: str
    created_at: datetime
    reviewed_at: datetime | None
    resolution_note: str | None


class StaffRefundRequestResponse(CustomerRefundRequestResponse):
    row_version: int


class RefundRequestPage(BaseModel):
    items: list[StaffRefundRequestResponse]
    total: int
    limit: int
    offset: int


class RefundEligibilityResponse(BaseModel):
    order_item_id: int
    product_id: int
    product_name: str
    item_price_usd: Decimal
    remaining_refundable_usd: Decimal
    eligible: bool
    reason: str | None
    current_request_status: str | None

