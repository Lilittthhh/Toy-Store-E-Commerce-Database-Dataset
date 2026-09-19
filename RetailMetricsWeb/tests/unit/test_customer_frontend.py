from pydantic import ValidationError
import pytest

from api.schemas.customer_auth import CustomerRegisterRequest
from api.schemas.customer_profile import CustomerProfileUpdate
from frontend.browser_session import COOKIE_NAME as STAFF_COOKIE_NAME
from frontend.customer_browser_session import CUSTOMER_COOKIE_NAME


def test_customer_browser_cookie_namespace_is_separate() -> None:
    assert CUSTOMER_COOKIE_NAME != STAFF_COOKIE_NAME


@pytest.mark.parametrize(
    "protected",
    ["dataset_user_id", "is_active", "token_version", "row_version", "password_hash", "role"],
)
def test_customer_registration_rejects_protected_fields(protected: str) -> None:
    payload = {
        "email": "customer@example.com",
        "password": "Customer-password-1!",
        "first_name": "Customer",
        "last_name": "Tester",
        protected: 1,
    }
    with pytest.raises(ValidationError):
        CustomerRegisterRequest.model_validate(payload)


@pytest.mark.parametrize(
    "protected",
    ["customer_account_id", "email", "password", "is_active", "dataset_user_id", "token_version"],
)
def test_customer_profile_rejects_account_security_fields(protected: str) -> None:
    payload = {
        "first_name": "Customer",
        "last_name": "Tester",
        "phone": None,
        "row_version": 1,
        protected: "forbidden",
    }
    with pytest.raises(ValidationError):
        CustomerProfileUpdate.model_validate(payload)
