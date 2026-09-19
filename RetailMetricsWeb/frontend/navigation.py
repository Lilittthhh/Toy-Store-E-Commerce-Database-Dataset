from __future__ import annotations

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
        ("System", ("Dashboard", "User Management", "Customer Accounts", "Audit Trail", "Notification Test")),
        ("Business", ("Customers", "Products", "Storefront Catalog", "Orders", "Refund Requests", "Refunds")),
        ("Analytics", ("Website Traffic", "Analytics Dashboard", "Business Reports", "Project Evidence")),
        ("Account", ("My Account", "Logout")),
    ),
    "operations_staff": (
        ("Operations", ("Dashboard", "Customers", "Orders", "Refund Requests", "Refunds")),
        ("Reference", ("Products", "Storefront Catalog")),
        ("Account", ("My Account", "Logout")),
    ),
    "analyst": (
        ("Analytics", ("Analytics Dashboard", "Customers", "Products", "Orders", "Refunds", "Website Traffic", "Business Reports")),
        ("Account", ("My Account", "Logout")),
    ),
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


def render_customer_navigation() -> str:
    """Render customer navigation as an application menu instead of a radio group."""
    if st.session_state.get(CUSTOMER_NAVIGATION_KEY) not in CUSTOMER_ACCOUNT_NAVIGATION:
        st.session_state[CUSTOMER_NAVIGATION_KEY] = CUSTOMER_ACCOUNT_NAVIGATION[0]
    current = st.session_state[CUSTOMER_NAVIGATION_KEY]
    keys = {
        "Home / Shop": "home",
        "Cart": "cart",
        "My Orders": "orders",
        "My Account": "account",
        "Logout": "logout",
    }
    for page in CUSTOMER_ACCOUNT_NAVIGATION:
        st.sidebar.button(
            page,
            key=f"customer_nav_{keys[page]}",
            use_container_width=True,
            type="primary" if page == current else "secondary",
            on_click=_select_customer_navigation,
            args=(page,),
        )
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
                                 type="primary" if page == st.session_state.staff_page else "secondary"):
                st.session_state.staff_page = page
                st.rerun()
    return st.session_state.staff_page
