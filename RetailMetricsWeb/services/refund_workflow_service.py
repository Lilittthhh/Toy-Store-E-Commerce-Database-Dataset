from __future__ import annotations

from decimal import Decimal

from fastapi import HTTPException

from core.models import AppUser, CustomerAccount
from repositories.refund_workflow_repository import (
    RefundWorkflowConflict, RefundWorkflowNotFound, RefundWorkflowRepository,
)


class RefundWorkflowService:
    def __init__(self, repository: RefundWorkflowRepository, outbox=None):
        self.repository = repository
        self.outbox = outbox

    @staticmethod
    def _call(operation, *args):
        try:
            return operation(*args)
        except RefundWorkflowNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RefundWorkflowConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    def create_request(self, customer: CustomerAccount, order_item_id: int, amount: Decimal, reason: str):
        result = self._call(self.repository.create_request, customer.customer_account_id, order_item_id, amount, reason)
        if self.outbox:
            self.outbox.queue_refund("refund_request_submitted", result["refund_request_id"])
        return result

    def list_customer_requests(self, customer: CustomerAccount):
        return self.repository.list_customer_requests(customer.customer_account_id)

    def get_customer_request(self, customer: CustomerAccount, request_id: int):
        result = self.repository.get_customer_request(customer.customer_account_id, request_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Refund request not found.")
        return result

    def eligibility(self, customer: CustomerAccount, order_id: int):
        return self._call(self.repository.eligibility, customer.customer_account_id, order_id)

    def get_staff_request(self, request_id: int):
        result = self.repository.get_staff_request(request_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Refund request not found.")
        return result

    def list_staff_requests(self, status_filter: str | None, limit: int, offset: int):
        return self.repository.list_staff_requests(status_filter, limit, offset)

    def approve(self, request_id: int, row_version: int, reviewer: AppUser, note: str | None):
        return self._call(self.repository.approve, request_id, row_version, reviewer.app_user_id, note)

    def reject(self, request_id: int, row_version: int, reviewer: AppUser, note: str):
        result = self._call(self.repository.reject, request_id, row_version, reviewer.app_user_id, note)
        if self.outbox:
            self.outbox.queue_refund("refund_rejected", request_id)
        return result

    def process(self, request_id: int, row_version: int, processor: AppUser):
        result = self._call(self.repository.process, request_id, row_version, processor.app_user_id)
        if self.outbox:
            self.outbox.queue_refund("refund_processed", request_id)
        return result
