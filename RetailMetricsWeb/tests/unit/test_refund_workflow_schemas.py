from decimal import Decimal

import pytest
from pydantic import ValidationError

from api.schemas.refund_workflow import (
    CustomerRefundRequestCreate, RefundProcessRequest, RefundRejectRequest,
    RefundReviewRequest,
)


@pytest.mark.parametrize(
    "field",
    [
        "customer_account_id", "order_id", "status", "reviewer",
        "reviewed_by_app_user_id", "reviewed_at", "refund_request_id",
        "record_origin", "created_by_app_user_id", "refund_amount_usd",
    ],
)
def test_customer_refund_request_rejects_server_controlled_fields(field: str) -> None:
    payload = {"order_item_id": 1, "requested_amount": "5.00", "reason": "Damaged", field: 1}
    with pytest.raises(ValidationError):
        CustomerRefundRequestCreate.model_validate(payload)


def test_customer_request_amount_and_reason_are_strict() -> None:
    valid = CustomerRefundRequestCreate.model_validate({
        "order_item_id": 1, "requested_amount": "5.25", "reason": "  Damaged box  ",
    })
    assert valid.requested_amount == Decimal("5.25") and valid.reason == "Damaged box"
    for amount in ("0.00", "-1.00"):
        with pytest.raises(ValidationError):
            CustomerRefundRequestCreate.model_validate({"order_item_id": 1, "requested_amount": amount, "reason": "Damaged"})


def test_staff_transition_schemas_reject_linkage_overrides_and_require_rejection_note() -> None:
    for schema, payload in (
        (RefundReviewRequest, {"row_version": 1, "order_item_id": 1}),
        (RefundProcessRequest, {"row_version": 1, "record_origin": "customer"}),
    ):
        with pytest.raises(ValidationError):
            schema.model_validate(payload)
    with pytest.raises(ValidationError):
        RefundRejectRequest.model_validate({"row_version": 1, "resolution_note": "   "})
