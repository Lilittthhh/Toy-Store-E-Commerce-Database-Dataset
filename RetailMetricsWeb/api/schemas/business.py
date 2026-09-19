from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictBusinessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OriginFilter(str, Enum):
    ALL = "all"
    IMPORTED = "imported"
    WEB = "web"
    CUSTOMER = "customer"


class ProductWrite(StrictBusinessRequest):
    created_at: datetime
    product_name: str = Field(min_length=1, max_length=500)

    @field_validator("product_name")
    @classmethod
    def product_name_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("product_name must not be blank")
        return value


class ProductCreate(ProductWrite):
    pass


class ProductUpdate(ProductWrite):
    row_version: int = Field(ge=1)


class OrderWrite(StrictBusinessRequest):
    created_at: datetime
    website_session_id: int = Field(ge=1)
    user_id: int = Field(ge=1)
    primary_product_id: int | None = Field(default=None, ge=1)
    items_purchased: int = Field(ge=1)
    price_usd: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    cogs_usd: Decimal = Field(ge=0, max_digits=12, decimal_places=2)


class OrderCreate(OrderWrite):
    pass


class OrderUpdate(OrderWrite):
    row_version: int = Field(ge=1)


class OrderItemWrite(StrictBusinessRequest):
    created_at: datetime
    order_id: int = Field(ge=1)
    product_id: int = Field(ge=1)
    is_primary_item: int | None = Field(default=None, ge=0, le=1)
    price_usd: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    cogs_usd: Decimal = Field(ge=0, max_digits=12, decimal_places=2)


class OrderItemCreate(OrderItemWrite):
    pass


class OrderItemUpdate(OrderItemWrite):
    row_version: int = Field(ge=1)


class RefundWrite(StrictBusinessRequest):
    created_at: datetime
    order_item_id: int = Field(ge=1)
    order_id: int = Field(ge=1)
    refund_amount_usd: Decimal = Field(gt=0, max_digits=12, decimal_places=2)


class RefundCreate(RefundWrite):
    pass


class RefundUpdate(RefundWrite):
    row_version: int = Field(ge=1)


class MutableResponse(BaseModel):
    created_by_app_user_id: int | None
    row_version: int
    origin: str


class ProductResponse(MutableResponse):
    product_id: int
    created_at: datetime
    product_name: str


class OrderResponse(MutableResponse):
    order_id: int
    created_at: datetime
    website_session_id: int | None
    user_id: int | None
    customer_account_id: int | None
    primary_product_id: int | None
    items_purchased: int
    price_usd: Decimal
    cogs_usd: Decimal
    order_status: str | None = None


class OrderItemResponse(MutableResponse):
    order_item_id: int
    created_at: datetime
    order_id: int
    product_id: int
    is_primary_item: int | None
    price_usd: Decimal
    cogs_usd: Decimal


class RefundResponse(MutableResponse):
    order_item_refund_id: int
    created_at: datetime
    order_item_id: int
    order_id: int
    refund_amount_usd: Decimal


class WebsiteSessionResponse(BaseModel):
    website_session_id: int
    created_at: datetime
    user_id: int
    is_repeat_session: int | None
    utm_source: str | None
    utm_campaign: str | None
    utm_content: str | None
    device_type: str | None
    http_referer: str | None


class WebsitePageviewResponse(BaseModel):
    website_pageview_id: int
    created_at: datetime
    website_session_id: int
    pageview_url: str


T = TypeVar("T")


class PageResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class DeleteResponse(BaseModel):
    deleted_id: int
    message: str
