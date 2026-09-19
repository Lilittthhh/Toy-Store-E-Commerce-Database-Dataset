from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import Field

from api.schemas.auth import StrictRequest


class CheckoutRequest(StrictRequest):
    address_id: int = Field(gt=0)
    payment_method_id: int = Field(gt=0)
    cart_row_version: int = Field(ge=1)


class CancelOrderRequest(StrictRequest):
    row_version: int = Field(ge=1)


class CustomerOrderItemResponse(StrictRequest):
    product_id: int
    product_name: str
    quantity: int
    unit_price_usd: Decimal
    line_total_usd: Decimal


class ShippingSnapshotResponse(StrictRequest):
    recipient_first_name: str
    recipient_last_name: str
    phone: str | None
    address_line_1: str
    address_line_2: str | None
    city: str
    province_region: str
    postal_code: str
    country_code: str


class PaymentSnapshotResponse(StrictRequest):
    method_type: str
    display_label: str
    payment_status: str
    amount_usd: Decimal
    simulated_reference: str | None


class CustomerOrderSummaryResponse(StrictRequest):
    order_id: int
    created_at: datetime
    order_status: str
    payment_status: str
    item_count: int
    total_quantity: int
    total_usd: Decimal
    row_version: int
    delivered_at: datetime | None = None
    delivered_confirmed_by_customer: bool = False


class CustomerOrderDetailResponse(StrictRequest):
    order_id: int
    created_at: datetime
    order_status: str
    total_quantity: int
    total_usd: Decimal
    row_version: int
    delivered_at: datetime | None = None
    delivered_confirmed_by_customer: bool = False
    items: list[CustomerOrderItemResponse]
    shipping: ShippingSnapshotResponse
    payment: PaymentSnapshotResponse
