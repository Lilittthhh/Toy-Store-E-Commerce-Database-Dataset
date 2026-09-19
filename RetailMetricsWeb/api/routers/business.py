from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from api.schemas.business import (
    DeleteResponse,
    OrderCreate,
    OrderItemCreate,
    OrderItemResponse,
    OrderItemUpdate,
    OrderResponse,
    OrderUpdate,
    OriginFilter,
    PageResponse,
    ProductCreate,
    ProductResponse,
    ProductUpdate,
    RefundCreate,
    RefundResponse,
    RefundUpdate,
    WebsitePageviewResponse,
    WebsiteSessionResponse,
)
from core.dependencies import (
    get_business_repository,
    get_business_service,
    get_current_user,
    require_roles,
)
from core.models import AppUser, Role
from repositories.business_repository import BusinessRepository
from services.business_service import BusinessService
from services.audit import set_entity_id


router = APIRouter(tags=["business data"])
ALL_ROLES = (Role.ADMIN, Role.OPERATIONS_STAFF, Role.ANALYST)
OPERATIONS_ROLES = (Role.ADMIN, Role.OPERATIONS_STAFF)


def origin_clause(origin: OriginFilter) -> list[str]:
    if origin == OriginFilter.IMPORTED:
        return ["record_origin = 'imported'"]
    if origin == OriginFilter.WEB:
        return ["record_origin = 'staff'"]
    if origin == OriginFilter.CUSTOMER:
        return ["record_origin = 'customer'"]
    return []


def page(items: list[dict[str, Any]], total: int, limit: int, offset: int):
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def get_or_404(repository: BusinessRepository, entity: str, entity_id: int):
    row = repository.get(entity, entity_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Record not found.")
    return row


@router.get("/products", response_model=PageResponse[ProductResponse])
def list_products(
    search: str | None = Query(default=None, max_length=200),
    origin: OriginFilter = OriginFilter.ALL,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: AppUser = Depends(require_roles(*ALL_ROLES)),
    repository: BusinessRepository = Depends(get_business_repository),
):
    clauses, params = origin_clause(origin), []
    if search:
        clauses.append("product_name ILIKE %s")
        params.append(f"%{search.strip()}%")
    items, total = repository.list_mutable("products", clauses, params, limit, offset)
    return page(items, total, limit, offset)


@router.get("/products/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, _: AppUser = Depends(require_roles(*ALL_ROLES)), repository: BusinessRepository = Depends(get_business_repository)):
    return get_or_404(repository, "products", product_id)


@router.post("/products", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(request: ProductCreate, http_request: Request, user: AppUser = Depends(require_roles(Role.ADMIN)), service: BusinessService = Depends(get_business_service)):
    result = service.create("products", request.model_dump(), user.app_user_id)
    set_entity_id(http_request, result["product_id"])
    return result


@router.put("/products/{product_id}", response_model=ProductResponse)
def update_product(product_id: int, request: ProductUpdate, _: AppUser = Depends(require_roles(Role.ADMIN)), service: BusinessService = Depends(get_business_service)):
    data = request.model_dump(exclude={"row_version"})
    return service.update("products", product_id, data, request.row_version)


@router.delete("/products/{product_id}", response_model=DeleteResponse)
def delete_product(product_id: int, row_version: int = Query(ge=1), _: AppUser = Depends(require_roles(Role.ADMIN)), service: BusinessService = Depends(get_business_service)):
    service.delete("products", product_id, row_version)
    return DeleteResponse(deleted_id=product_id, message="Product deleted.")


@router.get("/orders", response_model=PageResponse[OrderResponse])
def list_orders(
    website_session_id: int | None = Query(default=None, ge=1),
    user_id: int | None = Query(default=None, ge=1),
    primary_product_id: int | None = Query(default=None, ge=1),
    origin: OriginFilter = OriginFilter.ALL,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: AppUser = Depends(require_roles(*ALL_ROLES)),
    repository: BusinessRepository = Depends(get_business_repository),
):
    clauses, params = origin_clause(origin), []
    for column, value in (("website_session_id", website_session_id), ("user_id", user_id), ("primary_product_id", primary_product_id)):
        if value is not None:
            clauses.append(f"{column} = %s")
            params.append(value)
    items, total = repository.list_mutable("orders", clauses, params, limit, offset)
    return page(items, total, limit, offset)


@router.get("/orders/{order_id}", response_model=OrderResponse)
def get_order(order_id: int, _: AppUser = Depends(require_roles(*ALL_ROLES)), repository: BusinessRepository = Depends(get_business_repository)):
    return get_or_404(repository, "orders", order_id)


@router.post("/orders", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def create_order(request: OrderCreate, user: AppUser = Depends(require_roles(*OPERATIONS_ROLES)), service: BusinessService = Depends(get_business_service)):
    return service.create("orders", request.model_dump(), user.app_user_id)


@router.put("/orders/{order_id}", response_model=OrderResponse)
def update_order(order_id: int, request: OrderUpdate, _: AppUser = Depends(require_roles(*OPERATIONS_ROLES)), service: BusinessService = Depends(get_business_service)):
    return service.update("orders", order_id, request.model_dump(exclude={"row_version"}), request.row_version)


@router.delete("/orders/{order_id}", response_model=DeleteResponse)
def delete_order(order_id: int, row_version: int = Query(ge=1), _: AppUser = Depends(require_roles(*OPERATIONS_ROLES)), service: BusinessService = Depends(get_business_service)):
    service.delete("orders", order_id, row_version)
    return DeleteResponse(deleted_id=order_id, message="Order deleted.")


@router.get("/order-items", response_model=PageResponse[OrderItemResponse])
def list_order_items(
    order_id: int | None = Query(default=None, ge=1),
    product_id: int | None = Query(default=None, ge=1),
    origin: OriginFilter = OriginFilter.ALL,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: AppUser = Depends(require_roles(*ALL_ROLES)),
    repository: BusinessRepository = Depends(get_business_repository),
):
    clauses, params = origin_clause(origin), []
    if order_id is not None:
        clauses.append("order_id = %s"); params.append(order_id)
    if product_id is not None:
        clauses.append("product_id = %s"); params.append(product_id)
    items, total = repository.list_mutable("order_items", clauses, params, limit, offset)
    return page(items, total, limit, offset)


@router.get("/order-items/{order_item_id}", response_model=OrderItemResponse)
def get_order_item(order_item_id: int, _: AppUser = Depends(require_roles(*ALL_ROLES)), repository: BusinessRepository = Depends(get_business_repository)):
    return get_or_404(repository, "order_items", order_item_id)


@router.post("/order-items", response_model=OrderItemResponse, status_code=status.HTTP_201_CREATED)
def create_order_item(request: OrderItemCreate, user: AppUser = Depends(require_roles(*OPERATIONS_ROLES)), service: BusinessService = Depends(get_business_service)):
    return service.create("order_items", request.model_dump(), user.app_user_id)


@router.put("/order-items/{order_item_id}", response_model=OrderItemResponse)
def update_order_item(order_item_id: int, request: OrderItemUpdate, _: AppUser = Depends(require_roles(*OPERATIONS_ROLES)), service: BusinessService = Depends(get_business_service)):
    return service.update("order_items", order_item_id, request.model_dump(exclude={"row_version"}), request.row_version)


@router.delete("/order-items/{order_item_id}", response_model=DeleteResponse)
def delete_order_item(order_item_id: int, row_version: int = Query(ge=1), _: AppUser = Depends(require_roles(*OPERATIONS_ROLES)), service: BusinessService = Depends(get_business_service)):
    service.delete("order_items", order_item_id, row_version)
    return DeleteResponse(deleted_id=order_item_id, message="Order item deleted.")


@router.get("/refunds", response_model=PageResponse[RefundResponse])
def list_refunds(
    order_id: int | None = Query(default=None, ge=1),
    order_item_id: int | None = Query(default=None, ge=1),
    origin: OriginFilter = OriginFilter.ALL,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: AppUser = Depends(require_roles(*ALL_ROLES)),
    repository: BusinessRepository = Depends(get_business_repository),
):
    clauses, params = origin_clause(origin), []
    if order_id is not None:
        clauses.append("order_id = %s"); params.append(order_id)
    if order_item_id is not None:
        clauses.append("order_item_id = %s"); params.append(order_item_id)
    items, total = repository.list_mutable("order_item_refunds", clauses, params, limit, offset)
    return page(items, total, limit, offset)


@router.get("/refunds/{refund_id}", response_model=RefundResponse)
def get_refund(refund_id: int, _: AppUser = Depends(require_roles(*ALL_ROLES)), repository: BusinessRepository = Depends(get_business_repository)):
    return get_or_404(repository, "order_item_refunds", refund_id)


@router.post("/refunds", response_model=RefundResponse, status_code=status.HTTP_201_CREATED)
def create_refund(request: RefundCreate, user: AppUser = Depends(require_roles(*OPERATIONS_ROLES)), service: BusinessService = Depends(get_business_service)):
    return service.create("order_item_refunds", request.model_dump(), user.app_user_id)


@router.put("/refunds/{refund_id}", response_model=RefundResponse)
def update_refund(refund_id: int, request: RefundUpdate, _: AppUser = Depends(require_roles(*OPERATIONS_ROLES)), service: BusinessService = Depends(get_business_service)):
    return service.update("order_item_refunds", refund_id, request.model_dump(exclude={"row_version"}), request.row_version)


@router.delete("/refunds/{refund_id}", response_model=DeleteResponse)
def delete_refund(refund_id: int, row_version: int = Query(ge=1), _: AppUser = Depends(require_roles(*OPERATIONS_ROLES)), service: BusinessService = Depends(get_business_service)):
    service.delete("order_item_refunds", refund_id, row_version)
    return DeleteResponse(deleted_id=refund_id, message="Refund deleted.")


@router.get("/website-sessions", response_model=PageResponse[WebsiteSessionResponse])
def list_sessions(
    user_id: int | None = Query(default=None, ge=1),
    utm_source: str | None = Query(default=None, max_length=200),
    device_type: str | None = Query(default=None, max_length=100),
    has_order: bool | None = Query(
        default=None,
        description="Filter to sessions with or without an existing order.",
    ),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: AppUser = Depends(require_roles(*ALL_ROLES)),
    repository: BusinessRepository = Depends(get_business_repository),
):
    clauses, params = [], []
    for column, value in (("user_id", user_id), ("utm_source", utm_source), ("device_type", device_type)):
        if value is not None:
            clauses.append(f"{column} = %s"); params.append(value)
    if has_order is not None:
        predicate = "EXISTS" if has_order else "NOT EXISTS"
        clauses.append(
            f"{predicate} (SELECT 1 FROM public.orders o "
            "WHERE o.website_session_id = website_sessions.website_session_id)"
        )
    items, total = repository.list_readonly("website_sessions", "website_session_id", clauses, params, limit, offset)
    return page(items, total, limit, offset)


@router.get("/website-sessions/{website_session_id}", response_model=WebsiteSessionResponse)
def get_session(website_session_id: int, _: AppUser = Depends(require_roles(*ALL_ROLES)), repository: BusinessRepository = Depends(get_business_repository)):
    row = repository.get_readonly("website_sessions", "website_session_id", website_session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Website session not found.")
    return row


@router.get("/website-pageviews", response_model=PageResponse[WebsitePageviewResponse])
def list_pageviews(
    website_session_id: int | None = Query(default=None, ge=1),
    search: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: AppUser = Depends(require_roles(*ALL_ROLES)),
    repository: BusinessRepository = Depends(get_business_repository),
):
    clauses, params = [], []
    if website_session_id is not None:
        clauses.append("website_session_id = %s"); params.append(website_session_id)
    if search:
        clauses.append("pageview_url ILIKE %s"); params.append(f"%{search.strip()}%")
    items, total = repository.list_readonly("website_pageviews", "website_pageview_id", clauses, params, limit, offset)
    return page(items, total, limit, offset)


@router.get("/website-pageviews/{website_pageview_id}", response_model=WebsitePageviewResponse)
def get_pageview(website_pageview_id: int, _: AppUser = Depends(require_roles(*ALL_ROLES)), repository: BusinessRepository = Depends(get_business_repository)):
    row = repository.get_readonly("website_pageviews", "website_pageview_id", website_pageview_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Website pageview not found.")
    return row
