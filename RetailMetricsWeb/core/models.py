from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum


class Role(str, Enum):
    ADMIN = "admin"
    OPERATIONS_STAFF = "operations_staff"
    ANALYST = "analyst"


@dataclass(frozen=True)
class AppUser:
    app_user_id: int
    username: str
    email: str
    password_hash: str
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

    def is_locked(self, now: datetime | None = None) -> bool:
        if self.locked_until is None:
            return False
        current_time = now or datetime.now(timezone.utc)
        return self.locked_until > current_time


@dataclass(frozen=True)
class CustomerAccount:
    customer_account_id: int
    dataset_user_id: int | None
    email: str
    password_hash: str
    is_active: bool
    failed_login_attempts: int
    locked_until: datetime | None
    last_login_at: datetime | None
    password_changed_at: datetime
    password_reset_token_hash: str | None
    password_reset_expires_at: datetime | None
    token_version: int
    row_version: int
    created_at: datetime
    updated_at: datetime

    def is_locked(self, now: datetime | None = None) -> bool:
        if self.locked_until is None:
            return False
        current_time = now or datetime.now(timezone.utc)
        return self.locked_until > current_time


@dataclass(frozen=True)
class CustomerProfile:
    customer_account_id: int
    first_name: str
    last_name: str
    phone: str | None
    row_version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class CustomerIdentity:
    account: CustomerAccount
    profile: CustomerProfile


@dataclass(frozen=True)
class CustomerAddress:
    customer_address_id: int
    customer_account_id: int
    label: str
    recipient_first_name: str
    recipient_last_name: str
    phone: str | None
    address_line_1: str
    address_line_2: str | None
    city: str
    province_region: str
    postal_code: str
    country_code: str
    is_default: bool
    is_active: bool
    row_version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class PaymentMethod:
    payment_method_id: int
    customer_account_id: int
    method_type: str
    display_label: str
    card_brand: str | None
    card_last_four: str | None
    is_default: bool
    is_active: bool
    row_version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class CatalogProduct:
    product_id: int
    product_name: str
    description: str | None
    current_price_usd: Decimal | None
    current_cogs_usd: Decimal | None
    image_url: str | None
    is_available: bool | None
    updated_by_app_user_id: int | None
    row_version: int | None
    created_at: datetime | None
    updated_at: datetime | None

    @property
    def is_configured(self) -> bool:
        return self.row_version is not None


@dataclass(frozen=True)
class CartItem:
    cart_item_id: int
    product_id: int
    product_name: str
    image_url: str | None
    quantity: int
    stored_unit_price_usd: Decimal
    current_catalog_price_usd: Decimal | None
    is_available: bool
    row_version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ShoppingCart:
    shopping_cart_id: int | None
    row_version: int | None
    items: list[CartItem]
