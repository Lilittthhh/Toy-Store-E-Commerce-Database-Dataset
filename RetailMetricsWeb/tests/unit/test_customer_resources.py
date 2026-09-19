from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from api.schemas.customer_resources import CustomerAddressCreate, CustomerAddressUpdate, PaymentMethodCreate, PaymentMethodUpdate
from core.models import CustomerAccount
from services.customer_resource_service import CustomerResourceService
from tests.unit.fake_customer_resource_repository import FakeCustomerResourceRepository


def account(account_id=1, active=True):
    now = datetime.now(timezone.utc)
    return CustomerAccount(account_id, None, f"c{account_id}@example.com", "hash", active, 0, None, None, now, None, None, 1, 1, now, now)


ADDRESS = {
    "label": "Home", "recipient_first_name": "Ada", "recipient_last_name": "Lovelace",
    "phone": None, "address_line_1": "1 Demo Street", "address_line_2": None,
    "city": "Manila", "province_region": "Metro Manila", "postal_code": "1000", "country_code": "PH",
}


def test_address_ownership_defaults_versions_and_promotion() -> None:
    repo = FakeCustomerResourceRepository()
    service = CustomerResourceService(repo)
    owner, stranger = account(1), account(2)
    first = service.create_address(owner, ADDRESS, False)
    second = service.create_address(owner, {**ADDRESS, "label": "Office"}, False)
    assert first.is_default and not second.is_default
    assert len(service.list_addresses(owner)) == 2
    assert service.get_address(owner, first.customer_address_id) == first
    with pytest.raises(HTTPException) as private:
        service.get_address(stranger, first.customer_address_id)
    assert private.value.status_code == 404
    updated = service.update_address(owner, second.customer_address_id, {**ADDRESS, "label": "Work"}, 1)
    assert updated.label == "Work" and updated.row_version == 2
    with pytest.raises(HTTPException) as stale:
        service.update_address(owner, second.customer_address_id, ADDRESS, 1)
    assert stale.value.status_code == 409
    selected = service.set_default_address(owner, second.customer_address_id, 2)
    assert selected.is_default
    assert sum(x.is_default and x.is_active for x in service.list_addresses(owner)) == 1
    deactivated = service.deactivate_address(owner, second.customer_address_id, selected.row_version)
    assert not deactivated.is_active
    assert service.get_address(owner, first.customer_address_id).is_default


def test_payment_types_labels_defaults_versions_and_ownership() -> None:
    repo = FakeCustomerResourceRepository()
    service = CustomerResourceService(repo)
    owner, stranger = account(1), account(2)
    card_values = service.payment_values("card", "Visa", "1234")
    card = service.create_payment_method(owner, card_values, False)
    assert card.display_label == "Visa ending in 1234 — simulated" and card.is_default
    created = []
    for kind, label in (("gcash", "GCash — simulated"), ("paypal", "PayPal — simulated"), ("cash_on_delivery", "Cash on Delivery")):
        item = service.create_payment_method(owner, service.payment_values(kind, None, None), False)
        assert item.display_label == label
        created.append(item)
    with pytest.raises(HTTPException) as private:
        service.get_payment_method(stranger, card.payment_method_id)
    assert private.value.status_code == 404
    paypal = created[1]
    changed = service.update_payment_method(owner, paypal.payment_method_id, service.payment_values("card", "Mastercard", "5678"), 1)
    assert changed.display_label == "Mastercard ending in 5678 — simulated"
    with pytest.raises(HTTPException) as stale:
        service.set_default_payment_method(owner, changed.payment_method_id, 1)
    assert stale.value.status_code == 409
    selected = service.set_default_payment_method(owner, changed.payment_method_id, changed.row_version)
    assert sum(x.is_default and x.is_active for x in service.list_payment_methods(owner)) == 1
    service.deactivate_payment_method(owner, selected.payment_method_id, selected.row_version)
    assert service.get_payment_method(owner, card.payment_method_id).is_default


@pytest.mark.parametrize("field", ["customer_account_id", "created_at", "updated_at", "row_version", "is_active"])
def test_address_create_rejects_server_owned_fields(field: str) -> None:
    with pytest.raises(ValidationError):
        CustomerAddressCreate.model_validate({**ADDRESS, field: 1})


@pytest.mark.parametrize("field", ["customer_account_id", "display_label", "full_card_number", "card_number", "cvv", "gcash_number", "paypal_email", "password", "otp", "access_token", "created_at", "updated_at", "is_active"])
def test_payment_create_rejects_protected_or_sensitive_fields(field: str) -> None:
    with pytest.raises(ValidationError):
        PaymentMethodCreate.model_validate({"method_type": "card", "card_brand": "Visa", "card_last_four": "1234", field: "forbidden"})


def test_payment_validation_requires_safe_metadata_only() -> None:
    with pytest.raises(ValidationError):
        PaymentMethodCreate.model_validate({"method_type": "card", "card_brand": "Visa"})
    with pytest.raises(ValidationError):
        PaymentMethodCreate.model_validate({"method_type": "card", "card_brand": "Visa", "card_last_four": "12x4"})
    with pytest.raises(ValidationError):
        PaymentMethodCreate.model_validate({"method_type": "gcash", "card_brand": "Visa", "card_last_four": "1234"})


def test_update_schemas_also_reject_ownership_and_display_label() -> None:
    with pytest.raises(ValidationError):
        CustomerAddressUpdate.model_validate({**ADDRESS, "row_version": 1, "customer_account_id": 9})
    with pytest.raises(ValidationError):
        PaymentMethodUpdate.model_validate({"method_type": "paypal", "row_version": 1, "display_label": "fake"})


def test_inactive_customer_cannot_mutate() -> None:
    service = CustomerResourceService(FakeCustomerResourceRepository())
    with pytest.raises(HTTPException) as denied:
        service.create_address(account(active=False), ADDRESS, False)
    assert denied.value.status_code == 403
