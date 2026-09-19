from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, status

from api.schemas.admin_users import (
    AdminUserCreate,
    AdminUserResponse,
    UserRoleUpdate,
    UserStatusUpdate,
    UserUnlockRequest,
)
from api.schemas.business import PageResponse
from core.dependencies import get_admin_user_service, get_user_repository, require_roles
from core.models import AppUser, Role
from repositories.user_repository import UserRepository
from services.admin_user_service import AdminUserService
from services.audit import set_change_values, set_entity_id


router = APIRouter(prefix="/admin/users", tags=["Admin user management"])


@router.get("", response_model=PageResponse[AdminUserResponse])
def list_users(
    search: str | None = Query(default=None, max_length=254),
    role: Role | None = None,
    is_active: bool | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: AppUser = Depends(require_roles(Role.ADMIN)),
    repository: UserRepository = Depends(get_user_repository),
):
    users, total = repository.list_users(search, role, is_active, limit, offset)
    return {
        "items": [AdminUserResponse.from_user(user) for user in users],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{app_user_id}", response_model=AdminUserResponse)
def get_user(
    app_user_id: int,
    _: AppUser = Depends(require_roles(Role.ADMIN)),
    service: AdminUserService = Depends(get_admin_user_service),
):
    return AdminUserResponse.from_user(service.get_user(app_user_id))


@router.post("", response_model=AdminUserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    request: AdminUserCreate,
    http_request: Request,
    _: AppUser = Depends(require_roles(Role.ADMIN)),
    service: AdminUserService = Depends(get_admin_user_service),
):
    result = AdminUserResponse.from_user(
        service.create_user(
            request.username,
            str(request.email),
            request.password.get_secret_value(),
            request.role,
        )
    )
    set_entity_id(http_request, result.app_user_id)
    return result


@router.put("/{app_user_id}/role", response_model=AdminUserResponse)
def change_role(
    app_user_id: int,
    request: UserRoleUpdate,
    http_request: Request,
    actor: AppUser = Depends(require_roles(Role.ADMIN)),
    service: AdminUserService = Depends(get_admin_user_service),
):
    previous = service.get_user(app_user_id)
    result = service.change_role(actor, app_user_id, request.role, request.row_version)
    set_change_values(http_request, old={"role": previous.role.value}, new={"role": result.role.value})
    return AdminUserResponse.from_user(result)


@router.put("/{app_user_id}/status", response_model=AdminUserResponse)
def change_status(
    app_user_id: int,
    request: UserStatusUpdate,
    http_request: Request,
    actor: AppUser = Depends(require_roles(Role.ADMIN)),
    service: AdminUserService = Depends(get_admin_user_service),
):
    previous = service.get_user(app_user_id)
    result = service.change_active(actor, app_user_id, request.is_active, request.row_version)
    set_change_values(http_request, old={"is_active": previous.is_active}, new={"is_active": result.is_active})
    return AdminUserResponse.from_user(result)


@router.post("/{app_user_id}/unlock", response_model=AdminUserResponse)
def unlock_user(
    app_user_id: int,
    request: UserUnlockRequest,
    _: AppUser = Depends(require_roles(Role.ADMIN)),
    service: AdminUserService = Depends(get_admin_user_service),
):
    return AdminUserResponse.from_user(service.unlock(app_user_id, request.row_version))
