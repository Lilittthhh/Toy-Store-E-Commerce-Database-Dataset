from decimal import Decimal

import pytest
from pydantic import ValidationError

from api.schemas.storefront import (
    CartItemAddRequest, CartItemUpdateRequest, CatalogConfigureRequest,
    StorefrontProductResponse,
)


VALID_CATALOG = {
    "description": "A configured product.", "current_price_usd": "19.99",
    "current_cogs_usd": "8.50", "image_url": "https://example.com/toy.png",
    "is_available": True, "row_version": None,
}


def test_catalog_price_cogs_and_image_validation() -> None:
    model = CatalogConfigureRequest.model_validate(VALID_CATALOG)
    assert model.current_price_usd == Decimal("19.99")
    for changes in (
        {"current_price_usd": "0"},
        {"current_cogs_usd": "-0.01"},
        {"current_cogs_usd": "20.00"},
        {"image_url": "javascript:alert(1)"},
    ):
        with pytest.raises(ValidationError):
            CatalogConfigureRequest.model_validate({**VALID_CATALOG, **changes})


@pytest.mark.parametrize(
    "field",
    ["customer_account_id", "shopping_cart_id", "unit_price_usd", "current_price_usd", "current_price_override", "server_total", "cart_subtotal_usd", "record_origin", "created_by_app_user_id", "updated_by_app_user_id", "created_at", "updated_at"],
)
def test_add_cart_rejects_server_owned_fields(field: str) -> None:
    with pytest.raises(ValidationError):
        CartItemAddRequest.model_validate({"product_id": 1, "quantity": 1, field: "forbidden"})


def test_cart_quantities_require_one_to_ninety_nine() -> None:
    for quantity in (0, 100):
        with pytest.raises(ValidationError):
            CartItemAddRequest.model_validate({"product_id": 1, "quantity": quantity})
        with pytest.raises(ValidationError):
            CartItemUpdateRequest.model_validate({"quantity": quantity, "row_version": 1})


def test_customer_product_schema_has_no_cogs_or_audit_fields() -> None:
    response = StorefrontProductResponse(
        product_id=1, product_name="Toy", description="Demo",
        current_price_usd=Decimal("12.00"), image_url=None, is_available=True,
    )
    assert set(response.model_dump()) == {
        "product_id", "product_name", "description", "current_price_usd", "image_url", "is_available"
    }
