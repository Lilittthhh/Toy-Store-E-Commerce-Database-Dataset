from __future__ import annotations

import os
from decimal import Decimal

import psycopg2
import pytest

from core.config import Settings
from repositories.analytics_repository import PostgresAnalyticsRepository


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def repository():
    if os.getenv("RUN_DB_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_DB_INTEGRATION_TESTS=1 to use PostgreSQL")
    conn = psycopg2.connect(**Settings.from_environment().database_kwargs())
    try:
        yield PostgresAnalyticsRepository(conn)
    finally:
        conn.rollback()
        conn.close()


def test_imported_kpis_match_verified_baseline(repository):
    result = repository.dashboard("imported")
    metrics = result["metrics"]
    assert metrics["sessions"] == 472_871
    assert metrics["orders"] == 32_313
    assert metrics["gross_revenue"] == Decimal("1938509.75")
    assert metrics["cogs"] == Decimal("722370.25")
    assert metrics["gross_profit"] == Decimal("1216139.50")
    assert metrics["refund_amount"] == Decimal("85338.69")
    assert metrics["net_revenue"] == Decimal("1853171.06")
    assert round(metrics["conversion_rate"], 2) == Decimal("6.83")
    assert sum(row["sessions"] for row in result["traffic_sources"]) == 472_871
    assert sum(row["sessions"] for row in result["devices"]) == 472_871


def test_scope_separation_aggregate_shapes_and_limits(repository):
    imported = repository.dashboard("imported")
    application = repository.dashboard("application")
    combined = repository.dashboard("combined")
    assert application["metrics"]["sessions"] == 0
    assert application["metrics"]["conversion_rate"] is None
    assert combined["metrics"]["orders"] == imported["metrics"]["orders"] + application["metrics"]["orders"]
    assert len(imported["products"]) >= 4
    rows, total = repository.list_historical_customers(None, 10, 0)
    assert len(rows) <= 10 and total >= len(rows)
    assert all("email" not in row for row in rows)
    if rows:
        detail = repository.historical_customer_detail(rows[0]["dataset_user_id"])
        assert detail is not None
        assert len(detail["recent_orders"]) <= 10
        assert len(detail["recent_sessions"]) <= 10
    registered, registered_total = repository.list_registered_customers(None, 10, 0)
    assert len(registered) <= 10 and registered_total >= len(registered)
    workspace = repository.workspace()
    assert set(("active_staff", "active_customers", "locked_accounts", "orders_needing_action")) <= set(workspace)
