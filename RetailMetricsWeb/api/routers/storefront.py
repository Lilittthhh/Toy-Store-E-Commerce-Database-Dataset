from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query, Request, Response

from api.schemas.storefront import (
    AdminCatalogResponse, CartItemAddRequest, CartItemResponse, CartItemUpdateRequest,
    CartResponse, CatalogConfigureRequest, StorefrontProductResponse,
)
from core.dependencies import get_current_user, get_storefront_service, require_customer, require_roles
from core.models import AppUser, CustomerAccount, Role
from services.storefront_service import StorefrontService
from services.audit import set_entity_id


router = APIRouter(tags=["Storefront and cart"])


@router.get("/admin/catalog", response_model=list[AdminCatalogResponse])
def list_catalog(_: AppUser = Depends(get_current_user), service: StorefrontService = Depends(get_storefront_service)):
    return [AdminCatalogResponse.from_model(value) for value in service.list_catalog()]


@router.get("/admin/catalog/{product_id}", response_model=AdminCatalogResponse)
def get_catalog(product_id: int = Path(gt=0), _: AppUser = Depends(get_current_user), service: StorefrontService = Depends(get_storefront_service)):
    return AdminCatalogResponse.from_model(service.get_catalog(product_id))


@router.put("/admin/catalog/{product_id}", response_model=AdminCatalogResponse)
def configure_catalog(request: CatalogConfigureRequest, product_id: int = Path(gt=0), user: AppUser = Depends(require_roles(Role.ADMIN)), service: StorefrontService = Depends(get_storefront_service)):
    values = request.model_dump(exclude={"row_version"})
    values["image_url"] = str(request.image_url) if request.image_url else None
    return AdminCatalogResponse.from_model(service.configure_catalog(product_id, values, user, request.row_version))


@router.get("/customer/store/products", response_model=list[StorefrontProductResponse])
def list_store_products(search: str | None = Query(default=None, max_length=100), _: CustomerAccount = Depends(require_customer), service: StorefrontService = Depends(get_storefront_service)):
    return [StorefrontProductResponse.from_model(value) for value in service.list_store_products(search)]


@router.get("/customer/store/products/{product_id}", response_model=StorefrontProductResponse)
def get_store_product(product_id: int = Path(gt=0), _: CustomerAccount = Depends(require_customer), service: StorefrontService = Depends(get_storefront_service)):
    return StorefrontProductResponse.from_model(service.get_store_product(product_id))


@router.get("/customer/cart", response_model=CartResponse)
def get_cart(customer: CustomerAccount = Depends(require_customer), service: StorefrontService = Depends(get_storefront_service)):
    return CartResponse.from_cart(service.cart(customer))


@router.post("/customer/cart/items", response_model=CartItemResponse, status_code=201)
def add_cart_item(request: CartItemAddRequest, http_request: Request, customer: CustomerAccount = Depends(require_customer), service: StorefrontService = Depends(get_storefront_service)):
    result = CartItemResponse.from_model(service.add_to_cart(customer, request.product_id, request.quantity))
    set_entity_id(http_request, result.cart_item_id)
    return result


@router.put("/customer/cart/items/{cart_item_id}", response_model=CartItemResponse)
def update_cart_item(request: CartItemUpdateRequest, cart_item_id: int = Path(gt=0), customer: CustomerAccount = Depends(require_customer), service: StorefrontService = Depends(get_storefront_service)):
    return CartItemResponse.from_model(service.update_cart_item(customer, cart_item_id, request.quantity, request.row_version))


@router.delete("/customer/cart/items/{cart_item_id}", status_code=204)
def remove_cart_item(cart_item_id: int = Path(gt=0), row_version: int = Query(ge=1), customer: CustomerAccount = Depends(require_customer), service: StorefrontService = Depends(get_storefront_service)):
    service.remove_cart_item(customer, cart_item_id, row_version)
    return Response(status_code=204)
