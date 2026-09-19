from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from psycopg2 import errors

from core.models import AppUser, CartItem, CatalogProduct, CustomerAccount, ShoppingCart
from repositories.storefront_repository import CartQuantityExceeded, StorefrontRepository


class StorefrontService:
    def __init__(self, repository: StorefrontRepository):
        self.repository = repository

    def list_catalog(self) -> list[CatalogProduct]:
        return self.repository.list_catalog()

    def get_catalog(self, product_id: int) -> CatalogProduct:
        product = self.repository.get_catalog_product(product_id)
        if product is None:
            raise HTTPException(status_code=404, detail="Product not found.")
        return product

    def configure_catalog(self, product_id: int, values: dict[str, Any], user: AppUser, row_version: int | None) -> CatalogProduct:
        current = self.get_catalog(product_id)
        if current.is_configured:
            if row_version is None or row_version != current.row_version:
                raise HTTPException(status_code=409, detail=f"Stale row_version: expected {row_version}, current value is {current.row_version}.")
        elif row_version is not None:
            raise HTTPException(status_code=409, detail="Catalog configuration does not exist yet; omit row_version for the first configuration.")
        try:
            updated = self.repository.configure_catalog(product_id, values, user.app_user_id, row_version)
        except errors.UniqueViolation as exc:
            raise HTTPException(status_code=409, detail="Catalog configuration was created concurrently. Refresh and retry.") from exc
        if updated is None:
            current = self.get_catalog(product_id)
            raise HTTPException(status_code=409, detail=f"Stale row_version: expected {row_version}, current value is {current.row_version}.")
        return updated

    def list_store_products(self, search: str | None) -> list[CatalogProduct]:
        cleaned = search.strip() if search else None
        return self.repository.list_store_products(cleaned or None)

    def get_store_product(self, product_id: int) -> CatalogProduct:
        product = self.repository.get_store_product(product_id)
        if product is None:
            raise HTTPException(status_code=404, detail="Storefront product not found or unavailable.")
        return product

    def cart(self, customer: CustomerAccount) -> ShoppingCart:
        return self.repository.get_cart(customer.customer_account_id)

    def add_to_cart(self, customer: CustomerAccount, product_id: int, quantity: int) -> CartItem:
        product = self.get_store_product(product_id)
        try:
            return self.repository.add_cart_item(customer.customer_account_id, product_id, quantity, product.current_price_usd)
        except CartQuantityExceeded as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except errors.UniqueViolation as exc:
            raise HTTPException(status_code=409, detail="The cart changed concurrently. Refresh and retry.") from exc

    def update_cart_item(self, customer: CustomerAccount, item_id: int, quantity: int, row_version: int) -> CartItem:
        current = self._get_owned_item(customer, item_id)
        self._check_version(current.row_version, row_version)
        updated = self.repository.update_cart_item(customer.customer_account_id, item_id, quantity, row_version)
        if updated is None:
            return self._raise_item_conflict(customer, item_id, row_version)
        return updated

    def remove_cart_item(self, customer: CustomerAccount, item_id: int, row_version: int) -> None:
        current = self._get_owned_item(customer, item_id)
        self._check_version(current.row_version, row_version)
        if not self.repository.delete_cart_item(customer.customer_account_id, item_id, row_version):
            self._raise_item_conflict(customer, item_id, row_version)

    def _get_owned_item(self, customer: CustomerAccount, item_id: int) -> CartItem:
        item = self.repository.get_cart_item(customer.customer_account_id, item_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Cart item not found.")
        return item

    def _raise_item_conflict(self, customer: CustomerAccount, item_id: int, expected: int):
        current = self._get_owned_item(customer, item_id)
        self._check_version(current.row_version, expected)
        raise HTTPException(status_code=409, detail="Cart item changed during the request.")

    @staticmethod
    def _check_version(current: int, expected: int) -> None:
        if current != expected:
            raise HTTPException(status_code=409, detail=f"Stale row_version: expected {expected}, current value is {current}.")
