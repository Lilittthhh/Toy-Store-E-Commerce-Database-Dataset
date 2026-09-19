from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from core.models import CustomerAddress, PaymentMethod


class FakeCustomerResourceRepository:
    def __init__(self) -> None:
        self.addresses: dict[int, CustomerAddress] = {}
        self.payments: dict[int, PaymentMethod] = {}
        self.next_address = 1
        self.next_payment = 1
        self.now = datetime.now(timezone.utc)

    def list_addresses(self, account_id):
        return [value for value in self.addresses.values() if value.customer_account_id == account_id]

    def get_address(self, account_id, resource_id):
        value = self.addresses.get(resource_id)
        return value if value and value.customer_account_id == account_id else None

    def create_address(self, account_id, values, make_default):
        owned = self.list_addresses(account_id)
        use_default = make_default or not any(x.is_active and x.is_default for x in owned)
        if use_default:
            for key, item in list(self.addresses.items()):
                if item.customer_account_id == account_id and item.is_active and item.is_default:
                    self.addresses[key] = replace(item, is_default=False, row_version=item.row_version + 1)
        key = self.next_address
        self.next_address += 1
        value = CustomerAddress(key, account_id, **values, is_default=use_default, is_active=True, row_version=1, created_at=self.now, updated_at=self.now)
        self.addresses[key] = value
        return value

    def update_address(self, account_id, resource_id, values, version):
        current = self.get_address(account_id, resource_id)
        if not current or current.row_version != version:
            return None
        value = replace(current, **values, row_version=version + 1)
        self.addresses[resource_id] = value
        return value

    def set_default_address(self, account_id, resource_id, version):
        current = self.get_address(account_id, resource_id)
        if not current or current.row_version != version or not current.is_active:
            return None
        for key, item in list(self.addresses.items()):
            if item.customer_account_id == account_id and item.is_active and item.is_default and key != resource_id:
                self.addresses[key] = replace(item, is_default=False, row_version=item.row_version + 1)
        value = replace(current, is_default=True, row_version=version + 1)
        self.addresses[resource_id] = value
        return value

    def deactivate_address(self, account_id, resource_id, version):
        current = self.get_address(account_id, resource_id)
        if not current or current.row_version != version:
            return None
        value = replace(current, is_active=False, is_default=False, row_version=version + 1)
        self.addresses[resource_id] = value
        if current.is_default:
            candidates = sorted((x for x in self.list_addresses(account_id) if x.is_active), key=lambda x: x.customer_address_id)
            if candidates:
                promoted = candidates[0]
                self.addresses[promoted.customer_address_id] = replace(promoted, is_default=True, row_version=promoted.row_version + 1)
        return value

    def list_payment_methods(self, account_id):
        return [value for value in self.payments.values() if value.customer_account_id == account_id]

    def get_payment_method(self, account_id, resource_id):
        value = self.payments.get(resource_id)
        return value if value and value.customer_account_id == account_id else None

    def create_payment_method(self, account_id, values, make_default):
        owned = self.list_payment_methods(account_id)
        use_default = make_default or not any(x.is_active and x.is_default for x in owned)
        if use_default:
            for key, item in list(self.payments.items()):
                if item.customer_account_id == account_id and item.is_active and item.is_default:
                    self.payments[key] = replace(item, is_default=False, row_version=item.row_version + 1)
        key = self.next_payment
        self.next_payment += 1
        value = PaymentMethod(key, account_id, **values, is_default=use_default, is_active=True, row_version=1, created_at=self.now, updated_at=self.now)
        self.payments[key] = value
        return value

    def update_payment_method(self, account_id, resource_id, values, version):
        current = self.get_payment_method(account_id, resource_id)
        if not current or current.row_version != version:
            return None
        value = replace(current, **values, row_version=version + 1)
        self.payments[resource_id] = value
        return value

    def set_default_payment_method(self, account_id, resource_id, version):
        current = self.get_payment_method(account_id, resource_id)
        if not current or current.row_version != version or not current.is_active:
            return None
        for key, item in list(self.payments.items()):
            if item.customer_account_id == account_id and item.is_active and item.is_default and key != resource_id:
                self.payments[key] = replace(item, is_default=False, row_version=item.row_version + 1)
        value = replace(current, is_default=True, row_version=version + 1)
        self.payments[resource_id] = value
        return value

    def deactivate_payment_method(self, account_id, resource_id, version):
        current = self.get_payment_method(account_id, resource_id)
        if not current or current.row_version != version:
            return None
        value = replace(current, is_active=False, is_default=False, row_version=version + 1)
        self.payments[resource_id] = value
        if current.is_default:
            candidates = sorted((x for x in self.list_payment_methods(account_id) if x.is_active), key=lambda x: x.payment_method_id)
            if candidates:
                promoted = candidates[0]
                self.payments[promoted.payment_method_id] = replace(promoted, is_default=True, row_version=promoted.row_version + 1)
        return value
