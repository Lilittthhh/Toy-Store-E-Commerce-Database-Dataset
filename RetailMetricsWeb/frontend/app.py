from __future__ import annotations

import streamlit as st

from frontend.api_client import APIClient, APIError
from frontend.auth import initialize_session, sign_out
from frontend.browser_session import sync_browser_cookie
from frontend.customer_auth import customer_sign_out, initialize_customer_session
from frontend.customer_browser_session import sync_customer_browser_cookie
from frontend.navigation import (
    apply_pending_customer_navigation,
    render_customer_navigation,
    render_staff_navigation,
)
from frontend.views import (
    customer_account,
    customer_management,
    catalog_management,
    dashboard,
    entity_views,
    my_account,
    readonly_views,
    user_management,
    storefront,
    refund_requests,
    analytics_dashboard,
    staff_customers,
    reports,
    business_reports,
    website_traffic,
    notification_test,
    audit_trail,
)
from frontend.views.unified_auth import render as render_unified_auth
from frontend.ui import (
    apply_anonymous_theme,
    apply_customer_theme,
    apply_theme,
    page_header,
    render_sidebar_brand,
)


st.set_page_config(
    page_title="RetailMetrics",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_theme()
initialize_session()
initialize_customer_session()
sync_browser_cookie()
sync_customer_browser_cookie()


def anonymous_app() -> None:
    client = APIClient()
    apply_anonymous_theme()
    render_unified_auth(client)


def authenticated_app() -> None:
    client = APIClient(token=st.session_state.access_token)
    try:
        user = client.get("/auth/me")
        st.session_state.current_user = user
    except APIError as exc:
        sign_out()
        st.error("Your session is no longer valid. Please sign in again.")
        if exc.status_code not in {401, 403, 423}:
            st.caption(exc.message)
        st.rerun()
        return

    role = user["role"]
    render_sidebar_brand(user["username"], role)
    selected = render_staff_navigation(role)

    if selected == "Dashboard":
        dashboard.render(client)
    elif selected == "Analytics Dashboard":
        analytics_dashboard.render(client)
    elif selected == "Customers":
        staff_customers.render(client)
    elif selected == "Products":
        entity_views.render(client, "products")
    elif selected == "Orders":
        entity_views.render(client, "orders")
    elif selected == "Refunds":
        entity_views.render(client, "refunds")
    elif selected == "Refund Requests":
        refund_requests.render(client)
    elif selected == "Website Sessions":
        readonly_views.render_sessions(client)
    elif selected == "Website Pageviews":
        readonly_views.render_pageviews(client)
    elif selected == "Storefront Catalog":
        catalog_management.render(client)
    elif selected == "User Management":
        user_management.render(client, user)
    elif selected == "Customer Accounts":
        customer_management.render(client)
    elif selected == "Notification Test":
        notification_test.render(client)
    elif selected == "Audit Trail" and role == "admin":
        audit_trail.render(client)
    elif selected == "Business Reports":
        business_reports.render(client)
    elif selected == "Project Evidence":
        reports.render(client)
    elif selected == "Website Traffic":
        website_traffic.render(client)
    elif selected == "My Account":
        my_account.render(client, user)
    else:
        page_header("Logout", "Sign out of RetailMetrics on this device.")
        st.info("You will need to sign in again to return to your workspace.")
        if st.button("Log out", type="primary"):
            try:
                client.post("/auth/logout")
            except APIError:
                pass
            sign_out()
            st.rerun()


def customer_authenticated_app() -> None:
    apply_customer_theme()
    client = APIClient(token=st.session_state.customer_access_token)
    try:
        customer = client.get("/customer/auth/me")
        st.session_state.current_customer = customer
    except APIError as exc:
        customer_sign_out()
        st.error("Your customer session is no longer valid. Please sign in again.")
        if exc.status_code not in {401, 403, 423}:
            st.caption(exc.message)
        st.rerun()
        return

    render_sidebar_brand(customer["email"], "customer")
    apply_pending_customer_navigation()
    selected = render_customer_navigation()
    st.sidebar.markdown(
        '<div class="rm-customer-sidebar-footer">♥ Making every toy bring a little more joy.</div>',
        unsafe_allow_html=True,
    )
    if selected not in {"Cart", "My Account"}:
        st.session_state.pop("resume_checkout_after_account", None)
    if selected == "Home / Shop":
        storefront.render_shop(client, customer)
    elif selected == "Cart":
        storefront.render_cart(client)
    elif selected == "My Orders":
        storefront.render_orders(client)
    elif selected == "My Account":
        customer_account.render(client, customer)
    else:
        page_header("Customer Logout", "Securely end this customer session on the current device.")
        if st.button("Log out", type="primary"):
            try:
                client.post("/customer/auth/logout")
            except APIError:
                pass
            customer_sign_out()
            st.rerun()


if st.session_state.customer_access_token and st.session_state.active_portal != "staff":
    customer_authenticated_app()
elif st.session_state.access_token:
    authenticated_app()
elif st.session_state.customer_access_token:
    customer_authenticated_app()
else:
    anonymous_app()
