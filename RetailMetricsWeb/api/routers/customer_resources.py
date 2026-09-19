from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Request

from api.schemas.customer_resources import (
    CustomerAddressCreate, CustomerAddressResponse, CustomerAddressUpdate,
    PaymentMethodCreate, PaymentMethodResponse, PaymentMethodUpdate, VersionRequest,
)
from core.dependencies import get_customer_resource_service, require_customer
from core.models import CustomerAccount
from services.customer_resource_service import CustomerResourceService
from services.audit import set_entity_id


router = APIRouter(prefix="/customer", tags=["Customer saved resources"])


@router.get("/addresses", response_model=list[CustomerAddressResponse])
def list_addresses(account: CustomerAccount = Depends(require_customer), service: CustomerResourceService = Depends(get_customer_resource_service)):
    return [CustomerAddressResponse.from_model(value) for value in service.list_addresses(account)]


@router.post("/addresses", response_model=CustomerAddressResponse, status_code=201)
def create_address(request: CustomerAddressCreate, http_request: Request, account: CustomerAccount = Depends(require_customer), service: CustomerResourceService = Depends(get_customer_resource_service)):
    values = request.model_dump(exclude={"is_default"})
    result = CustomerAddressResponse.from_model(service.create_address(account, values, request.is_default))
    set_entity_id(http_request, result.customer_address_id)
    return result


@router.get("/addresses/{address_id}", response_model=CustomerAddressResponse)
def get_address(address_id: int = Path(gt=0), account: CustomerAccount = Depends(require_customer), service: CustomerResourceService = Depends(get_customer_resource_service)):
    return CustomerAddressResponse.from_model(service.get_address(account, address_id))


@router.put("/addresses/{address_id}", response_model=CustomerAddressResponse)
def update_address(request: CustomerAddressUpdate, address_id: int = Path(gt=0), account: CustomerAccount = Depends(require_customer), service: CustomerResourceService = Depends(get_customer_resource_service)):
    values = request.model_dump(exclude={"row_version"})
    return CustomerAddressResponse.from_model(service.update_address(account, address_id, values, request.row_version))


@router.post("/addresses/{address_id}/set-default", response_model=CustomerAddressResponse)
def set_default_address(request: VersionRequest, address_id: int = Path(gt=0), account: CustomerAccount = Depends(require_customer), service: CustomerResourceService = Depends(get_customer_resource_service)):
    return CustomerAddressResponse.from_model(service.set_default_address(account, address_id, request.row_version))


@router.post("/addresses/{address_id}/deactivate", response_model=CustomerAddressResponse)
def deactivate_address(request: VersionRequest, address_id: int = Path(gt=0), account: CustomerAccount = Depends(require_customer), service: CustomerResourceService = Depends(get_customer_resource_service)):
    return CustomerAddressResponse.from_model(service.deactivate_address(account, address_id, request.row_version))


@router.get("/payment-methods", response_model=list[PaymentMethodResponse])
def list_payment_methods(account: CustomerAccount = Depends(require_customer), service: CustomerResourceService = Depends(get_customer_resource_service)):
    return [PaymentMethodResponse.from_model(value) for value in service.list_payment_methods(account)]


@router.post("/payment-methods", response_model=PaymentMethodResponse, status_code=201)
def create_payment_method(request: PaymentMethodCreate, http_request: Request, account: CustomerAccount = Depends(require_customer), service: CustomerResourceService = Depends(get_customer_resource_service)):
    values = service.payment_values(request.method_type, request.card_brand, request.card_last_four)
    result = PaymentMethodResponse.from_model(service.create_payment_method(account, values, request.is_default))
    set_entity_id(http_request, result.payment_method_id)
    return result


@router.get("/payment-methods/{payment_method_id}", response_model=PaymentMethodResponse)
def get_payment_method(payment_method_id: int = Path(gt=0), account: CustomerAccount = Depends(require_customer), service: CustomerResourceService = Depends(get_customer_resource_service)):
    return PaymentMethodResponse.from_model(service.get_payment_method(account, payment_method_id))


@router.put("/payment-methods/{payment_method_id}", response_model=PaymentMethodResponse)
def update_payment_method(request: PaymentMethodUpdate, payment_method_id: int = Path(gt=0), account: CustomerAccount = Depends(require_customer), service: CustomerResourceService = Depends(get_customer_resource_service)):
    values = service.payment_values(request.method_type, request.card_brand, request.card_last_four)
    return PaymentMethodResponse.from_model(service.update_payment_method(account, payment_method_id, values, request.row_version))


@router.post("/payment-methods/{payment_method_id}/set-default", response_model=PaymentMethodResponse)
def set_default_payment_method(request: VersionRequest, payment_method_id: int = Path(gt=0), account: CustomerAccount = Depends(require_customer), service: CustomerResourceService = Depends(get_customer_resource_service)):
    return PaymentMethodResponse.from_model(service.set_default_payment_method(account, payment_method_id, request.row_version))


@router.post("/payment-methods/{payment_method_id}/deactivate", response_model=PaymentMethodResponse)
def deactivate_payment_method(request: VersionRequest, payment_method_id: int = Path(gt=0), account: CustomerAccount = Depends(require_customer), service: CustomerResourceService = Depends(get_customer_resource_service)):
    return PaymentMethodResponse.from_model(service.deactivate_payment_method(account, payment_method_id, request.row_version))
