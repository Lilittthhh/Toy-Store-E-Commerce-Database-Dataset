from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query, Request, status

from api.schemas.refund_workflow import (
    CustomerRefundRequestCreate, CustomerRefundRequestResponse,
    RefundEligibilityResponse, RefundProcessRequest, RefundRejectRequest,
    RefundRequestPage, RefundRequestStatus, RefundReviewRequest,
    StaffRefundRequestResponse,
)
from core.dependencies import get_refund_workflow_service, require_customer, require_roles
from core.models import AppUser, CustomerAccount, Role
from services.refund_workflow_service import RefundWorkflowService
from services.audit import set_entity_id


router = APIRouter(tags=["Refund request workflow"])
ALL_STAFF_ROLES = (Role.ADMIN, Role.OPERATIONS_STAFF, Role.ANALYST)
REVIEW_ROLES = (Role.ADMIN, Role.OPERATIONS_STAFF)


@router.post("/customer/refund-requests", response_model=CustomerRefundRequestResponse, status_code=status.HTTP_201_CREATED)
def create_customer_refund_request(request: CustomerRefundRequestCreate, http_request: Request, customer: CustomerAccount = Depends(require_customer), service: RefundWorkflowService = Depends(get_refund_workflow_service)):
    result = service.create_request(customer, request.order_item_id, request.requested_amount, request.reason)
    set_entity_id(http_request, result["refund_request_id"])
    return result


@router.get("/customer/refund-requests", response_model=list[CustomerRefundRequestResponse])
def list_customer_refund_requests(customer: CustomerAccount = Depends(require_customer), service: RefundWorkflowService = Depends(get_refund_workflow_service)):
    return service.list_customer_requests(customer)


@router.get("/customer/refund-requests/{request_id}", response_model=CustomerRefundRequestResponse)
def get_customer_refund_request(request_id: int = Path(gt=0), customer: CustomerAccount = Depends(require_customer), service: RefundWorkflowService = Depends(get_refund_workflow_service)):
    return service.get_customer_request(customer, request_id)


@router.get("/customer/orders/{order_id}/refund-eligibility", response_model=list[RefundEligibilityResponse])
def customer_refund_eligibility(order_id: int = Path(gt=0), customer: CustomerAccount = Depends(require_customer), service: RefundWorkflowService = Depends(get_refund_workflow_service)):
    return service.eligibility(customer, order_id)


@router.get("/refund-requests", response_model=RefundRequestPage)
def list_staff_refund_requests(status_filter: RefundRequestStatus | None = Query(default=None), limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0), _: AppUser = Depends(require_roles(*ALL_STAFF_ROLES)), service: RefundWorkflowService = Depends(get_refund_workflow_service)):
    items, total = service.list_staff_requests(status_filter.value if status_filter else None, limit, offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/refund-requests/{request_id}", response_model=StaffRefundRequestResponse)
def get_staff_refund_request(request_id: int = Path(gt=0), _: AppUser = Depends(require_roles(*ALL_STAFF_ROLES)), service: RefundWorkflowService = Depends(get_refund_workflow_service)):
    return service.get_staff_request(request_id)


@router.post("/refund-requests/{request_id}/approve", response_model=StaffRefundRequestResponse)
def approve_refund_request(request: RefundReviewRequest, request_id: int = Path(gt=0), user: AppUser = Depends(require_roles(*REVIEW_ROLES)), service: RefundWorkflowService = Depends(get_refund_workflow_service)):
    return service.approve(request_id, request.row_version, user, request.resolution_note)


@router.post("/refund-requests/{request_id}/reject", response_model=StaffRefundRequestResponse)
def reject_refund_request(request: RefundRejectRequest, request_id: int = Path(gt=0), user: AppUser = Depends(require_roles(*REVIEW_ROLES)), service: RefundWorkflowService = Depends(get_refund_workflow_service)):
    return service.reject(request_id, request.row_version, user, request.resolution_note)


@router.post("/refund-requests/{request_id}/process", response_model=StaffRefundRequestResponse)
def process_refund_request(request: RefundProcessRequest, request_id: int = Path(gt=0), user: AppUser = Depends(require_roles(*REVIEW_ROLES)), service: RefundWorkflowService = Depends(get_refund_workflow_service)):
    return service.process(request_id, request.row_version, user)
