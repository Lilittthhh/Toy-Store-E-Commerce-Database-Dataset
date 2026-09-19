from __future__ import annotations

from typing import Any

import streamlit as st

from frontend.browser_session import (
    persist_browser_session,
    request_cookie_delete,
    restore_browser_session,
)


def initialize_session() -> None:
    st.session_state.setdefault("access_token", None)
    st.session_state.setdefault("current_user", None)
    st.session_state.setdefault("browser_session_handle", None)
    st.session_state.setdefault("_ignore_browser_cookie", False)
    restore_browser_session()


def sign_in(token: str, user: dict[str, Any], expires_in: int = 1800) -> None:
    st.session_state.access_token = token
    st.session_state.current_user = user
    st.session_state.active_portal = "staff"
    persist_browser_session(token, expires_in)


def sign_out() -> None:
    request_cookie_delete()
    st.session_state.access_token = None
    st.session_state.current_user = None
    st.session_state.active_portal = None


def current_role() -> str | None:
    user = st.session_state.get("current_user")
    return user.get("role") if user else None


def can_mutate(entity: str, role: str | None) -> bool:
    # Final staff UI: only product master records use generic entity CRUD.
    # Customer transactions are changed through checkout/order/refund workflows.
    return role == "admin" and entity == "products"


def can_manage_users(role: str | None) -> bool:
    return role == "admin"
