from __future__ import annotations

from fastapi import APIRouter, Depends

from api.schemas.customer_profile import CustomerProfileResponse, CustomerProfileUpdate
from core.dependencies import get_customer_auth_service, require_customer
from core.models import CustomerAccount
from services.customer_auth_service import CustomerAuthService


router = APIRouter(prefix="/customer/profile", tags=["Customer profile"])


@router.get("", response_model=CustomerProfileResponse)
def get_profile(account: CustomerAccount = Depends(require_customer), service: CustomerAuthService = Depends(get_customer_auth_service)) -> CustomerProfileResponse:
    return CustomerProfileResponse.from_profile(service.get_profile(account))


@router.put("", response_model=CustomerProfileResponse)
def update_profile(request: CustomerProfileUpdate, account: CustomerAccount = Depends(require_customer), service: CustomerAuthService = Depends(get_customer_auth_service)) -> CustomerProfileResponse:
    profile = service.update_profile(
        account, request.first_name, request.last_name, request.phone, request.row_version
    )
    return CustomerProfileResponse.from_profile(profile)
