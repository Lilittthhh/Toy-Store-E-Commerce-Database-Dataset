from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query

from api.schemas.order_workflow import (
    CustomerOrderWorkflowStatus, OrderTransitionRequest,
    StaffCustomerOrderPage, StaffCustomerOrderResponse,
)
from core.dependencies import get_order_workflow_service, require_roles
from core.models import AppUser, Role
from services.order_workflow_service import OrderWorkflowService


router = APIRouter(tags=["Customer order operations workflow"])
ALL_STAFF_ROLES = (Role.ADMIN, Role.OPERATIONS_STAFF, Role.ANALYST)
OPERATIONS_ROLES = (Role.ADMIN, Role.OPERATIONS_STAFF)


@router.get("/order-workflow/orders", response_model=StaffCustomerOrderPage)
def list_customer_orders(status_filter: CustomerOrderWorkflowStatus | None = Query(default=None), limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0), _: AppUser = Depends(require_roles(*ALL_STAFF_ROLES)), service: OrderWorkflowService = Depends(get_order_workflow_service)):
    items, total = service.list_customer_orders(status_filter.value if status_filter else None, limit, offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def _transition(action: str, order_id: int, request: OrderTransitionRequest, user: AppUser, service: OrderWorkflowService):
    return service.transition(order_id, request.row_version, action, user)


@router.post("/orders/{order_id}/start-processing", response_model=StaffCustomerOrderResponse)
def start_processing(request: OrderTransitionRequest, order_id: int = Path(gt=0), user: AppUser = Depends(require_roles(*OPERATIONS_ROLES)), service: OrderWorkflowService = Depends(get_order_workflow_service)):
    return _transition("start-processing", order_id, request, user, service)


@router.post("/orders/{order_id}/ready-shipped", response_model=StaffCustomerOrderResponse)
def mark_ready_shipped(request: OrderTransitionRequest, order_id: int = Path(gt=0), user: AppUser = Depends(require_roles(*OPERATIONS_ROLES)), service: OrderWorkflowService = Depends(get_order_workflow_service)):
    return _transition("ready-shipped", order_id, request, user, service)


@router.post("/orders/{order_id}/cancel", response_model=StaffCustomerOrderResponse)
def cancel_customer_order(request: OrderTransitionRequest, order_id: int = Path(gt=0), user: AppUser = Depends(require_roles(*OPERATIONS_ROLES)), service: OrderWorkflowService = Depends(get_order_workflow_service)):
    return _transition("cancel", order_id, request, user, service)
