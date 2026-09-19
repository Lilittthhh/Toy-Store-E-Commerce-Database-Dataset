from __future__ import annotations

import logging

from fastapi import HTTPException

from core.models import AppUser
from repositories.order_workflow_repository import (
    OrderWorkflowConflict, OrderWorkflowNotFound, OrderWorkflowRepository,
)


logger = logging.getLogger(__name__)


class OrderWorkflowService:
    def __init__(self, repository: OrderWorkflowRepository, outbox=None):
        self.repository = repository
        self.outbox = outbox

    def list_customer_orders(self, status_filter: str | None, limit: int, offset: int):
        return self.repository.list_customer_orders(status_filter, limit, offset)

    def transition(self, order_id: int, row_version: int, action: str, actor: AppUser):
        try:
            result, previous_status = self.repository.transition(order_id, row_version, action)
        except OrderWorkflowNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except OrderWorkflowConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        logger.info(
            "customer order lifecycle transition actor=%s order=%s from=%s to=%s",
            actor.app_user_id,
            order_id,
            previous_status,
            result["order_status"],
        )
        if self.outbox:
            self.outbox.queue_order({
                "start-processing": "order_processing",
                "ready-shipped": "order_ready_shipped",
                "cancel": "order_cancelled",
            }[action], order_id)
        return result
