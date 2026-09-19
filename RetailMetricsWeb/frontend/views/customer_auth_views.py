from __future__ import annotations

import streamlit as st

from frontend.api_client import APIClient, APIError
from frontend.customer_auth import customer_sign_in
from frontend.ui import auth_card_header, section_label, show_api_error


def _header(title: str, caption: str):
    return auth_card_header(title, caption, "Customer Portal")


def render_login(client: APIClient) -> None:
    content = _header("Welcome to RetailMetrics", "Sign in to continue")
    with content:
        section_label("Customer access")
        with st.form("customer_login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)
        if submitted:
            try:
                token = client.post("/customer/auth/login", {"email": email, "password": password})
                authenticated = APIClient(token=token["access_token"])
                customer = authenticated.get("/customer/auth/me")
                customer_sign_in(token["access_token"], customer, token["expires_in"])
                st.rerun()
            except APIError as exc:
                show_api_error(exc)


def render_register(client: APIClient) -> None:
    content = _header("Create your customer account", "Secure access to the RetailMetrics storefront and customer services")
    with content:
        st.info("Create your profile, then sign in to browse the storefront, manage saved resources, and check out securely.")
        with st.form("customer_register_form"):
            first_name = st.text_input("First name")
            last_name = st.text_input("Last name")
            phone = st.text_input("Phone (optional)")
            email = st.text_input("Email")
            password = st.text_input("Password", type="password", help="At least 12 characters with uppercase, lowercase, number, and symbol.")
            confirmation = st.text_input("Confirm password", type="password")
            submitted = st.form_submit_button("Create customer account", type="primary", use_container_width=True)
        if submitted:
            if password != confirmation:
                st.error("Passwords do not match.")
                return
            try:
                client.post("/customer/auth/register", {
                    "email": email, "password": password, "first_name": first_name,
                    "last_name": last_name, "phone": phone or None,
                })
                st.success("Customer account created. You can now sign in.")
            except APIError as exc:
                show_api_error(exc)


def render_password_recovery(client: APIClient) -> None:
    content = _header("Customer password recovery", "Request a time-limited token and choose a new password")
    with content:
        request_tab, reset_tab = st.tabs(["Request reset", "Reset password"])
        with request_tab:
            with st.form("customer_forgot_form"):
                email = st.text_input("Customer email")
                submitted = st.form_submit_button("Request reset token", use_container_width=True)
            if submitted:
                try:
                    result = client.post("/customer/auth/forgot-password", {"email": email})
                    st.success(result["message"])
                    if result.get("reset_token"):
                        st.warning("Development-only reset code (mock mode) — do not share it.")
                        st.code(result["reset_token"])
                except APIError as exc:
                    show_api_error(exc)
        with reset_tab:
            with st.form("customer_reset_form"):
                token = st.text_input("Reset token")
                password = st.text_input("New password", type="password")
                confirmation = st.text_input("Confirm new password", type="password")
                submitted = st.form_submit_button("Reset password", type="primary", use_container_width=True)
            if submitted:
                if password != confirmation:
                    st.error("Passwords do not match.")
                    return
                try:
                    result = client.post("/customer/auth/reset-password", {"reset_token": token, "new_password": password})
                    st.success(result["message"])
                except APIError as exc:
                    show_api_error(exc)
