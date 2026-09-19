import pytest
from pydantic import ValidationError

from api.schemas.order_workflow import OrderTransitionRequest


def test_order_transition_accepts_only_row_version() -> None:
    assert OrderTransitionRequest.model_validate({"row_version": 3}).row_version == 3
    for field in ("order_status", "payment_status", "customer_account_id", "record_origin", "created_by_app_user_id"):
        with pytest.raises(ValidationError):
            OrderTransitionRequest.model_validate({"row_version": 3, field: "forbidden"})

