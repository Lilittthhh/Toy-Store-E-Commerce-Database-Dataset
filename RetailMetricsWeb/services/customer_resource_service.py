from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from core.models import CustomerAccount, CustomerAddress, PaymentMethod
from repositories.customer_resource_repository import CustomerResourceRepository


PAYMENT_LABELS = {
    "gcash": "GCash — simulated",
    "paypal": "PayPal — simulated",
    "cash_on_delivery": "Cash on Delivery",
}


class CustomerResourceService:
    def __init__(self, repository: CustomerResourceRepository):
        self.repository = repository

    @staticmethod
    def _account_id(account: CustomerAccount) -> int:
        if not account.is_active:
            raise HTTPException(status_code=403, detail="Customer account is inactive.")
        return account.customer_account_id

    def list_addresses(self, account: CustomerAccount) -> list[CustomerAddress]:
        return self.repository.list_addresses(self._account_id(account))

    def get_address(self, account: CustomerAccount, resource_id: int) -> CustomerAddress:
        value = self.repository.get_address(self._account_id(account), resource_id)
        if value is None:
            raise HTTPException(status_code=404, detail="Address not found.")
        return value

    def create_address(self, account: CustomerAccount, values: dict[str, Any], make_default: bool) -> CustomerAddress:
        return self.repository.create_address(self._account_id(account), values, make_default)

    def update_address(self, account: CustomerAccount, resource_id: int, values: dict[str, Any], version: int) -> CustomerAddress:
        current = self.get_address(account, resource_id)
        self._check_version(current.row_version, version)
        updated = self.repository.update_address(account.customer_account_id, resource_id, values, version)
        return updated or self._raise_address_conflict(account, resource_id, version)

    def set_default_address(self, account: CustomerAccount, resource_id: int, version: int) -> CustomerAddress:
        current = self.get_address(account, resource_id)
        self._check_version(current.row_version, version)
        if not current.is_active:
            raise HTTPException(status_code=409, detail="An inactive address cannot be the default.")
        updated = self.repository.set_default_address(account.customer_account_id, resource_id, version)
        return updated or self._raise_address_conflict(account, resource_id, version)

    def deactivate_address(self, account: CustomerAccount, resource_id: int, version: int) -> CustomerAddress:
        current = self.get_address(account, resource_id)
        self._check_version(current.row_version, version)
        if not current.is_active:
            raise HTTPException(status_code=409, detail="Address is already inactive.")
        updated = self.repository.deactivate_address(account.customer_account_id, resource_id, version)
        return updated or self._raise_address_conflict(account, resource_id, version)

    def _raise_address_conflict(self, account: CustomerAccount, resource_id: int, version: int):
        current = self.get_address(account, resource_id)
        self._check_version(current.row_version, version)
        raise HTTPException(status_code=409, detail="Address changed during the request.")

    def list_payment_methods(self, account: CustomerAccount) -> list[PaymentMethod]:
        return self.repository.list_payment_methods(self._account_id(account))

    def get_payment_method(self, account: CustomerAccount, resource_id: int) -> PaymentMethod:
        value = self.repository.get_payment_method(self._account_id(account), resource_id)
        if value is None:
            raise HTTPException(status_code=404, detail="Payment method not found.")
        return value

    @staticmethod
    def payment_values(method_type: str, card_brand: str | None, card_last_four: str | None) -> dict[str, Any]:
        brand = card_brand.strip() if card_brand else None
        if method_type == "card":
            label = f"{brand} ending in {card_last_four} — simulated"
        else:
            label = PAYMENT_LABELS[method_type]
        return {
            "method_type": method_type,
            "display_label": label,
            "card_brand": brand,
            "card_last_four": card_last_four,
        }

    def create_payment_method(self, account: CustomerAccount, values: dict[str, Any], make_default: bool) -> PaymentMethod:
        return self.repository.create_payment_method(self._account_id(account), values, make_default)

    def update_payment_method(self, account: CustomerAccount, resource_id: int, values: dict[str, Any], version: int) -> PaymentMethod:
        current = self.get_payment_method(account, resource_id)
        self._check_version(current.row_version, version)
        updated = self.repository.update_payment_method(account.customer_account_id, resource_id, values, version)
        return updated or self._raise_payment_conflict(account, resource_id, version)

    def set_default_payment_method(self, account: CustomerAccount, resource_id: int, version: int) -> PaymentMethod:
        current = self.get_payment_method(account, resource_id)
        self._check_version(current.row_version, version)
        if not current.is_active:
            raise HTTPException(status_code=409, detail="An inactive payment method cannot be the default.")
        updated = self.repository.set_default_payment_method(account.customer_account_id, resource_id, version)
        return updated or self._raise_payment_conflict(account, resource_id, version)

    def deactivate_payment_method(self, account: CustomerAccount, resource_id: int, version: int) -> PaymentMethod:
        current = self.get_payment_method(account, resource_id)
        self._check_version(current.row_version, version)
        if not current.is_active:
            raise HTTPException(status_code=409, detail="Payment method is already inactive.")
        updated = self.repository.deactivate_payment_method(account.customer_account_id, resource_id, version)
        return updated or self._raise_payment_conflict(account, resource_id, version)

    def _raise_payment_conflict(self, account: CustomerAccount, resource_id: int, version: int):
        current = self.get_payment_method(account, resource_id)
        self._check_version(current.row_version, version)
        raise HTTPException(status_code=409, detail="Payment method changed during the request.")

    @staticmethod
    def _check_version(current: int, expected: int) -> None:
        if current != expected:
            raise HTTPException(status_code=409, detail=f"Stale row_version: expected {expected}, current value is {current}.")
