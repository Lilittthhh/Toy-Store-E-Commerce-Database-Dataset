from __future__ import annotations

import hashlib
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components


COOKIE_NAME = "retailmetrics_browser_session"
COOKIE_COMMAND_KEY = "_browser_cookie_command"
COOKIE_COMPONENT_PATH = Path(__file__).resolve().parent / "components" / "session_cookie"
_cookie_component = components.declare_component(
    "retailmetrics_session_cookie",
    path=str(COOKIE_COMPONENT_PATH),
)


@dataclass(frozen=True)
class _StoredSession:
    access_token: str
    expires_at: float


class BrowserSessionStore:
    """Process-local token storage keyed by an unguessable browser handle."""

    def __init__(self) -> None:
        self._sessions: dict[str, _StoredSession] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(handle: str) -> str:
        return hashlib.sha256(handle.encode("utf-8")).hexdigest()

    def issue(self, access_token: str, expires_in: int) -> str:
        handle = secrets.token_urlsafe(32)
        now = time.time()
        with self._lock:
            self._remove_expired(now)
            self._sessions[self._key(handle)] = _StoredSession(
                access_token=access_token,
                expires_at=now + max(1, int(expires_in)),
            )
        return handle

    def resolve(self, handle: str | None) -> str | None:
        if not handle:
            return None
        now = time.time()
        with self._lock:
            self._remove_expired(now)
            session = self._sessions.get(self._key(handle))
            return session.access_token if session else None

    def revoke(self, handle: str | None) -> None:
        if not handle:
            return
        with self._lock:
            self._sessions.pop(self._key(handle), None)

    def _remove_expired(self, now: float) -> None:
        expired = [key for key, value in self._sessions.items() if value.expires_at <= now]
        for key in expired:
            self._sessions.pop(key, None)


@st.cache_resource(show_spinner=False)
def browser_session_store() -> BrowserSessionStore:
    return BrowserSessionStore()


def _cookie_handle() -> str | None:
    try:
        value = st.context.cookies.get(COOKIE_NAME)
        return value if isinstance(value, str) and value else None
    except (AttributeError, KeyError, RuntimeError):
        return None


def restore_browser_session() -> None:
    """Restore a server-held JWT from the opaque handle supplied by the browser."""
    if st.session_state.get("access_token") or st.session_state.get("_ignore_browser_cookie"):
        return
    handle = _cookie_handle()
    if not handle:
        return
    token = browser_session_store().resolve(handle)
    if token:
        st.session_state.access_token = token
        st.session_state.browser_session_handle = handle
        return
    request_cookie_delete()


def persist_browser_session(access_token: str, expires_in: int) -> None:
    previous = st.session_state.get("browser_session_handle")
    browser_session_store().revoke(previous)
    handle = browser_session_store().issue(access_token, expires_in)
    st.session_state.browser_session_handle = handle
    st.session_state._ignore_browser_cookie = False
    st.session_state[COOKIE_COMMAND_KEY] = {
        "action": "set",
        "value": handle,
        "command_id": secrets.token_urlsafe(12),
    }


def request_cookie_delete() -> None:
    handle = st.session_state.get("browser_session_handle") or _cookie_handle()
    browser_session_store().revoke(handle)
    st.session_state.browser_session_handle = None
    # st.context.cookies is a snapshot from the initial browser connection. Ignore
    # that snapshot after logout until the next full page load observes deletion.
    st.session_state._ignore_browser_cookie = True
    st.session_state[COOKIE_COMMAND_KEY] = {
        "action": "delete",
        "value": "",
        "command_id": secrets.token_urlsafe(12),
    }


def sync_browser_cookie() -> None:
    """Apply a pending set/delete operation through a zero-height component."""
    command = st.session_state.get(COOKIE_COMMAND_KEY)
    if not command:
        return
    try:
        secure = str(st.context.url).lower().startswith("https://")
    except (AttributeError, RuntimeError):
        secure = False
    result = _cookie_component(
        cookie_name=COOKIE_NAME,
        secure=secure,
        key="retailmetrics_session_cookie_sync",
        **command,
    )
    if result == command["command_id"]:
        st.session_state.pop(COOKIE_COMMAND_KEY, None)
