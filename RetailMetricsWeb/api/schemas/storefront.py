from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import AnyHttpUrl, Field, field_validator, model_validator

from api.schemas.auth import StrictRequest
from core.models import CartItem, CatalogProduct, ShoppingCart


class CatalogConfigureRequest(StrictRequest):
    description: str = Field(max_length=4000)
    current_price_usd: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    current_cogs_usd: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    image_url: AnyHttpUrl | None = None
    is_available: bool
    row_version: int | None = Field(default=None, ge=1)

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("description must not be blank")
        return cleaned

    @model_validator(mode="after")
    def cogs_not_above_price(self):
        if self.current_cogs_usd > self.current_price_usd:
            raise ValueError("current_cogs_usd must not exceed current_price_usd")
        return self


class AdminCatalogResponse(StrictRequest):
    product_id: int
    product_name: str
    description: str | None
    current_price_usd: Decimal | None
    current_cogs_usd: Decimal | None
    image_url: str | None
    is_available: bool | None
    is_configured: bool
    row_version: int | None
    created_at: datetime | None
    updated_at: datetime | None

    @classmethod
    def from_model(cls, value: CatalogProduct) -> "AdminCatalogResponse":
        data = value.__dict__.copy()
        data.pop("updated_by_app_user_id")
        data["is_configured"] = value.is_configured
        return cls(**data)


class StorefrontProductResponse(StrictRequest):
    product_id: int
    product_name: str
    description: str
    current_price_usd: Decimal
    image_url: str | None
    is_available: bool

    @classmethod
    def from_model(cls, value: CatalogProduct) -> "StorefrontProductResponse":
        return cls(
            product_id=value.product_id, product_name=value.product_name,
            description=value.description or "", current_price_usd=value.current_price_usd,
            image_url=value.image_url, is_available=bool(value.is_available),
        )


class CartItemAddRequest(StrictRequest):
    product_id: int = Field(gt=0)
    quantity: int = Field(ge=1, le=99)


class CartItemUpdateRequest(StrictRequest):
    quantity: int = Field(ge=1, le=99)
    row_version: int = Field(ge=1)


class CartItemResponse(StrictRequest):
    cart_item_id: int
    product_id: int
    product_name: str
    image_url: str | None
    quantity: int
    stored_unit_price_usd: Decimal
    current_catalog_price_usd: Decimal | None
    price_changed: bool
    is_available: bool
    line_subtotal_usd: Decimal
    row_version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, value: CartItem) -> "CartItemResponse":
        return cls(
            **value.__dict__,
            price_changed=(
                value.current_catalog_price_usd is not None
                and value.stored_unit_price_usd != value.current_catalog_price_usd
            ),
            line_subtotal_usd=value.stored_unit_price_usd * value.quantity,
        )


class CartResponse(StrictRequest):
    shopping_cart_id: int | None
    row_version: int | None
    items: list[CartItemResponse]
    distinct_items: int
    total_quantity: int
    cart_subtotal_usd: Decimal

    @classmethod
    def from_cart(cls, cart: ShoppingCart) -> "CartResponse":
        responses = [CartItemResponse.from_model(item) for item in cart.items]
        return cls(
            shopping_cart_id=cart.shopping_cart_id,
            row_version=cart.row_version,
            items=responses,
            distinct_items=len(responses),
            total_quantity=sum(item.quantity for item in cart.items),
            cart_subtotal_usd=sum(
                (item.stored_unit_price_usd * item.quantity for item in cart.items),
                start=Decimal("0.00"),
            ),
        )
