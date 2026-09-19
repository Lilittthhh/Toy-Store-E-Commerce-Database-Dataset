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
        customer = APIClient(token=token["access_token"]).get("/customer/auth/me")
        customer_sign_in(token["access_token"], customer, token["expires_in"])
        return True
    except APIError:
        return False


def render_login(client: APIClient) -> None:
    card = auth_card_header("Welcome back", "Sign in to continue to your account.")
    with card:
        identifier = st.text_input("Email or username", key="unified_login_identifier")
        show_password = bool(st.session_state.get("unified_login_show_password", False))
        password = st.text_input(
            "Password",
            type="default" if show_password else "password",
            key="unified_login_password",
        )
        st.checkbox("Show password", key="unified_login_show_password")
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
    tokens: list[str] = []
    for path in ("/auth/forgot-password", "/customer/auth/forgot-password"):
        try:
            result = client.post(path, {"email": email})
            if result.get("reset_token"):
                tokens.append(result["reset_token"])
        except APIError:
            pass
    st.success("If the email is registered, password-reset instructions have been sent.")
    for index, token in enumerate(dict.fromkeys(tokens), start=1):
        st.warning("Development-only reset code (mock mode) — do not share it.")
        st.code(token, language=None)


def _reset_password(client: APIClient, token: str, password: str) -> bool:
    for path in ("/auth/reset-password", "/customer/auth/reset-password"):
        try:
            client.post(path, {"reset_token": token, "new_password": password})
            return True
        except APIError:
            continue
    return False


def render_recovery(client: APIClient) -> None:
    card = auth_card_header("Password recovery", "Request a reset code or choose a new password.")
    with card:
        request_tab, reset_tab = st.tabs(["Request reset", "Reset password"])
        with request_tab:
            email = st.text_input("Account email", key="unified_recovery_email")
            if st.button("Request reset", key="unified_request_reset", use_container_width=True):
                _request_reset(client, email.strip())
        with reset_tab:
            token = st.text_input("Reset code", key="unified_reset_code")
            password = st.text_input("New password", type="password", key="unified_reset_password")
            confirmation = st.text_input(
                "Confirm new password", type="password", key="unified_reset_confirmation"
            )
            if st.button(
                "Reset password", key="unified_reset_submit", type="primary", use_container_width=True
            ):
                if password != confirmation:
                    st.error("Passwords do not match.")
                elif _reset_password(client, token, password):
                    st.success("Password reset successfully. You can now sign in.")
                else:
                    st.error("The reset code is invalid or expired.")
        st.button("Back to sign in", key="unified_recovery_back", on_click=_change_view, args=("login",))


def render_registration(client: APIClient) -> None:
    render_customer_register(client)
    _, content, _ = st.columns([1, 1.55, 1])
    content.button("Back to sign in", key="unified_registration_back", on_click=_change_view, args=("login",))


def render(client: APIClient) -> None:
    view = st.session_state.get(VIEW_KEY, "login")
    if view == "register":
        render_registration(client)
    elif view == "recovery":
        render_recovery(client)
    else:
        render_login(client)
