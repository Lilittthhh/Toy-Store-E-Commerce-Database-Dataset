"""Transaction-bound, allowlisted application audit events.

The caller never passes request bodies, tokens, or arbitrary user text to SQL.
Enabled only after Migration 005 has been reviewed and applied.
"""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Any

from psycopg2.extras import Json


SAFE_CHANGE_KEYS = frozenset({
    "order_status", "request_status", "role", "is_active", "is_available",
    "quantity", "delivered_confirmed_by_customer", "row_version",
})


def sanitize_values(values: dict[str, Any] | None) -> dict[str, Any] | None:
    """Permit only known business-state scalars, never a submitted object wholesale."""
    if not values:
        return None
    allowed_strings = {
        "order_status": {"pending", "processing", "ready_shipped", "delivered", "cancelled", "refunded"},
        "request_status": {"pending", "approved", "rejected", "processed"},
        "role": {"admin", "operations_staff", "analyst", "customer"},
    }
    safe = {}
    for key, value in values.items():
        if key not in SAFE_CHANGE_KEYS:
            continue
        if key in allowed_strings and type(value) is str and value in allowed_strings[key]:
            safe[key] = value
        elif key in {"is_active", "is_available", "delivered_confirmed_by_customer"} and type(value) is bool:
            safe[key] = value
        elif key in {"quantity", "row_version"} and type(value) is int and 0 <= value <= 1_000_000:
            safe[key] = value
    return safe or None


@dataclass(frozen=True)
class AuditEvent:
    action: str
    entity_type: str | None = None
    entity_id: str | None = None
    old_values: dict[str, Any] | None = None
    new_values: dict[str, Any] | None = None


def set_actor(request, actor_type: str, actor_id: int, role: str) -> None:
    request.state.audit_actor = (actor_type, actor_id, role)


def set_entity_id(request, entity_id: int) -> None:
    request.state.audit_entity_id = str(entity_id)


def set_change_values(request, *, old: dict[str, Any] | None = None,
                      new: dict[str, Any] | None = None) -> None:
    """Attach only allowlisted business-state values; never store a request object."""
    request.state.audit_old_values = sanitize_values(old)
    request.state.audit_new_values = sanitize_values(new)


# (HTTP method, FastAPI route template) -> action, entity, entity path parameter, old, new.
# One successful routed HTTP request yields at most one event. Internal service
# calls are never audited separately; framework, auth /me, and helper GETs are
# deliberately absent from this allowlist.
POLICY: dict[tuple[str, str], tuple[str, str | None, str | None, dict | None, dict | None]] = {
    ("POST", "/auth/register"): ("STAFF_REGISTERED", "app_user", None, None, None),
    ("POST", "/auth/login"): ("STAFF_LOGIN_SUCCESS", "app_user", None, None, None),
    ("POST", "/auth/logout"): ("STAFF_LOGOUT", "app_user", None, None, None),
    ("POST", "/auth/change-password"): ("STAFF_PASSWORD_CHANGED", "app_user", None, None, None),
    ("POST", "/auth/forgot-password"): ("STAFF_PASSWORD_RESET_REQUESTED", None, None, None, None),
    ("POST", "/auth/reset-password"): ("STAFF_PASSWORD_RESET_COMPLETED", None, None, None, None),
    ("POST", "/customer/auth/register"): ("CUSTOMER_REGISTERED", "customer_account", None, None, None),
    ("POST", "/customer/auth/login"): ("CUSTOMER_LOGIN_SUCCESS", "customer_account", None, None, None),
    ("POST", "/customer/auth/logout"): ("CUSTOMER_LOGOUT", "customer_account", None, None, None),
    ("POST", "/customer/auth/change-password"): ("CUSTOMER_PASSWORD_CHANGED", "customer_account", None, None, None),
    ("POST", "/customer/auth/forgot-password"): ("CUSTOMER_PASSWORD_RESET_REQUESTED", None, None, None, None),
    ("POST", "/customer/auth/reset-password"): ("CUSTOMER_PASSWORD_RESET_COMPLETED", None, None, None, None),
    ("PUT", "/customer/profile"): ("CUSTOMER_PROFILE_UPDATED", "customer_profile", None, None, None),
    ("POST", "/customer/addresses"): ("CUSTOMER_ADDRESS_CREATED", "customer_address", None, None, None),
    ("PUT", "/customer/addresses/{address_id}"): ("CUSTOMER_ADDRESS_UPDATED", "customer_address", "address_id", None, None),
    ("POST", "/customer/addresses/{address_id}/set-default"): ("CUSTOMER_ADDRESS_DEFAULT_CHANGED", "customer_address", "address_id", None, None),
    ("POST", "/customer/addresses/{address_id}/deactivate"): ("CUSTOMER_ADDRESS_DEACTIVATED", "customer_address", "address_id", None, {"is_active": False}),
    ("POST", "/customer/payment-methods"): ("PAYMENT_METHOD_CREATED", "payment_method", None, None, None),
    ("PUT", "/customer/payment-methods/{payment_method_id}"): ("PAYMENT_METHOD_UPDATED", "payment_method", "payment_method_id", None, None),
    ("POST", "/customer/payment-methods/{payment_method_id}/set-default"): ("PAYMENT_METHOD_DEFAULT_CHANGED", "payment_method", "payment_method_id", None, None),
    ("POST", "/customer/payment-methods/{payment_method_id}/deactivate"): ("PAYMENT_METHOD_DEACTIVATED", "payment_method", "payment_method_id", None, {"is_active": False}),
    ("POST", "/customer/cart/items"): ("CART_ITEM_ADDED", "cart_item", None, None, None),
    ("PUT", "/customer/cart/items/{cart_item_id}"): ("CART_ITEM_QUANTITY_UPDATED", "cart_item", "cart_item_id", None, None),
    ("DELETE", "/customer/cart/items/{cart_item_id}"): ("CART_ITEM_REMOVED", "cart_item", "cart_item_id", None, None),
    ("POST", "/customer/checkout"): ("ORDER_CREATED", "order", None, None, {"order_status": "pending"}),
    ("POST", "/customer/orders/{order_id}/cancel"): ("ORDER_CANCELLED", "order", "order_id", {"order_status": "pending"}, {"order_status": "cancelled"}),
    ("POST", "/customer/orders/{order_id}/confirm-delivery"): ("ORDER_DELIVERY_CONFIRMED", "order", "order_id", {"order_status": "ready_shipped"}, {"order_status": "delivered", "delivered_confirmed_by_customer": True}),
    ("POST", "/orders/{order_id}/start-processing"): ("ORDER_STATUS_CHANGED", "order", "order_id", {"order_status": "pending"}, {"order_status": "processing"}),
    ("POST", "/orders/{order_id}/ready-shipped"): ("ORDER_STATUS_CHANGED", "order", "order_id", {"order_status": "processing"}, {"order_status": "ready_shipped"}),
    ("POST", "/orders/{order_id}/cancel"): ("ORDER_CANCELLED", "order", "order_id", {"order_status": "pending"}, {"order_status": "cancelled"}),
    ("POST", "/customer/refund-requests"): ("REFUND_REQUESTED", "refund_request", None, None, {"request_status": "pending"}),
    ("POST", "/refund-requests/{request_id}/approve"): ("REFUND_APPROVED", "refund_request", "request_id", {"request_status": "pending"}, {"request_status": "approved"}),
    ("POST", "/refund-requests/{request_id}/reject"): ("REFUND_REJECTED", "refund_request", "request_id", {"request_status": "pending"}, {"request_status": "rejected"}),
    ("POST", "/refund-requests/{request_id}/process"): ("REFUND_PROCESSED", "refund_request", "request_id", {"request_status": "approved"}, {"request_status": "processed"}),
    ("POST", "/admin/users"): ("STAFF_ACCOUNT_CREATED", "app_user", None, None, None),
    ("PUT", "/admin/users/{app_user_id}/role"): ("STAFF_ROLE_CHANGED", "app_user", "app_user_id", None, None),
    ("PUT", "/admin/users/{app_user_id}/status"): ("STAFF_STATUS_CHANGED", "app_user", "app_user_id", None, None),
    ("POST", "/admin/users/{app_user_id}/unlock"): ("STAFF_ACCOUNT_UNLOCKED", "app_user", "app_user_id", None, None),
    ("PUT", "/admin/customers/{customer_account_id}/status"): ("CUSTOMER_STATUS_CHANGED", "customer_account", "customer_account_id", None, None),
    ("POST", "/admin/customers/{customer_account_id}/unlock"): ("CUSTOMER_ACCOUNT_UNLOCKED", "customer_account", "customer_account_id", None, None),
    ("PUT", "/admin/catalog/{product_id}"): ("CATALOG_UPDATED", "product_catalog", "product_id", None, None),
    ("POST", "/products"): ("PRODUCT_CREATED", "product", None, None, None),
    ("PUT", "/products/{product_id}"): ("PRODUCT_UPDATED", "product", "product_id", None, None),
    ("DELETE", "/products/{product_id}"): ("PRODUCT_DELETED", "product", "product_id", None, None),
    ("POST", "/orders"): ("STAFF_ORDER_CREATED", "order", None, None, None),
    ("PUT", "/orders/{order_id}"): ("STAFF_ORDER_UPDATED", "order", "order_id", None, None),
    ("DELETE", "/orders/{order_id}"): ("STAFF_ORDER_DELETED", "order", "order_id", None, None),
    ("POST", "/order-items"): ("STAFF_ORDER_ITEM_CREATED", "order_item", None, None, None),
    ("PUT", "/order-items/{order_item_id}"): ("STAFF_ORDER_ITEM_UPDATED", "order_item", "order_item_id", None, None),
    ("DELETE", "/order-items/{order_item_id}"): ("STAFF_ORDER_ITEM_DELETED", "order_item", "order_item_id", None, None),
    ("POST", "/refunds"): ("STAFF_REFUND_CREATED", "refund", None, None, None),
    ("PUT", "/refunds/{refund_id}"): ("STAFF_REFUND_UPDATED", "refund", "refund_id", None, None),
    ("DELETE", "/refunds/{refund_id}"): ("STAFF_REFUND_DELETED", "refund", "refund_id", None, None),

    # Meaningful authenticated views. No query string, search term, or result
    # body is copied into an audit entry. Detail IDs come only from typed path
    # parameters; pure reads leave old_values/new_values NULL.
    ("GET", "/admin/audit-logs"): ("VIEW_AUDIT_TRAIL", "audit_log", None, None, None),
    ("GET", "/admin/audit-logs/{audit_log_id}"): ("VIEW_AUDIT_DETAIL", "audit_log", "audit_log_id", None, None),
    ("GET", "/admin/users"): ("VIEW_STAFF_LIST", "app_user", None, None, None),
    ("GET", "/admin/users/{app_user_id}"): ("VIEW_STAFF_DETAIL", "app_user", "app_user_id", None, None),
    ("GET", "/admin/customers"): ("VIEW_CUSTOMER_LIST", "customer_account", None, None, None),
    ("GET", "/admin/customers/{customer_account_id}"): ("VIEW_CUSTOMER_DETAIL", "customer_account", "customer_account_id", None, None),
    ("GET", "/products"): ("VIEW_PRODUCT_LIST", "product", None, None, None),
    ("GET", "/products/{product_id}"): ("VIEW_PRODUCT_DETAIL", "product", "product_id", None, None),
    ("GET", "/orders"): ("VIEW_IMPORTED_ORDER_LIST", "order", None, None, None),
    ("GET", "/orders/{order_id}"): ("VIEW_ORDER_DETAIL", "order", "order_id", None, None),
    ("GET", "/order-items"): ("VIEW_ORDER_ITEM_LIST", "order_item", None, None, None),
    ("GET", "/order-items/{order_item_id}"): ("VIEW_ORDER_ITEM_DETAIL", "order_item", "order_item_id", None, None),
    ("GET", "/refunds"): ("VIEW_REFUND_LIST", "refund", None, None, None),
    ("GET", "/refunds/{refund_id}"): ("VIEW_REFUND_DETAIL", "refund", "refund_id", None, None),
    ("GET", "/website-sessions"): ("VIEW_WEBSITE_SESSIONS", "website_session", None, None, None),
    ("GET", "/website-sessions/{website_session_id}"): ("VIEW_WEBSITE_SESSION_DETAIL", "website_session", "website_session_id", None, None),
    ("GET", "/website-pageviews"): ("VIEW_WEBSITE_PAGEVIEWS", "website_pageview", None, None, None),
    ("GET", "/website-pageviews/{website_pageview_id}"): ("VIEW_WEBSITE_PAGEVIEW_DETAIL", "website_pageview", "website_pageview_id", None, None),
    ("GET", "/analytics/workspace"): ("VIEW_DASHBOARD", "dashboard", None, None, None),
    ("GET", "/analytics/dashboard"): ("VIEW_ANALYTICS", "analytics", None, None, None),
    ("GET", "/analytics/reports"): ("VIEW_REPORT", "report", None, None, None),
    ("GET", "/staff/customers/historical"): ("VIEW_HISTORICAL_SHOPPER_LIST", "historical_shopper", None, None, None),
    ("GET", "/staff/customers/historical/{dataset_user_id}"): ("VIEW_HISTORICAL_SHOPPER_DETAIL", "historical_shopper", "dataset_user_id", None, None),
    ("GET", "/staff/customers/registered"): ("VIEW_REGISTERED_CUSTOMER_LIST", "customer_account", None, None, None),
    ("GET", "/admin/catalog"): ("VIEW_CATALOG_LIST", "product_catalog", None, None, None),
    ("GET", "/admin/catalog/{product_id}"): ("VIEW_CATALOG_DETAIL", "product_catalog", "product_id", None, None),
    ("GET", "/order-workflow/orders"): ("VIEW_ORDER_LIST", "order", None, None, None),
    ("GET", "/refund-requests"): ("VIEW_REFUND_REQUEST_QUEUE", "refund_request", None, None, None),
    ("GET", "/refund-requests/{request_id}"): ("VIEW_REFUND_REQUEST_DETAIL", "refund_request", "request_id", None, None),
    ("GET", "/customer/profile"): ("VIEW_PROFILE", "customer_profile", None, None, None),
    ("GET", "/customer/addresses"): ("VIEW_ADDRESSES", "customer_address", None, None, None),
    ("GET", "/customer/addresses/{address_id}"): ("VIEW_ADDRESS_DETAIL", "customer_address", "address_id", None, None),
    ("GET", "/customer/payment-methods"): ("VIEW_PAYMENT_METHODS", "payment_method", None, None, None),
    ("GET", "/customer/payment-methods/{payment_method_id}"): ("VIEW_PAYMENT_METHOD_DETAIL", "payment_method", "payment_method_id", None, None),
    ("GET", "/customer/store/products"): ("VIEW_PRODUCT_LIST", "product", None, None, None),
    ("GET", "/customer/store/products/{product_id}"): ("VIEW_PRODUCT_DETAIL", "product", "product_id", None, None),
    ("GET", "/customer/cart"): ("VIEW_CART", "cart", None, None, None),
    ("GET", "/customer/orders"): ("VIEW_ORDER_HISTORY", "order", None, None, None),
    ("GET", "/customer/orders/{order_id}"): ("VIEW_ORDER_DETAIL", "order", "order_id", None, None),
    ("GET", "/customer/refund-requests"): ("VIEW_REFUND_STATUS", "refund_request", None, None, None),
    ("GET", "/customer/refund-requests/{request_id}"): ("VIEW_REFUND_STATUS", "refund_request", "request_id", None, None),
}


def event_for_request(request) -> AuditEvent | None:
    route = request.scope.get("route")
    spec = POLICY.get((request.method, getattr(route, "path", "")))
    if spec is None:
        return None
    if request.method == "GET" and not hasattr(request.state, "audit_actor"):
        # Unauthorized / anonymous reads must not create view records.
        return None
    action, entity_type, path_key, old_values, new_values = spec
    entity_id = getattr(request.state, "audit_entity_id", None)
    if entity_id is None and path_key:
        value = request.path_params.get(path_key)
        entity_id = str(value) if value is not None else None
    old = None if request.method == "GET" else getattr(request.state, "audit_old_values", None) or old_values
    new = None if request.method == "GET" else getattr(request.state, "audit_new_values", None) or new_values
    return AuditEvent(action, entity_type, entity_id, sanitize_values(old), sanitize_values(new))


def _safe_ip(request) -> str | None:
    try:
        return str(ipaddress.ip_address(request.client.host)) if request.client else None
    except ValueError:
        return None


def write_event(conn, request, event: AuditEvent) -> None:
    actor_type, actor_id, actor_role = getattr(request.state, "audit_actor", ("anonymous", None, None))
    actor_display = f"{actor_type.title()} #{actor_id}" if actor_id else None
    description = f"{event.action.replace('_', ' ').title()} on {event.entity_type or 'account'}."
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO public.audit_logs
               (actor_type,actor_id,actor_role,actor_display,action,entity_type,entity_id,
                description,old_values,new_values,ip_address)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (actor_type, actor_id, actor_role, actor_display, event.action, event.entity_type,
             event.entity_id, description, Json(sanitize_values(event.old_values)) if event.old_values else None,
             Json(sanitize_values(event.new_values)) if event.new_values else None, _safe_ip(request)),
        )
