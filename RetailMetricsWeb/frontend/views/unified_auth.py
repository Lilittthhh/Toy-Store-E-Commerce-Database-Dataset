from __future__ import annotations

import re

import streamlit as st

from frontend.api_client import APIClient, APIError
from frontend.auth import sign_in
from frontend.customer_auth import customer_sign_in
from frontend.ui import auth_card_header, show_api_error
from frontend.views.customer_auth_views import render_register as render_customer_register


VIEW_KEY = "anonymous_auth_view"
GENERIC_LOGIN_ERROR = "Invalid username/email or password."


def _change_view(view: str) -> None:
    st.session_state[VIEW_KEY] = view


def _looks_like_email(identifier: str) -> bool:
    return bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", identifier.strip()))


def _authenticate_staff(client: APIClient, identifier: str, password: str) -> bool:
    try:
        token = client.post("/auth/login", {"identifier": identifier, "password": password})
        user = APIClient(token=token["access_token"]).get("/auth/me")
        sign_in(token["access_token"], user, token["expires_in"])
        return True
    except APIError:
        return False


def _authenticate_customer(client: APIClient, identifier: str, password: str) -> bool:
    try:
        token = client.post("/customer/auth/login", {"email": identifier, "password": password})
        authenticated = APIClient(token=token["access_token"])
        customer = authenticated.get("/customer/auth/me")
    except APIError:
        return False

    guest_cart = st.session_state.get("guest_cart", {})
    transferred = []
    for key, item in list(guest_cart.items()):
        try:
            authenticated.post(
                "/customer/cart/items",
                {"product_id": int(item["product"]["product_id"]), "quantity": int(item["quantity"])},
            )
            transferred.append(key)
        except APIError:
            st.session_state["guest_cart_transfer_warning"] = True
            break
    for key in transferred:
        guest_cart.pop(key, None)
    customer_sign_in(token["access_token"], customer, token["expires_in"])
    if transferred or st.session_state.pop("guest_checkout_intent", False):
        st.session_state["customer_navigation"] = "Cart"
    return True


def render_login(client: APIClient) -> None:
    card = auth_card_header("Welcome back", "Sign in to continue to your account.")
    with card:
        identifier = st.text_input("Email or username", key="unified_login_identifier")
        password = st.text_input(
            "Password",
            type="password",
            key="unified_login_password",
        )
        st.button(
            "Forgot password?",
            key="unified_forgot_password",
            on_click=_change_view,
            args=("recovery",),
        )
        submitted = st.button(
            "Sign In",
            key="unified_sign_in",
            type="primary",
            use_container_width=True,
        )
        if submitted:
            # Deterministic ambiguity policy: a valid staff login always takes precedence.
            authenticated = _authenticate_staff(client, identifier.strip(), password)
            if not authenticated and _looks_like_email(identifier):
                authenticated = _authenticate_customer(client, identifier.strip(), password)
            if authenticated:
                st.rerun()
            else:
                st.error(GENERIC_LOGIN_ERROR)
        footer_label, footer_action = st.columns([1, 1.35], vertical_alignment="center")
        footer_label.markdown(
            '<div class="rm-auth-footer-label">New customer?</div>', unsafe_allow_html=True
        )
        footer_action.button(
            "Create an account",
            key="unified_create_account",
            on_click=_change_view,
            args=("register",),
            use_container_width=True,
        )


def _request_reset(client: APIClient, email: str) -> None:
    for path in ("/auth/forgot-password", "/customer/auth/forgot-password"):
        try:
            client.post(path, {"email": email})
        except APIError:
            pass
    st.session_state["password_reset_requested"] = True
    st.success("If the email is registered, a password-reset link has been sent.")


def _reset_password(client: APIClient, token: str, password: str, account_domain: str) -> bool:
    path = "/auth/reset-password" if account_domain == "staff" else "/customer/auth/reset-password"
    try:
        client.post(path, {"reset_token": token, "new_password": password})
        return True
    except APIError:
        return False


def _return_to_login() -> None:
    st.query_params.clear()
    st.session_state["public_store_view"] = "auth"
    st.session_state.pop("password_reset_requested", None)
    st.session_state.pop("password_reset_complete", None)
    _change_view("login")


def render_recovery(client: APIClient) -> None:
    card = auth_card_header("Forgot your password?", "Enter your email and we’ll send you a secure reset link.")
    with card:
        if st.session_state.get("password_reset_requested"):
            st.success("Check your email for a password-reset link.")
            st.caption("If an account matches that address, the email will arrive shortly. The link expires after a limited time.")
        email = st.text_input("Account email", key="unified_recovery_email")
        if st.button("Reset Password", key="unified_request_reset", type="primary", use_container_width=True):
            if not _looks_like_email(email):
                st.error("Enter a valid email address.")
            else:
                _request_reset(client, email.strip())
                st.rerun()
        st.button("Back to sign in", key="unified_recovery_back", on_click=_return_to_login)


def render_reset_password(client: APIClient, token: str, account_domain: str) -> None:
    card = auth_card_header("Choose a new password", "Create a strong password for your RetailMetrics account.")
    with card:
        if st.session_state.get("password_reset_complete"):
            st.success("Password reset successfully. You can now sign in.")
            st.button("Continue to sign in", type="primary", use_container_width=True, on_click=_return_to_login)
            return
        st.info("This secure link is time-limited and can be used only once.")
        password = st.text_input(
            "New password",
            type="password",
            key="unified_reset_password",
            help="At least 12 characters with uppercase, lowercase, number, and symbol.",
        )
        confirmation = st.text_input(
            "Confirm new password", type="password", key="unified_reset_confirmation"
        )
        if st.button("Reset password", key="unified_reset_submit", type="primary", use_container_width=True):
            if password != confirmation:
                st.error("Passwords do not match.")
            elif _reset_password(client, token, password, account_domain):
                st.session_state["password_reset_complete"] = True
                st.rerun()
            else:
                st.error("This reset link is invalid or has expired. Request a new link and try again.")
        st.button("Back to sign in", key="unified_reset_back", on_click=_return_to_login)


def render_registration(client: APIClient) -> None:
    showcase, registration = st.columns([1, 1.12], gap="large")
    with showcase:
        _render_auth_showcase()
    with registration:
        render_customer_register(client)
        st.button(
            "Back to sign in",
            key="unified_registration_back",
            on_click=_change_view,
            args=("login",),
            use_container_width=True,
        )


def _render_auth_showcase() -> None:
    st.markdown(
        """
        <section class="rm-auth-showcase">
          <div class="rm-auth-showcase-mark">RM</div>
          <div class="rm-shop-kicker">Welcome to RetailMetrics</div>
          <h2>A little play.<br>A world of possibility.</h2>
          <p>
            Discover something to smile about. Shop your favorites, keep track of orders,
            and make room for your next adventure.
          </p>
          <ul class="rm-auth-showcase-list">
            <li><strong>Find a favorite</strong>Browse our available toy collection.</li>
            <li><strong>Make it yours</strong>Save your cart and delivery details.</li>
            <li><strong>Follow the joy</strong>Track purchases from order to delivery.</li>
          </ul>
          <div class="rm-auth-staff-note">On the store team? Sign in with your staff account to open your workspace.</div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render(client: APIClient) -> None:
    reset_token = st.query_params.get("reset_token")
    if reset_token:
        account_domain = st.query_params.get("account", "customer")
        render_reset_password(client, str(reset_token), "staff" if account_domain == "staff" else "customer")
        return
    view = st.session_state.get(VIEW_KEY, "login")
    if view == "register":
        render_registration(client)
    elif view == "recovery":
        render_recovery(client)
    else:
        showcase, sign_in = st.columns([1.05, 1], gap="large")
        with showcase:
            _render_auth_showcase()
        with sign_in:
            render_login(client)
