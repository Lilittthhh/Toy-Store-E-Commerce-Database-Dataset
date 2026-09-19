from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from psycopg2 import errors

from repositories.business_repository import BusinessRepository


ENTITY_LABELS = {
    "products": "Product",
    "orders": "Order",
    "order_items": "Order item",
    "order_item_refunds": "Refund",
}


class BusinessService:
    def __init__(self, repository: BusinessRepository):
        self.repository = repository

    def require_fk(self, table: str, pk: str, value: int | None, field: str) -> None:
        if value is not None and not self.repository.relation_exists(table, pk, value):
            raise HTTPException(status_code=422, detail=f"{field} does not reference an existing {table} row.")

    def validate(self, entity: str, data: dict[str, Any], entity_id: int | None = None) -> None:
        if entity == "orders":
            session_user_id = self.repository.get_session_user_id(data["website_session_id"])
            if session_user_id is None:
                raise HTTPException(status_code=422, detail="website_session_id does not reference an existing website_sessions row.")
            if session_user_id != data["user_id"]:
                raise HTTPException(status_code=422, detail="user_id must match the referenced website session's user_id.")
            self.require_fk("products", "product_id", data["primary_product_id"], "primary_product_id")
            if self.repository.order_for_session_exists(data["website_session_id"], entity_id):
                raise HTTPException(status_code=409, detail="An order already exists for this website_session_id.")
        elif entity == "order_items":
            parent_origin = self.repository.get_order_record_origin(data["order_id"])
            if parent_origin is None:
                raise HTTPException(
                    status_code=422,
                    detail="order_id does not reference an existing orders row.",
                )
            if parent_origin != "staff":
                raise HTTPException(
                    status_code=409,
                    detail="Order items can only be added to application-created staff orders.",
                )
            self.require_fk("products", "product_id", data["product_id"], "product_id")
        elif entity == "order_item_refunds":
            self.require_fk("orders", "order_id", data["order_id"], "order_id")
            item = self.repository.get_order_item_for_refund(data["order_item_id"], lock=True)
            if item is None:
                raise HTTPException(status_code=422, detail="order_item_id does not reference an existing order_items row.")
            if int(item["order_id"]) != data["order_id"]:
                raise HTTPException(status_code=422, detail="order_id must match the referenced order item's order_id.")
            previous = Decimal(self.repository.refunded_total(data["order_item_id"], entity_id))
            if previous + Decimal(data["refund_amount_usd"]) > Decimal(item["price_usd"]):
                raise HTTPException(status_code=422, detail="Total refunds cannot exceed the related order-item price.")

    def create(self, entity: str, data: dict[str, Any], creator_id: int):
        self.validate(entity, data)
        try:
            return self.repository.create(entity, data, creator_id)
        except errors.UniqueViolation as exc:
            if entity == "orders":
                raise HTTPException(status_code=409, detail="An order already exists for this website_session_id.") from exc
            raise HTTPException(status_code=409, detail=f"Duplicate {ENTITY_LABELS[entity].lower()} value.") from exc
        except errors.ForeignKeyViolation as exc:
            raise HTTPException(status_code=422, detail="A referenced record no longer exists.") from exc

    def update(self, entity: str, entity_id: int, data: dict[str, Any], row_version: int):
        self._ensure_mutable_version(entity, entity_id, row_version)
        self.validate(entity, data, entity_id)
        try:
            row = self.repository.update(entity, entity_id, data, row_version)
        except errors.UniqueViolation as exc:
            raise HTTPException(status_code=409, detail="An order already exists for this website_session_id.") from exc
        except errors.ForeignKeyViolation as exc:
            raise HTTPException(status_code=422, detail="A referenced record no longer exists.") from exc
        if row is None:
            self._raise_mutation_failure(entity, entity_id, row_version)
        return row

    def delete(self, entity: str, entity_id: int, row_version: int) -> None:
        self._ensure_mutable_version(entity, entity_id, row_version)
        try:
            deleted = self.repository.delete(entity, entity_id, row_version)
        except errors.ForeignKeyViolation as exc:
            raise HTTPException(status_code=409, detail="Record is still referenced; delete dependent web rows first.") from exc
        if not deleted:
            self._raise_mutation_failure(entity, entity_id, row_version)

    def _ensure_mutable_version(self, entity: str, entity_id: int, expected: int) -> None:
        current = self.repository.get(entity, entity_id)
        label = ENTITY_LABELS[entity]
        if current is None:
            raise HTTPException(status_code=404, detail=f"{label} not found.")
        if current["record_origin"] != "staff":
            raise HTTPException(status_code=403, detail=f"Only staff-created {label.lower()} rows can use generic CRUD mutations.")
        if int(current["row_version"]) != expected:
            raise HTTPException(
                status_code=409,
                detail=f"Stale row_version: expected {expected}, current value is {current['row_version']}.",
            )

    def _raise_mutation_failure(self, entity: str, entity_id: int, expected: int) -> None:
        current = self.repository.get(entity, entity_id)
        label = ENTITY_LABELS[entity]
        if current is None:
            raise HTTPException(status_code=404, detail=f"{label} not found.")
        if current["record_origin"] != "staff":
            raise HTTPException(status_code=403, detail=f"Only staff-created {label.lower()} rows can use generic CRUD mutations.")
        raise HTTPException(
            status_code=409,
            detail=f"Stale row_version: expected {expected}, current value is {current['row_version']}.",
        )
