from __future__ import annotations

from html import escape

import streamlit as st


PUBLIC_NAVIGATION = ("Login", "Register", "Forgot / Reset Password")
PORTAL_NAVIGATION = ("Customer Portal", "Staff Portal")
CUSTOMER_PUBLIC_NAVIGATION = ("Customer Login", "Customer Register", "Forgot / Reset Password")
CUSTOMER_ACCOUNT_NAVIGATION = ("Home / Shop", "Cart", "My Orders", "My Account", "Logout")
CUSTOMER_NAVIGATION_KEY = "customer_navigation"
PENDING_CUSTOMER_NAVIGATION_KEY = "pending_customer_navigation"
INTERNAL_MODULE_NAMES = {
    "app",
    "auth pages",
    "auth views",
    "entity pages",
    "entity views",
    "readonly pages",
    "readonly views",
}

ROLE_SECTIONS: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "admin": (
        ("Overview", ("Dashboard",)),
        ("Store operations", ("Orders", "Refund Requests", "Products", "Storefront Catalog", "Customers")),
        ("Administration", ("User Management", "Customer Accounts", "Audit Trail", "Notification Test")),
        ("Analytics", ("Website Traffic", "Analytics Dashboard", "Business Reports", "Project Evidence")),
        ("Account", ("My Account", "Logout")),
    ),
    "operations_staff": (
        ("Operations", ("Dashboard", "Customers", "Orders", "Refund Requests")),
        ("Reference", ("Products", "Storefront Catalog")),
        ("Account", ("My Account", "Logout")),
    ),
    "analyst": (
        ("Analytics", ("Analytics Dashboard", "Customers", "Products", "Orders", "Refund Requests", "Website Traffic", "Business Reports")),
        ("Account", ("My Account", "Logout")),
    ),
}

PAGE_ICONS = {
    "Dashboard": ":material/dashboard:", "Orders": ":material/package_2:",
    "Refund Requests": ":material/assignment_return:",
    "Products": ":material/toys:", "Storefront Catalog": ":material/storefront:",
    "Customers": ":material/group:", "User Management": ":material/manage_accounts:",
    "Customer Accounts": ":material/contacts:", "Audit Trail": ":material/history:",
    "Notification Test": ":material/notifications:", "Website Traffic": ":material/public:",
    "Analytics Dashboard": ":material/monitoring:", "Business Reports": ":material/description:",
    "Project Evidence": ":material/folder:", "My Account": ":material/account_circle:",
    "Logout": ":material/logout:",
}


def navigation_for_role(role: str) -> tuple[str, ...]:
    return tuple(page for _, pages in ROLE_SECTIONS[role] for page in pages)


def request_customer_navigation(destination: str) -> None:
    """Queue customer navigation without mutating an instantiated widget key."""
    if destination not in CUSTOMER_ACCOUNT_NAVIGATION:
        raise ValueError(f"Unknown customer navigation destination: {destination}")
    st.session_state[PENDING_CUSTOMER_NAVIGATION_KEY] = destination


def apply_pending_customer_navigation() -> None:
    """Apply a queued destination before customer navigation is rendered."""
    destination = st.session_state.pop(PENDING_CUSTOMER_NAVIGATION_KEY, None)
    if destination is not None:
        st.session_state[CUSTOMER_NAVIGATION_KEY] = destination


def _select_customer_navigation(destination: str) -> None:
    st.session_state[CUSTOMER_NAVIGATION_KEY] = destination


def _customer_nav_button(container, label: str, destination: str, key: str, current: str) -> None:
    container.button(
        label,
        key=key,
        use_container_width=True,
        type="primary" if destination == current else "secondary",
        on_click=_select_customer_navigation,
        args=(destination,),
    )


def render_customer_navigation(customer: dict, cart_count: int = 0) -> str:
    """Render the customer website header without using the staff sidebar shell."""
    if st.session_state.get(CUSTOMER_NAVIGATION_KEY) not in CUSTOMER_ACCOUNT_NAVIGATION:
        st.session_state[CUSTOMER_NAVIGATION_KEY] = CUSTOMER_ACCOUNT_NAVIGATION[0]
    current = st.session_state[CUSTOMER_NAVIGATION_KEY]
    first_name = customer.get("first_name") or "Account"
    st.markdown(
        '<div class="rm-customer-ribbon">Little discoveries. Everyday adventures. Welcome to our toy store.</div>',
        unsafe_allow_html=True,
    )
    with st.container(key="customer_site_header"):
        brand, shop, cart, orders, account = st.columns([2.3, .8, 1, 1.05, 1.25], vertical_alignment="center")
        brand.markdown(
            '<div class="rm-site-brand"><span class="rm-site-brand-mark">RM</span><div>'
            '<strong>RetailMetrics</strong><small>Toy Store · Shop &amp; track orders</small></div></div>',
            unsafe_allow_html=True,
        )
        _customer_nav_button(shop, "Shop", "Home / Shop", "customer_desktop_shop", current)
        _customer_nav_button(cart, f"Cart · {cart_count}", "Cart", "customer_desktop_cart", current)
        _customer_nav_button(orders, "My Orders", "My Orders", "customer_desktop_orders", current)
        with account.popover(f"{first_name} ▾", use_container_width=True):
            st.caption(customer.get("email", "Customer account"))
            _customer_nav_button(st, "My Account", "My Account", "customer_desktop_account", current)
            _customer_nav_button(st, "Log out", "Logout", "customer_desktop_logout", current)

    with st.container(key="customer_mobile_header"):
        brand, cart, menu = st.columns([2.2, 1, .78], vertical_alignment="center")
        brand.markdown(
            '<div class="rm-site-brand"><span class="rm-site-brand-mark">RM</span><div>'
            '<strong>RetailMetrics</strong><small>Toy Store · Shop &amp; track orders</small></div></div>',
            unsafe_allow_html=True,
        )
        _customer_nav_button(cart, f"Cart · {cart_count}", "Cart", "customer_mobile_cart", current)
        with menu.popover("Menu", use_container_width=True):
            st.markdown(f'<div class="rm-mobile-account"><strong>{escape(first_name)}</strong><span>{escape(customer.get("email", ""))}</span></div>', unsafe_allow_html=True)
            _customer_nav_button(st, "Shop", "Home / Shop", "customer_mobile_shop", current)
            _customer_nav_button(st, "My Orders", "My Orders", "customer_mobile_orders", current)
            _customer_nav_button(st, "My Account", "My Account", "customer_mobile_account", current)
            _customer_nav_button(st, "Log out", "Logout", "customer_mobile_logout", current)
    return current


def render_staff_navigation(role: str) -> str:
    pages = navigation_for_role(role)
    default = "Analytics Dashboard" if role == "analyst" else "Dashboard"
    if st.session_state.get("staff_page") not in pages:
        st.session_state.staff_page = default
    for section, choices in ROLE_SECTIONS[role]:
        st.sidebar.markdown(f'<div class="rm-nav-section">{section}</div>', unsafe_allow_html=True)
        for page in choices:
            if st.sidebar.button(page, key=f"nav_{role}_{page}", use_container_width=True,
                                 icon=PAGE_ICONS.get(page),
                                 type="primary" if page == st.session_state.staff_page else "secondary"):
                st.session_state.staff_page = page
                st.rerun()
    return st.session_state.staff_page
