from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from api.schemas.business import OrderCreate, OrderItemCreate, ProductCreate, RefundCreate
from repositories.business_repository import ENTITIES
from services.business_service import BusinessService


class FakeBusinessRepository:
    def __init__(self):
        self.current = None
        self.exists = True
        self.session_has_order = False
        self.session_user_id = 50
        self.order_origin = "staff"
        self.item = {"order_item_id": 1, "order_id": 10, "price_usd": Decimal("20.00")}
        self.refunds = Decimal("0")

    def get(self, entity, entity_id):
        return self.current

    def relation_exists(self, table, pk, value):
        return self.exists

    def order_for_session_exists(self, session_id, exclude_id=None):
        return self.session_has_order

    def get_session_user_id(self, session_id):
        return self.session_user_id

    def get_order_record_origin(self, order_id):
        return self.order_origin

    def get_order_item_for_refund(self, order_item_id, lock=False):
        return self.item

    def refunded_total(self, order_item_id, exclude_refund_id=None):
        return self.refunds


def test_creator_attribution_is_not_accepted_from_clients() -> None:
    with pytest.raises(ValidationError):
        ProductCreate.model_validate(
            {
                "created_at": "2026-01-01T00:00:00",
                "product_name": "Demo",
                "created_by_app_user_id": 999,
            }
        )


@pytest.mark.parametrize(
    ("schema", "payload", "server_fields"),
    [
        (
            ProductCreate,
            {"created_at": "2026-01-01T00:00:00", "product_name": "Demo"},
            {"record_origin": "customer"},
        ),
        (
            OrderCreate,
            {
                "created_at": "2026-01-01T00:00:00",
                "website_session_id": 1,
                "user_id": 50,
                "primary_product_id": 1,
                "items_purchased": 1,
                "price_usd": "10.00",
                "cogs_usd": "4.00",
            },
            {"record_origin": "customer", "order_status": "pending"},
        ),
        (
            OrderItemCreate,
            {
                "created_at": "2026-01-01T00:00:00",
                "order_id": 1,
                "product_id": 1,
                "is_primary_item": 1,
                "price_usd": "10.00",
                "cogs_usd": "4.00",
            },
            {"record_origin": "customer"},
        ),
        (
            RefundCreate,
            {
                "created_at": "2026-01-01T00:00:00",
                "order_item_id": 1,
                "order_id": 1,
                "refund_amount_usd": "1.00",
            },
            {"record_origin": "customer", "refund_request_id": 1},
        ),
    ],
)
def test_migration002_lifecycle_fields_are_not_accepted_from_clients(
    schema, payload, server_fields
) -> None:
    with pytest.raises(ValidationError):
        schema.model_validate({**payload, **server_fields})


@pytest.mark.parametrize(
    ("entity", "expected"),
    [
        ("products", (("record_origin", "staff"),)),
        ("orders", (("record_origin", "staff"), ("order_status", "ready_shipped"))),
        ("order_items", (("record_origin", "staff"),)),
        (
            "order_item_refunds",
            (("record_origin", "staff"), ("refund_request_id", None)),
        ),
    ],
)
def test_staff_create_constants_are_server_controlled(entity, expected) -> None:
    assert ENTITIES[entity].create_constants == expected


def test_order_item_requires_staff_origin_parent() -> None:
    repository = FakeBusinessRepository()
    repository.order_origin = "imported"
    service = BusinessService(repository)

    with pytest.raises(HTTPException) as raised:
        service.validate(
            "order_items",
            {"order_id": 10, "product_id": 1},
        )

    assert raised.value.status_code == 409
    assert raised.value.detail == (
        "Order items can only be added to application-created staff orders."
    )


@pytest.mark.parametrize(
    ("current", "expected_status"),
    [
        (None, 404),
        ({"created_by_app_user_id": None, "record_origin": "imported", "row_version": 1}, 403),
        ({"created_by_app_user_id": 4, "record_origin": "staff", "row_version": 2}, 409),
        ({"created_by_app_user_id": 4, "record_origin": "customer", "row_version": 1}, 403),
    ],
)
def test_mutation_precheck_distinguishes_missing_canonical_and_stale(
    current, expected_status
) -> None:
    repository = FakeBusinessRepository()
    repository.current = current
    service = BusinessService(repository)
    with pytest.raises(HTTPException) as raised:
        service._ensure_mutable_version("products", 1, 1)
    assert raised.value.status_code == expected_status


def test_duplicate_order_is_conflict() -> None:
    repository = FakeBusinessRepository()
    repository.session_has_order = True
    service = BusinessService(repository)
    with pytest.raises(HTTPException) as raised:
        service.validate(
            "orders",
            {"website_session_id": 1, "user_id": 50, "primary_product_id": 1},
        )
    assert raised.value.status_code == 409


def test_refund_requires_matching_order_and_respects_cumulative_price() -> None:
    repository = FakeBusinessRepository()
    service = BusinessService(repository)
    with pytest.raises(HTTPException, match="must match"):
        service.validate(
            "order_item_refunds",
            {"order_item_id": 1, "order_id": 11, "refund_amount_usd": Decimal("1")},
        )

    repository.refunds = Decimal("15.00")
    with pytest.raises(HTTPException, match="cannot exceed"):
        service.validate(
            "order_item_refunds",
            {"order_item_id": 1, "order_id": 10, "refund_amount_usd": Decimal("6")},
        )
