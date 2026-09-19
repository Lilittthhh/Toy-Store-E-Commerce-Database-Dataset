from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from frontend.api_client import APIClient


APP_FILE = Path(__file__).resolve().parents[2] / "frontend" / "app.py"


CUSTOMER = {
    "customer_account_id": 7,
    "email": "customer@example.com",
    "is_active": True,
    "first_name": "Customer",
    "last_name": "Tester",
    "phone": None,
    "profile_row_version": 1,
    "created_at": "2026-09-11T09:30:00+00:00",
    "updated_at": "2026-09-11T09:30:00+00:00",
    "last_login_at": None,
}

PRODUCT = {
    "product_id": 4,
    "product_name": "Configured Toy",
    "description": "A configured storefront product.",
    "current_price_usd": "19.99",
    "image_url": None,
    "is_available": True,
}

CART = {
    "shopping_cart_id": 8,
    "row_version": 2,
    "items": [{
        "cart_item_id": 9,
        "product_id": 4,
        "product_name": "Configured Toy",
        "image_url": None,
        "quantity": 1,
        "stored_unit_price_usd": "19.99",
        "current_catalog_price_usd": "19.99",
        "price_changed": False,
        "is_available": True,
        "line_subtotal_usd": "19.99",
        "row_version": 1,
        "created_at": "2026-09-11T09:30:00+00:00",
        "updated_at": "2026-09-11T09:30:00+00:00",
    }],
    "distinct_items": 1,
    "total_quantity": 1,
    "cart_subtotal_usd": "19.99",
}

ADDRESS = {
    "customer_address_id": 1,
    "label": "Home",
    "recipient_first_name": "Customer",
    "recipient_last_name": "Tester",
    "phone": None,
    "address_line_1": "1 Demo Street",
    "address_line_2": None,
    "city": "Manila",
    "province_region": "Metro Manila",
    "postal_code": "1000",
    "country_code": "PH",
    "is_default": True,
    "is_active": True,
    "row_version": 1,
    "created_at": "2026-09-11T09:30:00+00:00",
    "updated_at": "2026-09-11T09:30:00+00:00",
}

PAYMENT = {
    "payment_method_id": 2,
    "method_type": "card",
    "display_label": "Demo Card ending in 0000 - simulated",
    "card_brand": "Demo Card",
    "card_last_four": "0000",
    "is_default": True,
    "is_active": True,
    "row_version": 1,
    "created_at": "2026-09-11T09:30:00+00:00",
    "updated_at": "2026-09-11T09:30:00+00:00",
}


def _order_detail(status: str = "ready_shipped") -> dict:
    payment_status = "refunded" if status in {"cancelled", "refunded"} else "paid"
    return {
        "order_id": 70001,
        "created_at": "2026-09-11T10:00:00+00:00",
        "order_status": status,
        "total_quantity": 1,
        "total_usd": "19.99",
        "row_version": 1,
        "items": [{
            "order_item_id": 11,
            "product_id": 4,
            "product_name": "Configured Toy",
            "quantity": 1,
            "unit_price_usd": "19.99",
            "line_total_usd": "19.99",
        }],
        "shipping": {
            "recipient_first_name": "Customer",
            "recipient_last_name": "Tester",
            "phone": None,
            "address_line_1": "1 Demo Street",
            "address_line_2": None,
            "city": "Manila",
            "province_region": "Metro Manila",
            "postal_code": "1000",
            "country_code": "PH",
        },
        "payment": {
            "method_type": "card",
            "display_label": "Demo Card ending in 0000 - simulated",
            "payment_status": payment_status,
            "amount_usd": "19.99",
            "simulated_reference": "RM-DEMO-TEST",
        },
    }


def _install_customer_api(monkeypatch, state: dict, order_status: str = "ready_shipped") -> None:
    state.setdefault("addresses", [ADDRESS.copy()])
    state.setdefault("payments", [PAYMENT.copy()])
    state.setdefault("calls", [])

    def get(_: APIClient, path: str, params=None):
        state["calls"].append(path)
        if path == "/customer/auth/me":
            return CUSTOMER.copy()
        if path == "/customer/profile":
            return {"customer_account_id": CUSTOMER["customer_account_id"],
                    "first_name": CUSTOMER["first_name"], "last_name": CUSTOMER["last_name"],
                    "phone": CUSTOMER.get("phone"), "row_version": CUSTOMER["profile_row_version"]}
        if path == "/customer/store/products":
            return [PRODUCT.copy()]
        if path == "/customer/store/products/4":
            return PRODUCT.copy()
        if path == "/customer/cart":
            return CART.copy()
        if path == "/customer/addresses":
            return [value.copy() for value in state["addresses"]]
        if path == "/customer/payment-methods":
            return [value.copy() for value in state["payments"]]
        if path == "/customer/orders":
            current_status = state.get("order_status", order_status)
            return [{
                "order_id": 70001,
                "created_at": "2026-09-11T10:00:00+00:00",
                "order_status": current_status,
                "payment_status": "refunded" if current_status in {"cancelled", "refunded"} else "paid",
                "item_count": 1,
                "total_quantity": 1,
                "total_usd": "19.99",
                "row_version": 1,
            }]
        if path == "/customer/orders/70001":
            detail = _order_detail(state.get("order_status", order_status))
            detail["row_version"] = state.get("order_version", 1)
            if detail["order_status"] == "delivered":
                detail["delivered_at"] = "2026-09-11T11:00:00+00:00"
                detail["delivered_confirmed_by_customer"] = True
            return detail
        if path == "/customer/orders/70001/notifications":
            return {"mode": "mock", "items": [
                {"event_type": "order_confirmation", "channel": "email", "delivery_status": "sent"}]}
        if path == "/customer/orders/70001/refund-eligibility":
            state["eligibility_calls"] = state.get("eligibility_calls", 0) + 1
            default_eligibility = [{
                "order_item_id": 11,
                "product_id": 4,
                "product_name": "Configured Toy",
                "item_price_usd": "19.99",
                "remaining_refundable_usd": "19.99",
                "eligible": True,
                "reason": None,
                "current_request_status": None,
            }]
            return [value.copy() for value in state.get("eligibility", default_eligibility)]
        if path == "/customer/refund-requests":
            return [value.copy() for value in state.get("refund_requests", [])]
        raise AssertionError(path)

    def post(_: APIClient, path: str, payload=None):
        if path == "/customer/orders/70001/confirm-delivery":
            assert payload == {"row_version": state.get("order_version", 1)}
            state["order_status"] = "delivered"
            state["order_version"] = state.get("order_version", 1) + 1
            return _order_detail("delivered")
        if path == "/customer/checkout":
            detail = _order_detail("pending")
            return {
                **detail,
                "shipping": detail["shipping"],
                "payment": detail["payment"],
            }
        raise AssertionError(path)

    monkeypatch.setattr(APIClient, "get", get)
    monkeypatch.setattr(APIClient, "post", post)


def _customer_app() -> AppTest:
    app = AppTest.from_file(str(APP_FILE))
    app.session_state["customer_access_token"] = "customer-token"
    app.session_state["active_portal"] = "customer"
    return app.run(timeout=20)


def _button(app: AppTest, label: str):
    return next(button for button in app.button if button.label == label)


def _customer_nav(app: AppTest, label: str) -> AppTest:
    next(button for button in app.sidebar.button if button.label == label).click().run(timeout=20)
    return app


def _visible_customer_text(app: AppTest) -> str:
    element_groups = (
        app.title, app.header, app.subheader, app.markdown, app.caption,
        app.info, app.warning, app.success, app.error, app.button,
    )
    return " ".join(
        str(element.value if hasattr(element, "value") else element.label)
        for group in element_groups
        for element in group
    )


def test_customer_navigation_is_compact_button_menu(monkeypatch) -> None:
    _install_customer_api(monkeypatch, {})
    app = _customer_app()

    assert [button.label for button in app.sidebar.button] == [
        "Home / Shop", "Cart", "My Orders", "My Account", "Logout",
    ]
    assert not app.sidebar.radio


def test_shop_cart_checkout_and_product_back_navigation(monkeypatch) -> None:
    _install_customer_api(monkeypatch, {})
    app = _customer_app()
    assert not app.exception

    _customer_nav(app, "Cart")
    assert not app.exception
    assert "Your Cart" in [title.value for title in app.title]
    assert {"Update", "Remove", "Proceed to Checkout"} <= {button.label for button in app.button}

    _button(app, "Proceed to Checkout").click().run(timeout=20)
    assert not app.exception
    assert "Checkout" in [title.value for title in app.title]

    next(button for button in app.button if "Return to Cart" in button.label).click().run(timeout=20)
    assert not app.exception
    assert "Your Cart" in [title.value for title in app.title]

    _customer_nav(app, "Home / Shop")
    _button(app, "View Details").click().run(timeout=20)
    assert not app.exception
    assert "Back to products" in " ".join(button.label for button in app.button)
    next(button for button in app.button if "Back to products" in button.label).click().run(timeout=20)
    assert not app.exception
    assert "View Details" in [button.label for button in app.button]


def test_product_cards_keep_description_before_aligned_actions() -> None:
    storefront_source = (APP_FILE.parent / "views" / "storefront.py").read_text(encoding="utf-8")
    theme_source = (APP_FILE.parent / "ui.py").read_text(encoding="utf-8")

    marker = storefront_source.index('class="rm-product-card-marker"')
    description = storefront_source.index('class="rm-product-description"', marker)
    details = storefront_source.index('"View Details"', description)
    cart = storefront_source.index('"Add to Cart"', details)
    assert marker < description < details < cart
    assert "-webkit-line-clamp:2" in theme_source
    assert '[class*="st-key-view_product_"] {margin-top:auto;}' in theme_source


@pytest.mark.parametrize("missing_resource", ["address", "payment"])
def test_checkout_resources_are_refetched_after_my_account(monkeypatch, missing_resource: str) -> None:
    state = {
        "addresses": [] if missing_resource == "address" else [ADDRESS.copy()],
        "payments": [] if missing_resource == "payment" else [PAYMENT.copy()],
    }
    _install_customer_api(monkeypatch, state)
    app = _customer_app()
    _customer_nav(app, "Cart")
    _button(app, "Proceed to Checkout").click().run(timeout=20)
    assert not app.exception

    calls_before = state["calls"].count(
        "/customer/addresses" if missing_resource == "address" else "/customer/payment-methods"
    )
    _button(app, "Go to My Account").click().run(timeout=20)
    assert not app.exception
    assert "/customer/profile" in state["calls"]
    assert app.session_state["customer_navigation"] == "My Account"
    assert "My Account" in [title.value for title in app.title]

    state["addresses"] = [ADDRESS.copy()]
    state["payments"] = [PAYMENT.copy()]
    _customer_nav(app, "Cart")

    assert not app.exception
    assert "Checkout" in [title.value for title in app.title]
    assert "Shipping address" in [selectbox.label for selectbox in app.selectbox]
    assert "Payment method" in [selectbox.label for selectbox in app.selectbox]
    resource_path = "/customer/addresses" if missing_resource == "address" else "/customer/payment-methods"
    assert state["calls"].count(resource_path) > calls_before
    assert "resume_checkout_after_account" not in app.session_state


def test_checkout_resume_intent_is_cleared_when_customer_navigates_elsewhere(monkeypatch) -> None:
    state = {"addresses": [], "payments": [PAYMENT.copy()]}
    _install_customer_api(monkeypatch, state)
    app = _customer_app()
    _customer_nav(app, "Cart")
    _button(app, "Proceed to Checkout").click().run(timeout=20)
    _button(app, "Go to My Account").click().run(timeout=20)
    assert "resume_checkout_after_account" in app.session_state

    _customer_nav(app, "Home / Shop")
    assert not app.exception
    assert "resume_checkout_after_account" not in app.session_state

    _customer_nav(app, "Cart")
    assert not app.exception
    assert "Your Cart" in [title.value for title in app.title]


def test_checkout_confirmation_view_order_and_order_back_navigation(monkeypatch) -> None:
    _install_customer_api(monkeypatch, {})
    app = _customer_app()
    _customer_nav(app, "Cart")
    _button(app, "Proceed to Checkout").click().run(timeout=20)
    _button(app, "Place Order").click().run(timeout=20)
    assert not app.exception

    _button(app, "View Order").click().run(timeout=20)
    assert not app.exception
    assert app.session_state["customer_navigation"] == "My Orders"
    assert "Order #70001" in [heading.value for heading in app.subheader]
    assert "checkout_confirmation" not in app.session_state

    next(button for button in app.button if "Back to My Orders" in button.label).click().run(timeout=20)
    assert not app.exception
    assert "My Orders" in [title.value for title in app.title]

    _button(app, "View Order").click().run(timeout=20)
    assert not app.exception
    assert "Order #70001" in [heading.value for heading in app.subheader]


def test_checkout_confirmation_continue_shopping_navigation(monkeypatch) -> None:
    _install_customer_api(monkeypatch, {})
    app = _customer_app()
    _customer_nav(app, "Cart")
    _button(app, "Proceed to Checkout").click().run(timeout=20)
    _button(app, "Place Order").click().run(timeout=20)
    _button(app, "Continue Shopping").click().run(timeout=20)

    assert not app.exception
    assert app.session_state["customer_navigation"] == "Home / Shop"
    assert any("Toys for Brighter Days" in item.value for item in app.markdown)
    assert "checkout_confirmation" not in app.session_state


def test_customer_delivery_confirmation_prompt_and_button_disappearance(monkeypatch) -> None:
    state: dict = {}
    _install_customer_api(monkeypatch, state)
    app = _customer_app()
    _customer_nav(app, "My Orders")
    assert "Mark as Received" in [button.label for button in app.button]
    _button(app, "Mark as Received").click().run(timeout=20)
    assert not app.exception
    assert "Confirm that you have received this order?" in _visible_customer_text(app)
    _button(app, "Confirm receipt").click().run(timeout=20)
    assert not app.exception
    assert state["order_status"] == "delivered"
    assert "Order #70001 has been marked as delivered." in _visible_customer_text(app)
    assert "Mark as Received" not in [button.label for button in app.button]


@pytest.mark.parametrize(
    ("status", "message"),
    [
        ("cancelled", "Refund requests are not available for cancelled orders."),
        ("refunded", "This order has been fully refunded."),
    ],
)
def test_ineligible_final_order_states_do_not_render_refund_controls(
    monkeypatch, status: str, message: str
) -> None:
    state: dict = {}
    _install_customer_api(monkeypatch, state, order_status=status)
    app = _customer_app()
    _customer_nav(app, "My Orders")
    _button(app, "View Order").click().run(timeout=20)

    assert not app.exception
    visible_messages = [element.value for element in [*app.info, *app.success]]
    assert any(message in value for value in visible_messages)
    assert "Request Refund" not in [button.label for button in app.button]
    assert state.get("eligibility_calls", 0) == 0


def test_pending_refund_is_compact_and_has_no_duplicate_form(monkeypatch) -> None:
    state = {
        "eligibility": [{
            "order_item_id": 11,
            "product_id": 4,
            "product_name": "Configured Toy",
            "item_price_usd": "19.99",
            "remaining_refundable_usd": "19.99",
            "eligible": False,
            "reason": "A pending request already reserves this item.",
            "current_request_status": "pending",
        }]
    }
    _install_customer_api(monkeypatch, state)
    app = _customer_app()
    _customer_nav(app, "My Orders")
    _button(app, "View Order").click().run(timeout=20)
    assert any("eligibility" in expander.label.lower() for expander in app.expander)

    assert not app.exception
    assert "Refund request pending" in _visible_customer_text(app)
    assert "Request Refund" not in [button.label for button in app.button]
    assert not app.text_area


def test_eligible_refund_uses_product_first_compact_fields(monkeypatch) -> None:
    _install_customer_api(monkeypatch, {})
    app = _customer_app()
    _customer_nav(app, "My Orders")
    _button(app, "View Order").click().run(timeout=20)
    assert any("eligibility" in expander.label.lower() for expander in app.expander)

    visible = _visible_customer_text(app)
    assert "Configured Toy" in visible
    assert "Purchased amount" in visible
    assert "Remaining refundable" in visible
    assert "Item #11" not in visible
    assert "Reason" in [field.label for field in app.text_input]
    assert not app.text_area
    assert "Request Refund" in [button.label for button in app.button]


def test_customer_pages_hide_internal_and_project_evidence_copy(monkeypatch) -> None:
    _install_customer_api(monkeypatch, {})
    app = _customer_app()
    pages = []
    for destination in ("Home / Shop", "Cart", "My Orders", "My Account"):
        _customer_nav(app, destination)
        pages.append(_visible_customer_text(app).lower())

    visible = " ".join(pages)
    for forbidden in (
        "record_origin", "canonical", "row_version", "synthetic session",
        "fastapi", "authoritative", "immutable snapshot", "customer-origin",
        "migration", "reconciliation", "grpc", "protobuf",
    ):
        assert forbidden not in visible
    assert "customer id" not in visible


def test_customer_account_has_expected_business_sections(monkeypatch) -> None:
    _install_customer_api(monkeypatch, {})
    app = _customer_app()
    _customer_nav(app, "My Account")

    assert [tab.label for tab in app.tabs] == [
        "Profile", "Addresses", "Payment Methods", "Security",
    ]
    assert "Customer ID" not in _visible_customer_text(app)
