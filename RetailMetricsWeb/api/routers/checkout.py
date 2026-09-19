from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Request

from api.schemas.checkout import (
    CancelOrderRequest, CheckoutRequest, CustomerOrderDetailResponse,
    CustomerOrderSummaryResponse,
)
from core.dependencies import get_checkout_service, require_customer
from core.models import CustomerAccount
from services.checkout_service import CheckoutService
from services.audit import set_entity_id


router = APIRouter(prefix="/customer", tags=["Customer checkout and orders"])


@router.post("/checkout", response_model=CustomerOrderDetailResponse, status_code=201)
def checkout(request: CheckoutRequest, http_request: Request, customer: CustomerAccount = Depends(require_customer), service: CheckoutService = Depends(get_checkout_service)):
    result = service.checkout(customer, request.address_id, request.payment_method_id, request.cart_row_version)
    set_entity_id(http_request, result["order_id"])
    return result


@router.get("/orders", response_model=list[CustomerOrderSummaryResponse])
def list_orders(customer: CustomerAccount = Depends(require_customer), service: CheckoutService = Depends(get_checkout_service)):
    return service.list_orders(customer)


@router.get("/orders/{order_id}", response_model=CustomerOrderDetailResponse)
def get_order(order_id: int = Path(gt=0), customer: CustomerAccount = Depends(require_customer), service: CheckoutService = Depends(get_checkout_service)):
    return service.get_order(customer, order_id)


@router.post("/orders/{order_id}/cancel", response_model=CustomerOrderDetailResponse)
def cancel_order(request: CancelOrderRequest, order_id: int = Path(gt=0), customer: CustomerAccount = Depends(require_customer), service: CheckoutService = Depends(get_checkout_service)):
    return service.cancel_order(customer, order_id, request.row_version)


@router.post("/orders/{order_id}/confirm-delivery", response_model=CustomerOrderDetailResponse)
def confirm_delivery(request: CancelOrderRequest, order_id: int = Path(gt=0), customer: CustomerAccount = Depends(require_customer), service: CheckoutService = Depends(get_checkout_service)):
    return service.confirm_delivery(customer, order_id, request.row_version)
