from __future__ import annotations

import streamlit as st

from frontend.api_client import APIClient, APIError
from frontend.auth import sign_in
from frontend.ui import auth_card_header, section_label, show_api_error


def _centered_header(title: str, caption: str):
    return auth_card_header(title, caption, "Staff Portal")


def render_login(client: APIClient) -> None:
    content = _centered_header(
        "Welcome to RetailMetrics",
        "Sign in to continue",
    )
    with content:
        section_label("Account access")
        with st.form("login_form"):
            identifier = st.text_input("Username or email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button(
                "Sign in",
                type="primary",
                use_container_width=True,
            )
        if submitted:
            try:
                token = client.post(
                    "/auth/login",
                    {"identifier": identifier, "password": password},
                )
                authenticated = APIClient(token=token["access_token"])
                user = authenticated.get("/auth/me")
                sign_in(token["access_token"], user, token["expires_in"])
                st.rerun()
            except APIError as exc:
                show_api_error(exc)


def render_register(client: APIClient) -> None:
    content = _centered_header(
        "Create an Analyst account",
        "Start with secure, read-only access",
    )
    with content:
        st.info(
            "Public registration creates Analyst accounts. "
            "Elevated roles are assigned by an Admin."
        )
        section_label("Create your account")
        with st.form("register_form"):
            username = st.text_input("Username")
            email = st.text_input("Email")
            password = st.text_input(
                "Password",
                type="password",
                help=(
                    "At least 12 characters with uppercase, lowercase, "
                    "number, and symbol."
                ),
            )
            confirmation = st.text_input("Confirm password", type="password")
            submitted = st.form_submit_button(
                "Register",
                type="primary",
                use_container_width=True,
            )
        if submitted:
            if password != confirmation:
                st.error("Passwords do not match.")
                return
            try:
                client.post(
                    "/auth/register",
                    {"username": username, "email": email, "password": password},
                )
                st.success("Analyst account created. You can now sign in.")
            except APIError as exc:
                show_api_error(exc)


def render_password_recovery(client: APIClient) -> None:
    content = _centered_header(
        "Password recovery",
        "Request a token, then choose a new password",
    )
    with content:
        st.info("Reset tokens are time-limited. Completing a reset invalidates existing sessions.")
        forgot_tab, reset_tab = st.tabs(["Request reset", "Reset password"])
        with forgot_tab:
            section_label("Request a secure token")
            with st.form("forgot_form"):
                email = st.text_input("Account email")
                submitted = st.form_submit_button(
                    "Request reset token",
                    use_container_width=True,
                )
            if submitted:
                try:
                    result = client.post("/auth/forgot-password", {"email": email})
                    st.success(result["message"])
                    if result.get("reset_token"):
                        st.warning(
                            "Development-only reset code (mock mode) — do not share it."
                        )
                        st.code(result["reset_token"])
                except APIError as exc:
                    show_api_error(exc)
        with reset_tab:
            section_label("Choose a new password")
            with st.form("reset_form"):
                token = st.text_input("Reset token")
                password = st.text_input("New password", type="password")
                confirmation = st.text_input(
                    "Confirm new password",
                    type="password",
                )
                submitted = st.form_submit_button(
                    "Reset password",
                    type="primary",
                    use_container_width=True,
                )
            if submitted:
                if password != confirmation:
                    st.error("Passwords do not match.")
                    return
                try:
                    result = client.post(
                        "/auth/reset-password",
                        {"reset_token": token, "new_password": password},
                    )
                    st.success(result["message"])
                except APIError as exc:
                    show_api_error(exc)
