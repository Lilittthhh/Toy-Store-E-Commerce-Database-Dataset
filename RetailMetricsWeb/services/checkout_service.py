from __future__ import annotations

from fastapi import HTTPException

from core.models import CustomerAccount
from repositories.checkout_repository import (
    CheckoutConflict, CheckoutRepository, CheckoutResourceNotFound,
    CustomerOrderConflict, CustomerOrderNotFound,
)


class CheckoutService:
    def __init__(self, repository: CheckoutRepository, outbox=None):
        self.repository = repository
        self.outbox = outbox

    def checkout(self, customer: CustomerAccount, address_id: int, payment_method_id: int, cart_version: int) -> dict:
        try:
            order = self.repository.checkout(customer.customer_account_id, address_id, payment_method_id, cart_version)
            if self.outbox:
                self.outbox.queue_order("order_confirmation", order["order_id"])
            return order
        except CheckoutResourceNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except CheckoutConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    def list_orders(self, customer: CustomerAccount) -> list[dict]:
        return self.repository.list_orders(customer.customer_account_id)

    def get_order(self, customer: CustomerAccount, order_id: int) -> dict:
        result = self.repository.get_order(customer.customer_account_id, order_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Order not found.")
        return result

    def cancel_order(self, customer: CustomerAccount, order_id: int, row_version: int) -> dict:
        try:
            result = self.repository.cancel_order(customer.customer_account_id, order_id, row_version)
            if self.outbox:
                self.outbox.queue_order("order_cancelled", order_id)
            return result
        except CustomerOrderNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except CustomerOrderConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    def confirm_delivery(self, customer: CustomerAccount, order_id: int, row_version: int) -> dict:
        try:
            result = self.repository.confirm_delivery(customer.customer_account_id, order_id, row_version)
            if self.outbox:
                self.outbox.queue_order("order_delivered", order_id)
            return result
        except CustomerOrderNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except CustomerOrderConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
