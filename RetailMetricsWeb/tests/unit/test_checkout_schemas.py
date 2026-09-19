import pytest
from pydantic import ValidationError

from api.schemas.checkout import CancelOrderRequest, CheckoutRequest


@pytest.mark.parametrize(
    "field",
    [
        "customer_account_id", "order_id", "record_origin", "order_status",
        "payment_status", "price_usd", "current_price_usd", "subtotal",
        "total", "cogs_usd", "created_by_app_user_id", "shipping_snapshot",
        "recipient_first_name", "payment_display_snapshot",
    ],
)
def test_checkout_rejects_server_controlled_fields(field: str) -> None:
    with pytest.raises(ValidationError):
        CheckoutRequest.model_validate({
            "address_id": 1, "payment_method_id": 2, "cart_row_version": 3,
            field: "forbidden",
        })


def test_checkout_requires_only_positive_resource_ids_and_cart_version() -> None:
    assert CheckoutRequest(address_id=1, payment_method_id=2, cart_row_version=3)
    with pytest.raises(ValidationError):
        CheckoutRequest(address_id=0, payment_method_id=2, cart_row_version=3)


def test_cancel_request_accepts_only_row_version() -> None:
    assert CancelOrderRequest(row_version=1)
    with pytest.raises(ValidationError):
        CancelOrderRequest.model_validate({"row_version": 1, "order_status": "cancelled"})
