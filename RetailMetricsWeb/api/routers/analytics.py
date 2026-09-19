from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from core.dependencies import get_analytics_service, require_roles
from core.models import AppUser, Role
from services.analytics_service import AnalyticsService


router = APIRouter(tags=["Staff analytics and customer intelligence"])
STAFF = (Role.ADMIN, Role.OPERATIONS_STAFF, Role.ANALYST)


@router.get("/analytics/dashboard")
def dashboard(scope: str = Query(default="imported"), _: AppUser = Depends(require_roles(*STAFF)), service: AnalyticsService = Depends(get_analytics_service)):
    return service.dashboard(scope)


@router.get("/analytics/workspace")
def workspace(_: AppUser = Depends(require_roles(*STAFF)), service: AnalyticsService = Depends(get_analytics_service)):
    return service.workspace()


@router.get("/analytics/reports")
def reports(_: AppUser = Depends(require_roles(*STAFF)), service: AnalyticsService = Depends(get_analytics_service)):
    return service.reports()


@router.get("/staff/customers/historical")
def historical_customers(search: str | None = Query(default=None, max_length=32), limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0), _: AppUser = Depends(require_roles(*STAFF)), service: AnalyticsService = Depends(get_analytics_service)):
    return service.historical_customers(search, limit, offset)


@router.get("/staff/customers/historical/{dataset_user_id}")
def historical_customer(dataset_user_id: int, _: AppUser = Depends(require_roles(*STAFF)), service: AnalyticsService = Depends(get_analytics_service)):
    return service.historical_detail(dataset_user_id)


@router.get("/staff/customers/registered")
def registered_customers(search: str | None = Query(default=None, max_length=254), limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0), user: AppUser = Depends(require_roles(*STAFF)), service: AnalyticsService = Depends(get_analytics_service)):
    return service.registered_customers(user.role, search, limit, offset)
