from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from api.schemas.admin_customers import AdminCustomerResponse, CustomerStatusUpdate, CustomerUnlockRequest
from api.schemas.business import PageResponse
from core.dependencies import get_admin_customer_service, get_customer_repository, require_roles
from core.models import AppUser, Role
from repositories.customer_repository import CustomerRepository
from services.admin_customer_service import AdminCustomerService
from services.audit import set_change_values


router = APIRouter(prefix="/admin/customers", tags=["Admin customer management"])


@router.get("", response_model=PageResponse[AdminCustomerResponse])
def list_customers(
    search: str | None = Query(default=None, max_length=254),
    is_active: bool | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: AppUser = Depends(require_roles(Role.ADMIN)),
    repository: CustomerRepository = Depends(get_customer_repository),
):
    identities, total = repository.list_identities(search, is_active, limit, offset)
    return {"items": [AdminCustomerResponse.from_identity(value) for value in identities], "total": total, "limit": limit, "offset": offset}


@router.get("/{customer_account_id}", response_model=AdminCustomerResponse)
def get_customer(customer_account_id: int, _: AppUser = Depends(require_roles(Role.ADMIN)), service: AdminCustomerService = Depends(get_admin_customer_service)) -> AdminCustomerResponse:
    return AdminCustomerResponse.from_identity(service.get_customer(customer_account_id))


@router.put("/{customer_account_id}/status", response_model=AdminCustomerResponse)
def change_status(customer_account_id: int, request: CustomerStatusUpdate, http_request: Request, _: AppUser = Depends(require_roles(Role.ADMIN)), service: AdminCustomerService = Depends(get_admin_customer_service)) -> AdminCustomerResponse:
    previous = service.get_customer(customer_account_id)
    result = service.change_active(customer_account_id, request.is_active, request.row_version)
    set_change_values(http_request, old={"is_active": previous.account.is_active}, new={"is_active": result.account.is_active})
    return AdminCustomerResponse.from_identity(result)


@router.post("/{customer_account_id}/unlock", response_model=AdminCustomerResponse)
def unlock(customer_account_id: int, request: CustomerUnlockRequest, _: AppUser = Depends(require_roles(Role.ADMIN)), service: AdminCustomerService = Depends(get_admin_customer_service)) -> AdminCustomerResponse:
    return AdminCustomerResponse.from_identity(service.unlock(customer_account_id, request.row_version))
