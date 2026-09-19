from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field

from api.schemas.auth import StrictRequest


class CustomerOrderWorkflowStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY_SHIPPED = "ready_shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class OrderTransitionRequest(StrictRequest):
    row_version: int = Field(ge=1)


class StaffCustomerOrderResponse(BaseModel):
    order_id: int
    customer_account_id: int
    created_at: datetime
    total_usd: Decimal
    payment_status: str
    order_status: str
    origin: str
    row_version: int
    delivered_at: datetime | None = None
    delivered_confirmed_by_customer: bool = False


class StaffCustomerOrderPage(BaseModel):
    items: list[StaffCustomerOrderResponse]
    total: int
    limit: int
    offset: int
