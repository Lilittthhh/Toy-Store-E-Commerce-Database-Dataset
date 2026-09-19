from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from repositories.checkout_repository import PostgresCheckoutRepository
from services.checkout_service import CheckoutService


class FakeOrderCursor:
    def __init__(self, db):
        self.db = db
        self.rowcount = 0
        self.selected = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params):
        self.db.queries.append((query, params))
        if "SELECT order_status,row_version" in query:
            order_id, customer_id = params
            self.selected = (
                {"order_status": self.db.status, "row_version": self.db.version}
                if (order_id, customer_id) == (81, 9) else None
            )
        elif "UPDATE public.orders SET order_status='delivered'" in query:
            order_id, customer_id, version = params
            self.rowcount = int(
                (order_id, customer_id, version) == (81, 9, self.db.version)
                and self.db.status == "ready_shipped"
            )
            if self.rowcount:
                self.db.status = "delivered"
                self.db.version += 1
                self.db.confirmed = True

    def fetchone(self):
        return self.selected


class FakeOrderDb:
    def __init__(self, status="ready_shipped", version=3):
        self.status = status
        self.version = version
        self.confirmed = False
        self.queries = []

    def cursor(self, **kwargs):
        return FakeOrderCursor(self)


class FakeCheckoutRepository(PostgresCheckoutRepository):
    def get_order(self, customer_id, order_id):
        assert (customer_id, order_id) == (9, 81)
        return {"order_id": 81, "order_status": self.conn.status,
                "row_version": self.conn.version,
                "delivered_confirmed_by_customer": self.conn.confirmed}


@pytest.mark.parametrize("status", ["pending", "processing", "delivered", "cancelled", "refunded"])
def test_customer_cannot_confirm_from_invalid_state(status):
    db = FakeOrderDb(status)
    service = CheckoutService(FakeCheckoutRepository(db))
    with pytest.raises(HTTPException) as error:
        service.confirm_delivery(SimpleNamespace(customer_account_id=9), 81, 3)
    assert error.value.status_code == 409
    assert db.status == status
    assert not db.confirmed


def test_confirm_delivery_is_owner_scoped_versioned_and_queues_one_event():
    db = FakeOrderDb()
    queued = []
    outbox = SimpleNamespace(queue_order=lambda event, order: queued.append((event, order)))
    service = CheckoutService(FakeCheckoutRepository(db), outbox)
    foreign = SimpleNamespace(customer_account_id=10)
    with pytest.raises(HTTPException) as foreign_error:
        service.confirm_delivery(foreign, 81, 3)
    assert foreign_error.value.status_code == 404
    owner = SimpleNamespace(customer_account_id=9)
    with pytest.raises(HTTPException) as stale_error:
        service.confirm_delivery(owner, 81, 2)
    assert stale_error.value.status_code == 409
    result = service.confirm_delivery(owner, 81, 3)
    assert result == {"order_id": 81, "order_status": "delivered", "row_version": 4,
                      "delivered_confirmed_by_customer": True}
    assert queued == [("order_delivered", 81)]
    assert any("FOR UPDATE" in query for query, _ in db.queries)
    assert any("record_origin='customer'" in query for query, _ in db.queries)
    with pytest.raises(HTTPException) as repeat_error:
        service.confirm_delivery(owner, 81, 4)
    assert repeat_error.value.status_code == 409
    assert queued == [("order_delivered", 81)]
