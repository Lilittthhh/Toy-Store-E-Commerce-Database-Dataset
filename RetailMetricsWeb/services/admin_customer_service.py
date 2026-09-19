from __future__ import annotations

from fastapi import HTTPException

from core.models import CustomerAccount, CustomerIdentity
from repositories.customer_repository import CustomerRepository


class AdminCustomerService:
    def __init__(self, repository: CustomerRepository):
        self.repository = repository

    def get_customer(self, customer_account_id: int) -> CustomerIdentity:
        identity = self.repository.get_identity(customer_account_id)
        if identity is None:
            raise HTTPException(status_code=404, detail="Customer account not found.")
        return identity

    def change_active(self, customer_account_id: int, is_active: bool, row_version: int) -> CustomerIdentity:
        self._require_account_version(customer_account_id, row_version)
        updated = self.repository.update_active(customer_account_id, is_active, row_version)
        if updated is None:
            self._raise_stale(customer_account_id, row_version)
        return self.get_customer(customer_account_id)

    def unlock(self, customer_account_id: int, row_version: int) -> CustomerIdentity:
        self._require_account_version(customer_account_id, row_version)
        updated = self.repository.unlock(customer_account_id, row_version)
        if updated is None:
            self._raise_stale(customer_account_id, row_version)
        return self.get_customer(customer_account_id)

    def _require_account_version(self, customer_account_id: int, expected: int) -> CustomerAccount:
        account = self.repository.get_by_id(customer_account_id)
        if account is None:
            raise HTTPException(status_code=404, detail="Customer account not found.")
        if account.row_version != expected:
            raise HTTPException(status_code=409, detail=f"Stale row_version: expected {expected}, current value is {account.row_version}.")
        return account

    def _raise_stale(self, customer_account_id: int, expected: int) -> None:
        current = self._require_account_version(customer_account_id, expected)
        raise HTTPException(status_code=409, detail=f"Stale row_version: expected {expected}, current value is {current.row_version}.")
