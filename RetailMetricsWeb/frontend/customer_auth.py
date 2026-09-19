from __future__ import annotations

from typing import Any

import streamlit as st

from frontend.customer_browser_session import (
    persist_customer_browser_session,
    request_customer_cookie_delete,
    restore_customer_browser_session,
)


def initialize_customer_session() -> None:
    st.session_state.setdefault("customer_access_token", None)
    st.session_state.setdefault("current_customer", None)
    st.session_state.setdefault("customer_browser_session_handle", None)
    st.session_state.setdefault("_ignore_customer_browser_cookie", False)
    st.session_state.setdefault("active_portal", None)
    restore_customer_browser_session()


def customer_sign_in(token: str, customer: dict[str, Any], expires_in: int = 1800) -> None:
    st.session_state.customer_access_token = token
    st.session_state.current_customer = customer
    st.session_state.active_portal = "customer"
    persist_customer_browser_session(token, expires_in)


def customer_sign_out() -> None:
    request_customer_cookie_delete()
    st.session_state.customer_access_token = None
    st.session_state.current_customer = None
    st.session_state.active_portal = None
