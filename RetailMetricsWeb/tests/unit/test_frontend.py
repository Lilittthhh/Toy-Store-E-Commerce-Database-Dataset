from __future__ import annotations

import httpx
import pytest

from frontend.api_client import APIClient, APIError
from frontend.auth import can_manage_users, can_mutate
from frontend.navigation import (
    INTERNAL_MODULE_NAMES,
    PUBLIC_NAVIGATION,
    ROLE_SECTIONS,
    navigation_for_role,
)
from frontend.ui import format_money, format_status, format_value, source_label
from frontend.views.entity_views import (
    _analyst_product_rows,
    _order_customer_label,
    _order_table_rows,
    _refund_table_rows,
)
from frontend.views.readonly_views import _pageview_rows, _session_rows


def test_api_client_sends_bearer_token_and_decodes_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer signed-token"
        assert request.url.params["limit"] == "10"
        return httpx.Response(200, json={"items": [], "total": 0})

    client = APIClient(
        base_url="http://testserver",
        token="signed-token",
        transport=httpx.MockTransport(handler),
    )
    assert client.get("/products", {"limit": 10})["total"] == 0


def test_api_client_converts_validation_and_conflict_errors() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"detail": "Stale row_version."})

    client = APIClient(base_url="http://testserver", transport=httpx.MockTransport(handler))
    with pytest.raises(APIError) as raised:
        client.put("/products/1", {"row_version": 1})
    assert raised.value.status_code == 409
    assert raised.value.message == "Stale row_version."


@pytest.mark.parametrize(
    ("role", "entity", "allowed"),
    [
        ("admin", "products", True),
        ("admin", "orders", False),
        ("admin", "order_items", False),
        ("admin", "refunds", False),
        ("operations_staff", "products", False),
        ("operations_staff", "orders", False),
        ("operations_staff", "order_items", False),
        ("operations_staff", "refunds", False),
        ("analyst", "orders", False),
    ],
)
def test_frontend_mutation_visibility(role: str, entity: str, allowed: bool) -> None:
    assert can_mutate(entity, role) is allowed


def test_only_admin_sees_user_management() -> None:
    assert can_manage_users("admin") is True
    assert can_manage_users("operations_staff") is False
    assert can_manage_users("analyst") is False


def test_custom_navigation_contains_only_user_facing_routes() -> None:
    assert navigation_for_role("admin") == (
        "Dashboard", "User Management", "Customer Accounts", "Audit Trail", "Notification Test", "Customers", "Products",
        "Storefront Catalog", "Orders", "Refund Requests", "Refunds", "Website Traffic",
        "Analytics Dashboard", "Business Reports", "Project Evidence", "My Account", "Logout",
    )
    assert navigation_for_role("analyst")[0] == "Analytics Dashboard"
    assert "Customers" in navigation_for_role("operations_staff")
    assert navigation_for_role("operations_staff") == (
        "Dashboard", "Customers", "Orders", "Refund Requests", "Refunds",
        "Products", "Storefront Catalog", "My Account", "Logout",
    )
    assert navigation_for_role("analyst") == (
        "Analytics Dashboard", "Customers", "Products", "Orders", "Refunds",
        "Website Traffic", "Business Reports", "My Account", "Logout",
    )
    assert "Project Evidence" in navigation_for_role("admin")
    assert "Project Evidence" not in navigation_for_role("analyst")
    assert "User Management" not in navigation_for_role("operations_staff")
    assert "User Management" not in navigation_for_role("analyst")
    assert "Storefront Catalog" not in navigation_for_role("analyst")
    assert "Order Items" not in navigation_for_role("admin")
    assert "Website Sessions" not in navigation_for_role("admin")
    assert "Website Pageviews" not in navigation_for_role("admin")
    assert "Order Items" not in navigation_for_role("operations_staff")
    assert "Website Sessions" not in navigation_for_role("operations_staff")
    assert "Website Pageviews" not in navigation_for_role("operations_staff")
    assert "Order Items" not in navigation_for_role("analyst")
    displayed = (*PUBLIC_NAVIGATION, *navigation_for_role("admin"))
    assert not INTERNAL_MODULE_NAMES.intersection(displayed)


def test_website_traffic_uses_business_labels_and_no_raw_nulls() -> None:
    session = _session_rows([{
        "website_session_id": 21,
        "created_at": "2013-01-01T08:00:00+00:00",
        "user_id": 818,
        "is_repeat_session": True,
        "utm_source": "gsearch",
        "utm_campaign": None,
        "utm_content": None,
        "device_type": "desktop",
        "http_referer": None,
    }])[0]
    pageview = _pageview_rows([{
        "website_pageview_id": 31,
        "created_at": "2013-01-01T08:01:00+00:00",
        "website_session_id": 21,
        "pageview_url": "/home",
    }])[0]

    assert list(session) == [
        "Session #", "Date", "Historical Shopper", "Repeat Visit", "Traffic Source",
        "Campaign", "Content", "Device", "Referrer",
    ]
    assert session["Repeat Visit"] == "Yes"
    assert session["Campaign"] == "—"
    assert session["Referrer"] == "—"
    assert None not in session.values()
    assert list(pageview) == ["Pageview #", "Date", "Session #", "Page"]


def test_customer_created_order_uses_safe_registered_customer_projection() -> None:
    source = {
        "order_id": 70001,
        "created_at": "2026-09-12T08:00:00+00:00",
        "website_session_id": None,
        "user_id": None,
        "customer_account_id": 105,
        "primary_product_id": 1,
        "items_purchased": 1,
        "price_usd": "49.99",
        "cogs_usd": "19.49",
        "order_status": "pending",
        "origin": "customer",
    }

    rendered = _order_table_rows([source], "admin")[0]

    assert rendered["Customer"] == "Customer #105"
    assert rendered["Website Session"] == "Not applicable"
    assert None not in rendered.values()
    assert "user_id" not in rendered
    assert "customer_account_id" not in rendered


def test_imported_order_uses_historical_shopper_and_real_session() -> None:
    source = {
        "order_id": 10,
        "created_at": "2013-01-01T08:00:00+00:00",
        "website_session_id": 4242,
        "user_id": 818,
        "customer_account_id": None,
        "primary_product_id": 1,
        "items_purchased": 1,
        "price_usd": "49.99",
        "cogs_usd": "19.49",
        "order_status": None,
        "origin": "imported",
    }

    rendered = _order_table_rows([source], "operations_staff")[0]

    assert rendered["Customer"] == "Historical Shopper #818"
    assert rendered["Website Session"] == "4242"
    assert None not in rendered.values()


def test_analyst_customer_order_label_remains_deidentified() -> None:
    row = {"origin": "customer", "customer_account_id": 105, "user_id": None}

    label = _order_customer_label(row, "analyst")

    assert label == "Customer #105"
    assert "@" not in label


def test_analyst_business_entity_projections_are_compact_and_read_only() -> None:
    product = _analyst_product_rows(
        [{"product_id": 1, "product_name": "Toy", "origin": "imported"}],
        [{"product_id": 1, "orders": 5, "units": 6, "revenue": "100.00", "cogs": "40.00", "refunds": "5.00"}],
    )[0]
    refund = _refund_table_rows([{
        "order_item_refund_id": 8,
        "order_id": 12,
        "refund_amount_usd": "5.00",
        "created_at": "2013-01-01T08:00:00+00:00",
        "origin": "imported",
    }], "analyst")[0]

    assert list(product) == ["Product", "Revenue", "Orders", "Units", "Gross profit", "Refunds", "Source"]
    assert product["Gross profit"] == "$60.00"
    assert product["Source"] == "Historical data"
    assert "Customer-created" not in product.values()
    assert list(refund) == ["Refund #", "Order #", "Amount", "Date", "Source"]


@pytest.mark.parametrize(
    ("stored", "displayed"),
    [
        ("pending", "Pending"), ("processing", "Processing"),
        ("ready_shipped", "Ready / Shipped"), ("delivered", "Delivered"),
        ("cancelled", "Cancelled"),
        ("refunded", "Refunded"), ("paid", "Paid"),
        ("partially_refunded", "Partially Refunded"),
        ("approved", "Approved"), ("rejected", "Rejected"),
        ("processed", "Processed"), ("active", "Active"),
        ("inactive", "Inactive"), ("locked", "Locked"),
    ],
)
def test_shared_status_formatter_uses_business_labels(stored: str, displayed: str) -> None:
    assert format_status(stored) == displayed


def test_shared_null_money_and_source_formatters() -> None:
    assert format_value(None) == "—"
    assert format_value("") == "—"
    assert format_value(None, "Not applicable") == "Not applicable"
    assert format_money(None) == "—"
    assert format_money("12.5") == "$12.50"
    assert source_label({"origin": "imported"}) == "Historical data"
    assert source_label({"origin": "customer"}) == "Customer-created"
    assert source_label({"origin": "staff"}) == "Application-created"
    assert source_label({"origin": "web"}) == "Application-created"


def test_imported_order_status_is_historical_not_missing() -> None:
    row = {
        "order_id": 10, "created_at": "2013-01-01T08:00:00+00:00",
        "website_session_id": 44, "user_id": 12, "customer_account_id": None,
        "primary_product_id": 1, "items_purchased": 1, "price_usd": "49.99",
        "cogs_usd": "19.49", "order_status": None, "origin": "imported",
    }
    assert _order_table_rows([row], "analyst")[0]["Status"] == "Historical record"
