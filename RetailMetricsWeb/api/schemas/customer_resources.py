from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from api.schemas.auth import StrictRequest
from core.models import CustomerAddress, PaymentMethod


def _required_text(value: str) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError("must not be blank")
    return cleaned


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    return cleaned or None


class AddressFields(StrictRequest):
    label: str = Field(min_length=1, max_length=50)
    recipient_first_name: str = Field(min_length=1, max_length=100)
    recipient_last_name: str = Field(min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=32)
    address_line_1: str = Field(min_length=1, max_length=200)
    address_line_2: str | None = Field(default=None, max_length=200)
    city: str = Field(min_length=1, max_length=100)
    province_region: str = Field(min_length=1, max_length=100)
    postal_code: str = Field(min_length=1, max_length=20)
    country_code: str = Field(default="PH", min_length=2, max_length=2)

    _clean_required = field_validator(
        "label", "recipient_first_name", "recipient_last_name", "address_line_1",
        "city", "province_region", "postal_code",
    )(_required_text)
    _clean_optional = field_validator("phone", "address_line_2")(_optional_text)

    @field_validator("country_code")
    @classmethod
    def normalize_country_code(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if len(cleaned) != 2 or not cleaned.isalpha() or not cleaned.isascii():
            raise ValueError("must be a two-letter country code")
        return cleaned


class CustomerAddressCreate(AddressFields):
    is_default: bool = False


class CustomerAddressUpdate(AddressFields):
    row_version: int = Field(ge=1)


class VersionRequest(StrictRequest):
    row_version: int = Field(ge=1)


class CustomerAddressResponse(AddressFields):
    customer_address_id: int
    is_default: bool
    is_active: bool
    row_version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, value: CustomerAddress) -> "CustomerAddressResponse":
        data = value.__dict__.copy()
        data.pop("customer_account_id")
        return cls(**data)


PaymentType = Literal["card", "gcash", "paypal", "cash_on_delivery"]


class PaymentMethodFields(StrictRequest):
    method_type: PaymentType
    card_brand: str | None = Field(default=None, min_length=1, max_length=32)
    card_last_four: str | None = Field(default=None, min_length=4, max_length=4)

    _brand = field_validator("card_brand")(_optional_text)

    @model_validator(mode="after")
    def validate_safe_metadata(self) -> Self:
        if self.method_type == "card":
            if not self.card_brand or not self.card_last_four:
                raise ValueError("Card methods require a simulated brand and last four digits.")
            if not self.card_last_four.isascii() or not self.card_last_four.isdigit():
                raise ValueError("card_last_four must contain exactly four numeric characters.")
        elif self.card_brand is not None or self.card_last_four is not None:
            raise ValueError("Non-card methods must not include card metadata.")
        return self


class PaymentMethodCreate(PaymentMethodFields):
    is_default: bool = False


class PaymentMethodUpdate(PaymentMethodFields):
    row_version: int = Field(ge=1)


class PaymentMethodResponse(PaymentMethodFields):
    payment_method_id: int
    display_label: str
    is_default: bool
    is_active: bool
    row_version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, value: PaymentMethod) -> "PaymentMethodResponse":
        data = value.__dict__.copy()
        data.pop("customer_account_id")
        if data.get("card_last_four") is not None:
            data["card_last_four"] = data["card_last_four"].strip()
        return cls(**data)
