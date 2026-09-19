from __future__ import annotations

import secrets
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from frontend.browser_session import BrowserSessionStore


CUSTOMER_COOKIE_NAME = "retailmetrics_customer_browser_session"
CUSTOMER_COOKIE_COMMAND_KEY = "_customer_browser_cookie_command"
COOKIE_COMPONENT_PATH = Path(__file__).resolve().parent / "components" / "session_cookie"
_customer_cookie_component = components.declare_component(
    "retailmetrics_customer_session_cookie",
    path=str(COOKIE_COMPONENT_PATH),
)


@st.cache_resource(show_spinner=False)
def customer_browser_session_store() -> BrowserSessionStore:
    return BrowserSessionStore()


def _cookie_handle() -> str | None:
    try:
        value = st.context.cookies.get(CUSTOMER_COOKIE_NAME)
        return value if isinstance(value, str) and value else None
    except (AttributeError, KeyError, RuntimeError):
        return None


def restore_customer_browser_session() -> None:
    if st.session_state.get("customer_access_token") or st.session_state.get("_ignore_customer_browser_cookie"):
        return
    handle = _cookie_handle()
    if not handle:
        return
    token = customer_browser_session_store().resolve(handle)
    if token:
        st.session_state.customer_access_token = token
        st.session_state.customer_browser_session_handle = handle
        return
    request_customer_cookie_delete()


def persist_customer_browser_session(access_token: str, expires_in: int) -> None:
    previous = st.session_state.get("customer_browser_session_handle")
    customer_browser_session_store().revoke(previous)
    handle = customer_browser_session_store().issue(access_token, expires_in)
    st.session_state.customer_browser_session_handle = handle
    st.session_state._ignore_customer_browser_cookie = False
    st.session_state[CUSTOMER_COOKIE_COMMAND_KEY] = {
        "action": "set", "value": handle, "command_id": secrets.token_urlsafe(12)
    }


def request_customer_cookie_delete() -> None:
    handle = st.session_state.get("customer_browser_session_handle") or _cookie_handle()
    customer_browser_session_store().revoke(handle)
    st.session_state.customer_browser_session_handle = None
    st.session_state._ignore_customer_browser_cookie = True
    st.session_state[CUSTOMER_COOKIE_COMMAND_KEY] = {
        "action": "delete", "value": "", "command_id": secrets.token_urlsafe(12)
    }


def sync_customer_browser_cookie() -> None:
    command = st.session_state.get(CUSTOMER_COOKIE_COMMAND_KEY)
    if not command:
        return
    try:
        secure = str(st.context.url).lower().startswith("https://")
    except (AttributeError, RuntimeError):
        secure = False
    result = _customer_cookie_component(
        cookie_name=CUSTOMER_COOKIE_NAME,
        secure=secure,
        key="retailmetrics_customer_session_cookie_sync",
        **command,
    )
    if result == command["command_id"]:
        st.session_state.pop(CUSTOMER_COOKIE_COMMAND_KEY, None)
