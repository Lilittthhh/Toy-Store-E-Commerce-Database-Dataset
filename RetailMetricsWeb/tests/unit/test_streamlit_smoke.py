from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from frontend.api_client import APIClient, APIError
from frontend.navigation import (
    CUSTOMER_ACCOUNT_NAVIGATION,
    INTERNAL_MODULE_NAMES,
    navigation_for_role,
)


APP_FILE = Path(__file__).resolve().parents[2] / "frontend" / "app.py"


def _navigate(app: AppTest, label: str) -> AppTest:
    next(button for button in app.sidebar.button if button.label == label).click().run(timeout=20)
    return app


def _assert_no_generic_transaction_crud(app: AppTest, create_label: str) -> None:
    """Assert against the actual rendered widget tree, not only permission helpers."""
    assert "Create new" not in [tab.label for tab in app.tabs]
    assert "Update or delete" not in [tab.label for tab in app.tabs]
    assert create_label.lower() not in [button.label.lower() for button in app.button]
    assert create_label.lower() not in [heading.value.lower() for heading in app.subheader]


def test_anonymous_streamlit_pages_render_without_runtime_errors() -> None:
    app = AppTest.from_file(str(APP_FILE)).run(timeout=20)
    assert not app.exception
    assert not app.sidebar.radio
    assert not app.sidebar.button
    assert not app.sidebar.markdown
    styles = " ".join(item.value for item in app.markdown)
    assert 'data-testid="stSidebar"' in styles
    assert 'data-testid="stSidebarCollapsedControl"' in styles
    assert not app.radio
    assert [title.value for title in app.title] == ["Welcome back"]
    assert {item.label for item in app.text_input} >= {"Email or username", "Password"}
    assert "Show password" in [item.label for item in app.checkbox]
    assert "Sign In" in [button.label for button in app.button]
    rendered = " ".join(item.value for item in app.markdown)
    for removed in ("Customer Portal", "Staff Portal", "Customer Login", "Customer Register"):
        assert removed not in rendered

    next(button for button in app.button if button.label == "Create an account").click().run(timeout=20)
    assert not app.exception
    assert [title.value for title in app.title] == ["Create your customer account"]

    next(button for button in app.button if button.label == "Back to sign in").click().run(timeout=20)
    next(button for button in app.button if button.label == "Forgot password?").click().run(timeout=20)
    assert not app.exception
    assert [title.value for title in app.title] == ["Password recovery"]


@pytest.mark.parametrize("role", ["admin", "operations_staff", "analyst"])
def test_successful_staff_login_restores_role_navigation(monkeypatch, role: str) -> None:
    role_state = {"role": role}
    get = _fake_get(role_state)

    def post(_: APIClient, path: str, payload=None):
        if path == "/auth/login":
            return {"access_token": "signed-staff-token", "token_type": "bearer", "expires_in": 1800}
        raise AssertionError(path)

    monkeypatch.setattr(APIClient, "get", get)
    monkeypatch.setattr(APIClient, "post", post)
    app = AppTest.from_file(str(APP_FILE)).run(timeout=20)
    assert not app.sidebar.button
    next(item for item in app.text_input if item.label == "Email or username").set_value("operator")
    next(item for item in app.text_input if item.label == "Password").set_value("not-used-by-mock")
    next(button for button in app.button if button.label == "Sign In").click().run(timeout=20)

    assert not app.exception
    assert app.session_state["access_token"] == "signed-staff-token"
    assert tuple(button.label for button in app.sidebar.button) == navigation_for_role(role)


def test_successful_customer_login_restores_customer_navigation(monkeypatch) -> None:
    def get(_: APIClient, path: str, params=None):
        if path == "/customer/auth/me":
            return {
                "customer_account_id": 105,
                "email": "customer@example.com",
                "is_active": True,
                "first_name": "Presentation",
                "last_name": "Customer",
            }
        if path == "/customer/store/products":
            return []
        raise AssertionError(path)

    def post(_: APIClient, path: str, payload=None):
        if path == "/auth/login":
            raise APIError(401, "Invalid staff credentials")
        if path == "/customer/auth/login":
            return {"access_token": "signed-customer-token", "token_type": "bearer", "expires_in": 1800}
        raise AssertionError(path)

    monkeypatch.setattr(APIClient, "get", get)
    monkeypatch.setattr(APIClient, "post", post)
    app = AppTest.from_file(str(APP_FILE)).run(timeout=20)
    assert not app.sidebar.button
    next(item for item in app.text_input if item.label == "Email or username").set_value("customer@example.com")
    next(item for item in app.text_input if item.label == "Password").set_value("not-used-by-mock")
    next(button for button in app.button if button.label == "Sign In").click().run(timeout=20)

    assert not app.exception
    assert app.session_state["customer_access_token"] == "signed-customer-token"
    assert tuple(button.label for button in app.sidebar.button) == CUSTOMER_ACCOUNT_NAVIGATION


def test_unified_login_failure_is_generic(monkeypatch) -> None:
    def reject(*args, **kwargs):
        raise APIError(401, "Store-specific account detail must remain hidden")

    monkeypatch.setattr(APIClient, "post", reject)
    app = AppTest.from_file(str(APP_FILE)).run(timeout=20)
    next(item for item in app.text_input if item.label == "Email or username").set_value(
        "unknown@example.com"
    )
    next(item for item in app.text_input if item.label == "Password").set_value("wrong-password")
    next(button for button in app.button if button.label == "Sign In").click().run(timeout=20)

    assert not app.exception
    errors = " ".join(item.value for item in app.error)
    assert "Invalid username/email or password." in errors
    assert "Store-specific" not in errors


def _fake_get(role_state):
    def get(_: APIClient, path: str, params=None):
        if path == "/auth/me":
            return {
                "app_user_id": 1,
                "username": "presentation_user",
                "email": "presentation@example.com",
                "role": role_state["role"],
                "is_active": True,
                "locked_until": None,
                "last_login_at": "2026-09-05T09:30:00+00:00",
                "password_changed_at": "2026-09-01T09:30:00+00:00",
                "created_at": "2026-09-01T09:30:00+00:00",
                "updated_at": "2026-09-05T09:30:00+00:00",
            }
        if path == "/admin/catalog":
            return []
        if path == "/admin/notifications/config":
            return {
                "mode": "live", "email_provider": "smtp", "email_live_enabled": True,
                "smtp_host_configured": True, "smtp_port_configured": True,
                "smtp_username_configured": True, "smtp_password_configured": True,
                "smtp_sender_configured": True, "sms_provider": "mock",
                "sms_live_enabled": False,
            }
        if path == "/analytics/dashboard":
            return {
                "scope": (params or {}).get("scope", "imported"),
                "metrics": {"gross_revenue": "100.00", "net_revenue": "95.00", "gross_profit": "60.00", "cogs": "40.00", "orders": 2, "conversion_rate": "2.00", "refund_amount": "5.00", "sessions": 100},
                "time_series": [], "products": [], "traffic_sources": [], "devices": [], "refund_trend": [],
            }
        if path == "/analytics/workspace":
            return {"active_staff": 3, "active_customers": 2, "locked_accounts": 0,
                    "configured_products": 0, "pending_refunds": 0, "approved_refunds": 0,
                    "recent_customers": 0, "recent_completed_orders": 0, "orders_by_status": {}, "orders_needing_action": [],
                    "refunds_needing_action": []}
        if path == "/analytics/reports":
            return {"available": False, "message": "Not available in smoke fixture."}
        if path in {"/staff/customers/historical", "/staff/customers/registered"}:
            return {"items": [], "total": 0, "limit": 25, "offset": 0}
        return {"items": [], "total": 0, "limit": 25, "offset": 0}

    return get


def test_authenticated_pages_and_role_navigation_render(monkeypatch) -> None:
    role_state = {"role": "analyst"}
    monkeypatch.setattr(APIClient, "get", _fake_get(role_state))

    app = AppTest.from_file(str(APP_FILE))
    app.session_state["access_token"] = "test-token"
    app.run(timeout=20)
    assert not app.exception
    options = tuple(button.label for button in app.sidebar.button)
    assert options == navigation_for_role("analyst")
    assert not INTERNAL_MODULE_NAMES.intersection(options)

    expected_titles = {
        "Analytics Dashboard": "Analytics Dashboard",
        "Customers": "Customers",
        "Products": "Products",
        "Orders": "Orders",
        "Refunds": "Refunds",
        "Website Traffic": "Website Traffic",
        "Business Reports": "Business Reports",
        "My Account": "My Account",
        "Logout": "Logout",
    }
    for route, title in expected_titles.items():
        _navigate(app, route)
        assert not app.exception, route
        assert title in [element.value for element in app.title]
        if route not in {"My Account", "Logout"}:
            assert "Refresh Data" in [button.label for button in app.button]

    role_state["role"] = "admin"
    app.run(timeout=20)
    assert "User Management" in [button.label for button in app.sidebar.button]
    _navigate(app, "User Management")
    assert not app.exception
    assert "User Management" in [title.value for title in app.title]
    assert "Refresh Data" in [button.label for button in app.button]
    _navigate(app, "Customer Accounts")
    assert not app.exception
    assert "Customer Accounts" in [title.value for title in app.title]
    _navigate(app, "Project Evidence")
    assert not app.exception
    assert "Project Evidence" in [title.value for title in app.title]


def test_refresh_data_refetches_without_losing_authentication(monkeypatch) -> None:
    calls = []
    role_state = {"role": "analyst"}
    fake_get = _fake_get(role_state)

    def tracking_get(client, path, params=None):
        calls.append((path, params))
        return fake_get(client, path, params)

    monkeypatch.setattr(APIClient, "get", tracking_get)
    app = AppTest.from_file(str(APP_FILE))
    app.session_state["access_token"] = "test-token"
    app.run(timeout=20)
    _navigate(app, "Products")
    before = sum(path == "/products" for path, _ in calls)

    refresh = next(button for button in app.button if button.label == "Refresh Data")
    refresh.click().run(timeout=20)

    assert not app.exception
    assert app.session_state["access_token"] == "test-token"
    assert sum(path == "/products" for path, _ in calls) > before
    assert "Products" in [title.value for title in app.title]
    assert "Data refreshed successfully." in [item.value for item in app.toast]


def test_notification_test_buttons_react_to_destination_and_confirmation(monkeypatch) -> None:
    role_state = {"role": "admin"}
    monkeypatch.setattr(APIClient, "get", _fake_get(role_state))

    def forbid_send(*args, **kwargs):
        raise AssertionError("A notification send must not occur in this rendering test")

    monkeypatch.setattr(APIClient, "post", forbid_send)
    app = AppTest.from_file(str(APP_FILE))
    app.session_state["access_token"] = "admin-token"
    app.run(timeout=20)
    _navigate(app, "Notification Test")
    assert not app.exception

    email_button = next(button for button in app.button if button.label == "Send Test Email")
    sms_button = next(button for button in app.button if button.label == "Simulate Test SMS")
    assert email_button.disabled and sms_button.disabled

    next(item for item in app.text_input if item.label == "Test email address").set_value(
        "admin@example.com"
    ).run(timeout=20)
    app.checkbox[0].set_value(True).run(timeout=20)
    email_button = next(button for button in app.button if button.label == "Send Test Email")
    sms_button = next(button for button in app.button if button.label == "Simulate Test SMS")
    assert not email_button.disabled and sms_button.disabled

    next(item for item in app.text_input if item.label == "Test mobile number").set_value(
        "09171234567"
    ).run(timeout=20)
    email_button = next(button for button in app.button if button.label == "Send Test Email")
    sms_button = next(button for button in app.button if button.label == "Simulate Test SMS")
    assert not email_button.disabled and not sms_button.disabled


def test_analyst_business_reports_replace_technical_console(monkeypatch) -> None:
    role_state = {"role": "analyst"}
    monkeypatch.setattr(APIClient, "get", _fake_get(role_state))
    app = AppTest.from_file(str(APP_FILE))
    app.session_state["access_token"] = "staff-token"
    app.run(timeout=20)

    assert tuple(button.label for button in app.sidebar.button) == navigation_for_role("analyst")
    assert "Project Evidence" not in [button.label for button in app.sidebar.button]
    _navigate(app, "Business Reports")
    assert not app.exception
    markup = " ".join(item.value for item in app.markdown)
    for section in (
        "Sales summary", "Product performance", "Customer activity",
        "Traffic &amp; conversion", "Refund analysis", "Revenue / activity trends",
    ):
        assert section in markup
    assert not app.json
    assert "Communication Diagnostics" not in [tab.label for tab in app.tabs]
    assert "Raw reconciliation JSON" not in [item.label for item in app.expander]


def test_analyst_pages_use_deidentified_compact_business_views(monkeypatch) -> None:
    role_state = {"role": "analyst"}
    base_get = _fake_get(role_state)
    calls = []

    def get(client: APIClient, path: str, params=None):
        calls.append(path)
        if path == "/analytics/dashboard":
            return {
                "scope": (params or {}).get("scope", "imported"),
                "metrics": {"gross_revenue": "100.00", "net_revenue": "95.00", "gross_profit": "60.00", "cogs": "40.00", "orders": 2, "conversion_rate": None if (params or {}).get("scope") == "application" else "2.00", "refund_amount": "5.00", "sessions": 0 if (params or {}).get("scope") == "application" else 100},
                "time_series": [],
                "products": [{"product_id": 1, "product_name": "Historical Toy", "orders": 2, "units": 3, "revenue": "100.00", "cogs": "40.00", "refunds": "5.00", "net_revenue": "95.00"}],
                "traffic_sources": [], "devices": [],
                "refund_trend": [{"period": "2013-01", "refunds": 1, "amount": "5.00"}],
            }
        if path == "/products":
            return {"items": [{"product_id": 1, "product_name": "Historical Toy", "created_at": "2012-01-01T00:00:00+00:00", "origin": "imported", "created_by_app_user_id": None, "row_version": 1}], "total": 1, "limit": 25, "offset": 0}
        if path == "/orders":
            return {"items": [{"order_id": 12, "created_at": "2013-01-01T08:00:00+00:00", "website_session_id": 21, "user_id": 818, "customer_account_id": None, "primary_product_id": 1, "items_purchased": 1, "price_usd": "49.99", "cogs_usd": "19.49", "order_status": None, "origin": "imported", "created_by_app_user_id": None, "row_version": 1}], "total": 1, "limit": 25, "offset": 0}
        if path == "/refunds":
            return {"items": [{"order_item_refund_id": 7, "order_id": 12, "order_item_id": 14, "refund_amount_usd": "5.00", "created_at": "2013-01-02T08:00:00+00:00", "origin": "imported", "created_by_app_user_id": None, "row_version": 1}], "total": 1, "limit": 25, "offset": 0}
        if path == "/staff/customers/historical":
            return {"items": [{"dataset_user_id": 818, "order_count": 2, "total_spent": "99.98", "refund_total": "5.00", "last_visit": "2013-01-02T08:00:00+00:00"}], "total": 1, "limit": 25, "offset": 0}
        if path == "/staff/customers/registered":
            return {"items": [{"customer_account_id": 105, "customer_label": "Registered Customer #105", "order_count": 0, "total_spent": "0.00", "created_at": "2026-09-01T08:00:00+00:00", "dataset_user_id": None}], "total": 1, "limit": 25, "offset": 0}
        if path == "/website-sessions":
            return {"items": [{"website_session_id": 21, "created_at": "2013-01-01T08:00:00+00:00", "user_id": 818, "is_repeat_session": False, "utm_source": None, "utm_campaign": None, "utm_content": None, "device_type": "desktop", "http_referer": None}], "total": 1, "limit": 25, "offset": 0}
        if path == "/website-pageviews":
            return {"items": [{"website_pageview_id": 31, "created_at": "2013-01-01T08:01:00+00:00", "website_session_id": 21, "pageview_url": "/home"}], "total": 1, "limit": 25, "offset": 0}
        return base_get(client, path, params)

    monkeypatch.setattr(APIClient, "get", get)
    app = AppTest.from_file(str(APP_FILE))
    app.session_state["access_token"] = "analyst-token"
    app.run(timeout=20)

    assert tuple(button.label for button in app.sidebar.button) == navigation_for_role("analyst")
    assert "Project Evidence" not in [button.label for button in app.sidebar.button]

    _navigate(app, "Customers")
    customer_frames = [frame.value for frame in app.dataframe]
    assert any(list(frame.columns) == ["Customer", "Orders", "Total Spent", "Refunds", "Last Activity"] for frame in customer_frames)
    registered = next(frame for frame in customer_frames if "Account Since" in frame.columns)
    assert list(registered.columns) == ["Customer", "Orders", "Total Spent", "Account Since"]
    assert registered.iloc[0]["Customer"] == "Customer #105"
    assert "email" not in " ".join(map(str, registered.columns)).lower()

    _navigate(app, "Products")
    assert list(app.dataframe[-1].value.columns) == ["Product", "Revenue", "Orders", "Units", "Gross Profit", "Refunds", "Source"]
    assert "Customer-created" not in app.dataframe[-1].value["Source"].tolist()

    _navigate(app, "Orders")
    assert list(app.dataframe[-1].value.columns) == ["Order #", "Customer", "Date", "Total", "Status", "Source"]
    assert app.dataframe[-1].value.iloc[0]["Status"] == "Historical Record"

    _navigate(app, "Refunds")
    assert list(app.dataframe[-1].value.columns) == ["Refund #", "Order #", "Amount", "Date", "Source"]

    _navigate(app, "Website Traffic")
    assert [tab.label for tab in app.tabs] == ["Sessions", "Pageviews"]
    session_frame = next(frame.value for frame in app.dataframe if "Traffic Source" in frame.value.columns)
    assert "Referrer" in session_frame.columns and "Repeat Visit" in session_frame.columns
    assert not session_frame.astype(str).apply(lambda column: column.str.contains("None|NULL", case=False).any()).any()

    forbidden_actions = {"Create Product", "Save changes", "Delete record", "Start Processing", "Approve", "Reject", "Process Refund"}
    assert not forbidden_actions.intersection(button.label for button in app.button)
    assert "/analytics/reports" not in calls


def test_analyst_application_conversion_is_not_applicable(monkeypatch) -> None:
    role_state = {"role": "analyst"}
    base_get = _fake_get(role_state)

    def get(client: APIClient, path: str, params=None):
        result = base_get(client, path, params)
        if path == "/analytics/dashboard" and (params or {}).get("scope") == "application":
            result["metrics"]["conversion_rate"] = None
            result["metrics"]["sessions"] = 0
        return result

    monkeypatch.setattr(APIClient, "get", get)
    app = AppTest.from_file(str(APP_FILE))
    app.session_state["access_token"] = "analyst-token"
    app.run(timeout=20)
    scope = next(item for item in app.selectbox if item.label == "Reporting scope")
    scope.set_value("application").run(timeout=20)

    conversion = next(metric for metric in app.metric if metric.label == "Conversion Rate")
    assert conversion.value == "Not applicable"
    assert next(metric for metric in app.metric if metric.label == "Sessions").value == "0"


def test_project_evidence_is_admin_only_and_keeps_technical_artifacts(monkeypatch) -> None:
    role_state = {"role": "admin"}
    base_get = _fake_get(role_state)

    def get(client: APIClient, path: str, params=None):
        if path == "/analytics/reports":
            return {
                "available": True,
                "reconciliation": {"passed": True},
                "product_performance": [],
                "latency": [],
                "payload_sizes": [],
                "observation_note": "Local measurements only.",
            }
        return base_get(client, path, params)

    monkeypatch.setattr(APIClient, "get", get)
    app = AppTest.from_file(str(APP_FILE))
    app.session_state["access_token"] = "staff-token"
    app.run(timeout=20)
    _navigate(app, "Project Evidence")
    assert not app.exception
    assert "Project Evidence" in [title.value for title in app.title]
    assert "Raw reconciliation JSON" in [item.label for item in app.expander]
    assert "Communication Diagnostics" in [tab.label for tab in app.tabs]


def test_products_omit_impossible_customer_created_source_badge(monkeypatch) -> None:
    role_state = {"role": "analyst"}
    monkeypatch.setattr(APIClient, "get", _fake_get(role_state))
    app = AppTest.from_file(str(APP_FILE))
    app.session_state["access_token"] = "staff-token"
    app.run(timeout=20)
    _navigate(app, "Products")
    markup = " ".join(item.value for item in app.markdown)
    assert "Historical data" in markup
    assert "Application-created" in markup
    assert "Customer-created" not in markup


def test_role_specific_crud_controls_remain_visible_only_when_allowed(monkeypatch) -> None:
    role_state = {"role": "analyst"}
    monkeypatch.setattr(APIClient, "get", _fake_get(role_state))
    app = AppTest.from_file(str(APP_FILE))
    app.session_state["access_token"] = "test-token"
    app.run(timeout=20)

    _navigate(app, "Products")
    assert not app.tabs
    _navigate(app, "Orders")
    _assert_no_generic_transaction_crud(app, "Create order")
    assert "Start Processing" not in [button.label for button in app.button]
    _navigate(app, "Refunds")
    _assert_no_generic_transaction_crud(app, "Create refund")

    role_state["role"] = "operations_staff"
    app.run(timeout=20)
    operations_navigation = [button.label for button in app.sidebar.button]
    assert "Website Sessions" not in operations_navigation
    assert "Website Pageviews" not in operations_navigation
    assert "User Management" not in operations_navigation
    assert "Customer Accounts" not in operations_navigation
    assert "Project Evidence" not in operations_navigation
    assert not app.tabs
    _navigate(app, "Orders")
    _assert_no_generic_transaction_crud(app, "Create order")
    assert "Create Order Item" not in [button.label for button in app.button]
    assert "Delete record" not in [button.label for button in app.button]
    assert "Order Items" not in [button.label for button in app.sidebar.button]
    _navigate(app, "Refunds")
    _assert_no_generic_transaction_crud(app, "Create refund")

    role_state["role"] = "admin"
    app.run(timeout=20)
    _navigate(app, "Products")
    assert [tab.label for tab in app.tabs] == ["Create Product", "Manage Products"]
    assert "User Management" in [button.label for button in app.sidebar.button]
    assert "Order Items" not in [button.label for button in app.sidebar.button]

    _navigate(app, "Orders")
    _assert_no_generic_transaction_crud(app, "Create order")

    _navigate(app, "Refunds")
    _assert_no_generic_transaction_crud(app, "Create refund")

    _navigate(app, "Website Traffic")
    assert [tab.label for tab in app.tabs] == ["Sessions", "Pageviews"]


def test_staff_orders_render_source_aware_customer_and_session_fields(monkeypatch) -> None:
    role_state = {"role": "analyst"}
    customer_order = {
        "order_id": 70001, "created_at": "2026-09-12T08:00:00+00:00",
        "website_session_id": None, "user_id": None, "customer_account_id": 105,
        "primary_product_id": 1, "items_purchased": 1, "price_usd": "49.99",
        "cogs_usd": "19.49", "order_status": "pending", "origin": "customer",
        "created_by_app_user_id": None, "row_version": 1,
    }
    imported_order = {
        "order_id": 12, "created_at": "2013-01-01T08:00:00+00:00",
        "website_session_id": 4242, "user_id": 818, "customer_account_id": None,
        "primary_product_id": 1, "items_purchased": 1, "price_usd": "49.99",
        "cogs_usd": "19.49", "order_status": None, "origin": "imported",
        "created_by_app_user_id": None, "row_version": 1,
    }
    base_get = _fake_get(role_state)

    def get(client: APIClient, path: str, params=None):
        if path == "/orders":
            return {"items": [customer_order, imported_order], "total": 2, "limit": 25, "offset": 0}
        return base_get(client, path, params)

    monkeypatch.setattr(APIClient, "get", get)
    app = AppTest.from_file(str(APP_FILE))
    app.session_state["access_token"] = "staff-token"
    app.run(timeout=20)
    _navigate(app, "Orders")
    assert not app.exception

    frame = app.dataframe[-1].value
    assert list(frame.columns) == [
        "Order #", "Customer", "Date", "Total", "Status", "Source",
    ]
    assert frame.iloc[0]["Customer"] == "Customer #105"
    assert frame.iloc[1]["Customer"] == "Historical Shopper #818"
    assert not frame.astype(str).apply(lambda column: column.str.contains("None").any()).any()

    visible = " ".join(element.value for element in app.markdown)
    assert "Customer #105" in visible
    assert "customer@example.com" not in visible
    assert "Website Session" not in visible
    assert "Dataset User ID" not in visible

    detail_select = next(item for item in app.selectbox if item.label == "Order to inspect")
    detail_select.set_value(12).run(timeout=20)
    visible = " ".join(element.value for element in app.markdown)
    assert "Historical Shopper #818" in visible
    assert "Website Session" not in visible


def test_customer_authenticated_navigation_is_separate(monkeypatch) -> None:
    def customer_get(_: APIClient, path: str, params=None):
        if path in {"/customer/addresses", "/customer/payment-methods", "/customer/store/products"}:
            return []
        if path == "/customer/profile":
            return {"customer_account_id": 7, "first_name": "Customer", "last_name": "Tester",
                    "phone": None, "row_version": 1}
        if path == "/customer/cart":
            return {"items": [], "distinct_items": 0, "total_quantity": 0, "cart_subtotal_usd": "0.00"}
        assert path == "/customer/auth/me"
        return {
            "customer_account_id": 7,
            "email": "customer@example.com",
            "is_active": True,
            "first_name": "Customer",
            "last_name": "Tester",
            "phone": None,
            "profile_row_version": 1,
            "created_at": "2026-09-11T09:30:00+00:00",
            "updated_at": "2026-09-11T09:30:00+00:00",
            "last_login_at": "2026-09-11T09:30:00+00:00",
        }

    monkeypatch.setattr(APIClient, "get", customer_get)
    app = AppTest.from_file(str(APP_FILE))
    app.session_state["customer_access_token"] = "customer-token"
    app.session_state["active_portal"] = "customer"
    app.run(timeout=20)
    assert not app.exception
    customer_navigation = tuple(button.label for button in app.sidebar.button)
    assert customer_navigation == ("Home / Shop", "Cart", "My Orders", "My Account", "Logout")
    assert any("Toys for Brighter Days" in item.value for item in app.markdown)
    customer_copy = " ".join(
        item.value for collection in (app.caption, app.info, app.warning, app.success)
        for item in collection
    )
    for internal_label in ("record_origin", "canonical", "Customer-created", "Application-created", "Historical data"):
        assert internal_label not in customer_copy
    _navigate(app, "Cart")
    assert "Your Cart" in [title.value for title in app.title]
    _navigate(app, "My Account")
    assert "My Account" in [title.value for title in app.title]
    labels = [tab.label for tab in app.tabs]
    for expected in ("Profile", "Addresses", "Payment Methods", "Security"):
        assert expected in labels
    assert "Dashboard" not in customer_navigation


def test_customer_storefront_cards_details_and_cart_warnings_render(monkeypatch) -> None:
    product = {
        "product_id": 4, "product_name": "Configured Toy", "description": "A real configured description.",
        "current_price_usd": "21.99", "image_url": None, "is_available": True,
    }
    item = {
        "cart_item_id": 9, "product_id": 4, "product_name": "Configured Toy", "image_url": None,
        "quantity": 2, "stored_unit_price_usd": "19.99", "current_catalog_price_usd": "21.99",
        "price_changed": True, "is_available": False, "line_subtotal_usd": "39.98",
        "row_version": 3, "created_at": "2026-09-11T09:30:00+00:00", "updated_at": "2026-09-11T09:30:00+00:00",
    }

    def customer_get(_: APIClient, path: str, params=None):
        if path == "/customer/auth/me":
            return {
                "customer_account_id": 7, "email": "customer@example.com", "is_active": True,
                "first_name": "Customer", "last_name": "Tester", "phone": None,
                "profile_row_version": 1, "created_at": "2026-09-11T09:30:00+00:00",
                "updated_at": "2026-09-11T09:30:00+00:00", "last_login_at": None,
            }
        if path == "/customer/store/products":
            return [product]
        if path == "/customer/store/products/4":
            return product
        if path == "/customer/cart":
            return {"items": [item], "distinct_items": 1, "total_quantity": 2, "cart_subtotal_usd": "39.98"}
        if path in {"/customer/addresses", "/customer/payment-methods"}:
            return []
        raise AssertionError(path)

    monkeypatch.setattr(APIClient, "get", customer_get)
    app = AppTest.from_file(str(APP_FILE))
    app.session_state["customer_access_token"] = "customer-token"
    app.session_state["active_portal"] = "customer"
    app.run(timeout=20)
    assert not app.exception
    assert "Configured Toy" in [heading.value for heading in app.subheader]
    assert "View Details" in [button.label for button in app.button]
    next(button for button in app.button if button.label == "View Details").click().run(timeout=20)
    assert not app.exception
    assert "Back to products" in " ".join(button.label for button in app.button)
    _navigate(app, "Cart")
    assert not app.exception
    assert "Update" in [button.label for button in app.button]
    assert "Remove" in [button.label for button in app.button]
    assert app.warning and app.error


def test_catalog_configuration_controls_are_admin_only(monkeypatch) -> None:
    role_state = {"role": "analyst"}

    def get(client: APIClient, path: str, params=None):
        if path == "/admin/catalog":
            return [{
                "product_id": 1, "product_name": "Source Toy", "description": None,
                "current_price_usd": None, "current_cogs_usd": None, "image_url": None,
                "is_available": None, "is_configured": False, "row_version": None,
                "created_at": None, "updated_at": None,
            }]
        return _fake_get(role_state)(client, path, params)

    monkeypatch.setattr(APIClient, "get", get)
    app = AppTest.from_file(str(APP_FILE))
    app.session_state["access_token"] = "staff-token"
    app.run(timeout=20)
    assert "Storefront Catalog" not in [button.label for button in app.sidebar.button]
    role_state["role"] = "admin"
    app.run(timeout=20)
    _navigate(app, "Storefront Catalog")
    assert not app.exception
    assert "Configure storefront details" in [item.label for item in app.expander]


def test_checkout_and_customer_order_pages_render(monkeypatch) -> None:
    customer = {
        "customer_account_id": 7, "email": "customer@example.com", "is_active": True,
        "first_name": "Customer", "last_name": "Tester", "phone": None,
        "profile_row_version": 1, "created_at": "2026-09-11T09:30:00+00:00",
        "updated_at": "2026-09-11T09:30:00+00:00", "last_login_at": None,
    }
    order_detail = {
        "order_id": 70001, "created_at": "2026-09-11T10:00:00+00:00", "order_status": "ready_shipped",
        "total_quantity": 2, "total_usd": "39.98", "row_version": 1,
        "items": [{"product_id": 4, "product_name": "Configured Toy", "quantity": 2, "unit_price_usd": "19.99", "line_total_usd": "39.98"}],
        "shipping": {"recipient_first_name": "Customer", "recipient_last_name": "Tester", "phone": None, "address_line_1": "1 Demo Street", "address_line_2": None, "city": "Manila", "province_region": "Metro Manila", "postal_code": "1000", "country_code": "PH"},
        "payment": {"method_type": "card", "display_label": "Visa ending in 1234 — simulated", "payment_status": "paid", "amount_usd": "39.98", "simulated_reference": "RM-DEMO-TEST"},
    }

    def get(_: APIClient, path: str, params=None):
        if path == "/customer/auth/me": return customer
        if path == "/customer/store/products": return []
        if path == "/customer/cart":
            return {"shopping_cart_id": 8, "row_version": 2, "items": [{
                "cart_item_id": 9, "product_id": 4, "product_name": "Configured Toy", "image_url": None,
                "quantity": 2, "stored_unit_price_usd": "19.99", "current_catalog_price_usd": "19.99",
                "price_changed": False, "is_available": True, "line_subtotal_usd": "39.98", "row_version": 1,
                "created_at": "2026-09-11T09:30:00+00:00", "updated_at": "2026-09-11T09:30:00+00:00",
            }], "distinct_items": 1, "total_quantity": 2, "cart_subtotal_usd": "39.98"}
        if path == "/customer/addresses":
            return [{"customer_address_id": 1, "label": "Home", "address_line_1": "1 Demo Street", "city": "Manila", "is_active": True, "is_default": True}]
        if path == "/customer/payment-methods":
            return [{"payment_method_id": 2, "display_label": "Visa ending in 1234 — simulated", "is_active": True, "is_default": True}]
        if path == "/customer/orders":
            return [{"order_id": 70001, "created_at": order_detail["created_at"], "order_status": "ready_shipped", "payment_status": "paid", "item_count": 2, "total_quantity": 2, "total_usd": "39.98", "row_version": 1}]
        if path == "/customer/orders/70001": return order_detail
        if path == "/customer/orders/70001/refund-eligibility":
            return [{"order_item_id": 11, "product_id": 4, "product_name": "Configured Toy", "item_price_usd": "19.99", "remaining_refundable_usd": "19.99", "eligible": True, "reason": None, "current_request_status": None}]
        if path == "/customer/refund-requests": return []
        raise AssertionError(path)

    monkeypatch.setattr(APIClient, "get", get)
    app = AppTest.from_file(str(APP_FILE))
    app.session_state["customer_access_token"] = "customer-token"
    app.session_state["active_portal"] = "customer"
    app.run(timeout=20)
    _navigate(app, "Cart")
    next(button for button in app.button if button.label == "Proceed to Checkout").click().run(timeout=20)
    assert not app.exception
    assert "Checkout" in [title.value for title in app.title]
    assert "Place Order" in [button.label for button in app.button]
    app.session_state["show_checkout"] = False
    _navigate(app, "My Orders")
    assert "My Orders" in [title.value for title in app.title]
    next(button for button in app.button if button.label == "View Order").click().run(timeout=20)
    assert not app.exception
    assert "Order #70001" in [heading.value for heading in app.subheader]
    assert "Request Refund" in [button.label for button in app.button]


def test_staff_refund_request_actions_are_role_aware(monkeypatch) -> None:
    role_state = {"role": "operations_staff"}
    request = {
        "refund_request_id": 9, "order_id": 7, "order_item_id": 8,
        "product_id": 1, "product_name": "Demo Toy", "requested_amount": "4.00",
        "reason": "Damaged", "status": "pending", "created_at": "2026-09-11T10:00:00+00:00",
        "reviewed_at": None, "resolution_note": None, "row_version": 1,
    }

    def get(client: APIClient, path: str, params=None):
        if path == "/refund-requests":
            return {"items": [request], "total": 1, "limit": 25, "offset": 0}
        return _fake_get(role_state)(client, path, params)

    monkeypatch.setattr(APIClient, "get", get)
    app = AppTest.from_file(str(APP_FILE))
    app.session_state["access_token"] = "staff-token"
    app.run(timeout=20)
    _navigate(app, "Refund Requests")
    assert not app.exception
    assert "Approve" in [button.label for button in app.button]
    assert "Reject" in [button.label for button in app.button]
    assert list(app.dataframe[-1].value.columns) == [
        "Request #", "Order #", "Product", "Amount", "Reason", "Status", "Requested", "Outcome",
    ]
    assert "Item #8" not in " ".join(element.value for element in app.markdown)
    request["status"] = "approved"
    app.run(timeout=20)
    assert "Process Refund" in [button.label for button in app.button]
    role_state["role"] = "analyst"
    app.run(timeout=20)
    assert "Approve" not in [button.label for button in app.button]
    assert "Reject" not in [button.label for button in app.button]
    assert "Process Refund" not in [button.label for button in app.button]


def test_operations_rejected_and_processed_refunds_are_compact_read_only(monkeypatch) -> None:
    role_state = {"role": "operations_staff"}
    request = {
        "refund_request_id": 10, "order_id": 7, "order_item_id": 8,
        "product_id": 1, "product_name": "Demo Toy", "requested_amount": "4.00",
        "reason": "Damaged", "status": "rejected", "created_at": "2026-09-11T10:00:00+00:00",
        "reviewed_at": "2026-09-11T11:00:00+00:00", "resolution_note": "Outside the return window",
        "row_version": 2,
    }

    def get(client: APIClient, path: str, params=None):
        if path == "/refund-requests":
            return {"items": [request], "total": 1, "limit": 25, "offset": 0}
        return _fake_get(role_state)(client, path, params)

    monkeypatch.setattr(APIClient, "get", get)
    app = AppTest.from_file(str(APP_FILE))
    app.session_state["access_token"] = "operations-token"
    app.run(timeout=20)
    _navigate(app, "Refund Requests")

    assert "Outside the return window" in app.dataframe[-1].value["Outcome"].tolist()
    assert not {"Approve", "Reject", "Process Refund"}.intersection(button.label for button in app.button)

    request["status"] = "processed"
    request["resolution_note"] = "Refund completed"
    app.run(timeout=20)
    assert "Refund completed" in app.dataframe[-1].value["Outcome"].tolist()
    assert not {"Approve", "Reject", "Process Refund"}.intersection(button.label for button in app.button)


def test_customer_order_workflow_controls_are_role_aware(monkeypatch) -> None:
    role_state = {"role": "operations_staff"}
    workflow_order = {
        "order_id": 70010, "customer_account_id": 19,
        "created_at": "2026-09-11T10:00:00+00:00", "total_usd": "24.00",
        "payment_status": "paid", "order_status": "pending",
        "origin": "customer", "row_version": 1,
    }

    def get(client: APIClient, path: str, params=None):
        if path == "/order-workflow/orders":
            return {"items": [workflow_order], "total": 1, "limit": 25, "offset": 0}
        return _fake_get(role_state)(client, path, params)

    monkeypatch.setattr(APIClient, "get", get)
    app = AppTest.from_file(str(APP_FILE))
    app.session_state["access_token"] = "staff-token"
    app.run(timeout=20)
    _navigate(app, "Orders")
    assert not app.exception
    assert "Start Processing" in [button.label for button in app.button]
    assert "Cancel Pending Order" in [button.label for button in app.button]
    assert list(app.dataframe[0].value.columns) == [
        "Order #", "Customer", "Date", "Total", "Payment", "Status",
    ]
    role_state["role"] = "analyst"
    app.run(timeout=20)
    assert "Start Processing" not in [button.label for button in app.button]
    role_state["role"] = "admin"
    app.run(timeout=20)
    assert "Start Processing" in [button.label for button in app.button]
    assert "Cancel Pending Order" in [button.label for button in app.button]
    workflow_order["order_status"] = "processing"
    workflow_order["row_version"] = 2
    app.run(timeout=20)
    assert "Mark Ready / Shipped" in [button.label for button in app.button]
    assert "Mark as Received" not in [button.label for button in app.button]
    role_state["role"] = "operations_staff"
    app.run(timeout=20)
    assert "Mark Ready / Shipped" in [button.label for button in app.button]
    workflow_order["order_status"] = "delivered"
    app.run(timeout=20)
    assert "Mark Ready / Shipped" not in [button.label for button in app.button]


def test_operations_workspace_uses_compact_read_only_projections(monkeypatch) -> None:
    role_state = {"role": "operations_staff"}
    base_get = _fake_get(role_state)

    def get(client: APIClient, path: str, params=None):
        if path == "/staff/customers/registered":
            return {"items": [{
                "customer_account_id": 12, "customer_label": "Jamie Rivera",
                "email": "jamie@example.com", "is_active": True,
                "order_count": 3, "total_spent": "129.97", "created_at": "2026-09-01T10:00:00+00:00",
                "dataset_user_id": None,
            }], "total": 1, "limit": 25, "offset": 0}
        if path == "/staff/customers/historical":
            return {"items": [{
                "dataset_user_id": 44, "session_count": 7, "repeat_visitor": True,
                "order_count": 2, "total_spent": "79.98", "refund_total": "0.00",
                "last_visit": "2015-03-01T10:00:00+00:00", "latest_utm_source": None,
                "latest_device_type": None,
            }], "total": 1, "limit": 25, "offset": 0}
        if path == "/products":
            return {"items": [{
                "product_id": 1, "product_name": "The Original Mr. Fuzzy",
                "created_at": "2012-03-19T10:00:00+00:00", "origin": "imported",
                "created_by_app_user_id": None, "row_version": 1,
            }], "total": 1, "limit": 25, "offset": 0}
        if path == "/refunds":
            return {"items": [{
                "order_item_refund_id": 31, "order_id": 22, "order_item_id": 25,
                "refund_amount_usd": "9.99", "created_at": "2026-09-11T10:00:00+00:00",
                "origin": "customer", "created_by_app_user_id": 2, "row_version": 1,
            }], "total": 1, "limit": 25, "offset": 0}
        if path == "/admin/catalog":
            return [{
                "product_id": 1, "product_name": "The Original Mr. Fuzzy",
                "description": "A cheerful toy.", "current_price_usd": "49.99",
                "current_cogs_usd": "19.49", "image_url": None, "is_available": True,
                "is_configured": True, "row_version": 1,
                "created_at": "2026-09-01T10:00:00+00:00", "updated_at": "2026-09-11T10:00:00+00:00",
            }]
        return base_get(client, path, params)

    monkeypatch.setattr(APIClient, "get", get)
    app = AppTest.from_file(str(APP_FILE))
    app.session_state["access_token"] = "operations-token"
    app.run(timeout=20)

    _navigate(app, "Customers")
    registered = next(frame.value for frame in app.dataframe if "Email" in frame.value.columns)
    assert list(registered.columns) == ["Customer", "Email", "Orders", "Total Spent", "Account Status"]
    assert "Set Active" not in [button.label for button in app.button]
    assert "Unlock" not in [button.label for button in app.button]

    _navigate(app, "Products")
    assert list(app.dataframe[-1].value.columns) == ["Product", "Created", "Source"]
    assert "Create new" not in [tab.label for tab in app.tabs]
    assert "Delete record" not in [button.label for button in app.button]

    _navigate(app, "Storefront Catalog")
    assert any("read-only for Operations Staff" in item.value for item in app.info)
    assert "Configure storefront details" not in [item.label for item in app.expander]
    assert not app.number_input

    _navigate(app, "Refunds")
    assert list(app.dataframe[-1].value.columns) == ["Refund #", "Order #", "Product", "Amount", "Date", "Source"]
    _assert_no_generic_transaction_crud(app, "Create refund")


def test_operations_dashboard_actions_and_business_copy(monkeypatch) -> None:
    role_state = {"role": "operations_staff"}
    base_get = _fake_get(role_state)

    def get(client: APIClient, path: str, params=None):
        if path == "/analytics/workspace":
            return {
                "active_staff": 3, "active_customers": 2, "locked_accounts": 0,
                "configured_products": 4, "pending_refunds": 1, "approved_refunds": 1,
                "recent_customers": 2, "recent_completed_orders": 3,
                "orders_by_status": {"pending": 1, "processing": 1},
                "orders_needing_action": [{
                    "order_id": 71, "customer_account_id": 12, "status": "pending",
                    "payment_status": "paid", "total": "49.99", "created_at": "2026-09-11T10:00:00+00:00",
                }],
                "refunds_needing_action": [{
                    "request_id": 9, "order_id": 71, "product": "The Original Mr. Fuzzy",
                    "status": "pending", "amount": "10.00",
                }],
            }
        return base_get(client, path, params)

    monkeypatch.setattr(APIClient, "get", get)
    app = AppTest.from_file(str(APP_FILE))
    app.session_state["access_token"] = "operations-token"
    app.run(timeout=20)

    assert {"Open Orders", "Open Refund Requests"} <= {button.label for button in app.button}
    visible = " ".join(
        str(element.value) for collection in (
            app.title, app.header, app.subheader, app.markdown, app.caption,
            app.info, app.warning, app.success,
        ) for element in collection
    ).lower()
    for forbidden in (
        "fastapi", "record_origin", "row_version", "synthetic", "migration",
        "reconciliation", "protobuf", "grpc", "rest", "api token",
    ):
        assert forbidden not in visible

    _navigate(app, "Logout")
    assert any("Sign out of RetailMetrics on this device." in item.value for item in app.caption)


def test_admin_dashboard_and_final_navigation_are_management_focused(monkeypatch) -> None:
    role_state = {"role": "admin"}
    monkeypatch.setattr(APIClient, "get", _fake_get(role_state))
    app = AppTest.from_file(str(APP_FILE))
    app.session_state["access_token"] = "admin-token"
    app.run(timeout=20)

    assert tuple(button.label for button in app.sidebar.button) == navigation_for_role("admin")
    assert "Website Sessions" not in [button.label for button in app.sidebar.button]
    assert "Website Pageviews" not in [button.label for button in app.sidebar.button]
    metric_labels = [metric.label for metric in app.metric]
    assert "Historical Orders" in metric_labels
    assert "Customer Orders" in metric_labels
    assert "Baseline Orders" not in metric_labels

    _navigate(app, "Website Traffic")
    assert [tab.label for tab in app.tabs] == ["Sessions", "Pageviews"]
    _navigate(app, "Project Evidence")
    assert "Project Evidence" in [title.value for title in app.title]


def test_admin_account_control_tables_hide_internal_security_fields(monkeypatch) -> None:
    role_state = {"role": "admin"}
    base_get = _fake_get(role_state)

    def get(client: APIClient, path: str, params=None):
        if path == "/admin/users":
            return {"items": [{
                "app_user_id": 1, "username": "admin_user", "email": "admin@example.com",
                "role": "admin", "is_active": True, "locked_until": None,
                "last_login_at": "2026-09-11T10:00:00+00:00", "row_version": 3,
            }], "total": 1, "limit": 25, "offset": 0}
        if path == "/admin/customers":
            return {"items": [{
                "customer_account_id": 12, "first_name": "Jamie", "last_name": "Rivera",
                "email": "jamie@example.com", "phone": "09170000000", "is_active": True,
                "locked_until": None, "last_login_at": "2026-09-11T10:00:00+00:00",
                "account_row_version": 2,
            }], "total": 1, "limit": 25, "offset": 0}
        return base_get(client, path, params)

    monkeypatch.setattr(APIClient, "get", get)
    app = AppTest.from_file(str(APP_FILE))
    app.session_state["access_token"] = "admin-token"
    app.run(timeout=20)

    _navigate(app, "User Management")
    assert list(app.dataframe[-1].value.columns) == ["Username", "Role", "Status", "Email", "Last login"]
    assert "Create user" in [tab.label for tab in app.tabs]
    assert "Manage user" in [tab.label for tab in app.tabs]

    _navigate(app, "Customer Accounts")
    assert list(app.dataframe[-1].value.columns) == ["Customer", "Email", "Status", "Lock status", "Last login"]
    assert "Deactivate" in [button.label for button in app.button]
    assert "Unlock account" in [button.label for button in app.button]
    table_text = app.dataframe[-1].value.astype(str).to_string().lower()
    assert "row_version" not in table_text
    assert "token_version" not in table_text


def test_admin_customer_activity_and_product_management_are_cleanly_separated(monkeypatch) -> None:
    role_state = {"role": "admin"}
    base_get = _fake_get(role_state)

    def get(client: APIClient, path: str, params=None):
        if path == "/staff/customers/historical":
            return {"items": [{
                "dataset_user_id": 44, "session_count": 7, "repeat_visitor": True,
                "order_count": 2, "total_spent": "79.98", "refund_total": "5.00",
                "last_visit": "2015-03-01T10:00:00+00:00", "latest_utm_source": "gsearch",
                "latest_device_type": "desktop",
            }], "total": 1, "limit": 25, "offset": 0}
        if path == "/staff/customers/registered":
            return {"items": [{
                "customer_account_id": 12, "customer_label": "Jamie Rivera",
                "email": "jamie@example.com", "is_active": True, "is_locked": False,
                "order_count": 3, "total_spent": "129.97", "created_at": "2026-09-01T10:00:00+00:00",
                "dataset_user_id": None,
            }], "total": 1, "limit": 25, "offset": 0}
        if path == "/products":
            return {"items": [
                {"product_id": 1, "product_name": "Historical Toy", "created_at": "2012-03-19T10:00:00+00:00", "origin": "imported", "created_by_app_user_id": None, "row_version": 1},
                {"product_id": 70001, "product_name": "Application Toy", "created_at": "2026-09-11T10:00:00+00:00", "origin": "web", "created_by_app_user_id": 1, "row_version": 2},
            ], "total": 2, "limit": 25, "offset": 0}
        if path == "/admin/catalog":
            return [{
                "product_id": 1, "product_name": "Historical Toy", "description": "A toy.",
                "current_price_usd": "49.99", "current_cogs_usd": "19.49", "image_url": None,
                "is_available": True, "is_configured": True, "row_version": 1,
                "created_at": "2026-09-01T10:00:00+00:00", "updated_at": "2026-09-11T10:00:00+00:00",
            }]
        return base_get(client, path, params)

    monkeypatch.setattr(APIClient, "get", get)
    app = AppTest.from_file(str(APP_FILE))
    app.session_state["access_token"] = "admin-token"
    app.run(timeout=20)

    _navigate(app, "Customers")
    historical = next(frame.value for frame in app.dataframe if "Refunds" in frame.value.columns)
    registered = next(frame.value for frame in app.dataframe if "Email" in frame.value.columns)
    assert list(historical.columns) == ["Customer", "Orders", "Total Spent", "Refunds", "Last Activity"]
    assert list(registered.columns) == ["Customer", "Email", "Orders", "Total Spent", "Account Since", "Status"]
    assert "Unlock account" not in [button.label for button in app.button]

    _navigate(app, "Products")
    product_table = app.dataframe[-1].value
    assert list(product_table.columns) == ["Product", "Created", "Source", "Storefront Status"]
    assert "Customer-created" not in product_table["Source"].tolist()
    assert [tab.label for tab in app.tabs] == ["Create Product", "Manage Products"]
    managed = next(item for item in app.selectbox if item.label == "Application-created record")
    assert tuple(managed.options) == ("70001",)
