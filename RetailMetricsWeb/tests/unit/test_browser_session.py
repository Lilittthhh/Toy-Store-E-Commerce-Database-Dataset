from pathlib import Path

import frontend.browser_session as browser_session
from frontend.browser_session import BrowserSessionStore, COOKIE_NAME


def test_opaque_handle_restores_and_revokes_server_held_token() -> None:
    store = BrowserSessionStore()
    raw_token = "signed.jwt.value"

    handle = store.issue(raw_token, expires_in=60)

    assert handle != raw_token
    assert raw_token not in handle
    assert len(handle) >= 40
    assert store.resolve(handle) == raw_token

    store.revoke(handle)
    assert store.resolve(handle) is None


def test_expired_browser_session_is_not_restored(monkeypatch) -> None:
    clock = {"now": 1000.0}
    monkeypatch.setattr("frontend.browser_session.time.time", lambda: clock["now"])
    store = BrowserSessionStore()
    handle = store.issue("short-lived-token", expires_in=5)

    clock["now"] = 1006.0

    assert store.resolve(handle) is None


def test_cookie_component_never_receives_the_raw_access_token() -> None:
    component = (
        Path(__file__).resolve().parents[2]
        / "frontend"
        / "components"
        / "session_cookie"
        / "index.html"
    ).read_text(encoding="utf-8")

    assert COOKIE_NAME not in component
    assert "access_token" not in component
    assert "SameSite=Strict" in component


def test_new_streamlit_session_restores_token_from_cookie_handle(monkeypatch) -> None:
    class State(dict):
        __getattr__ = dict.get
        __setattr__ = dict.__setitem__

    store = BrowserSessionStore()
    handle = store.issue("restored.jwt", expires_in=60)
    state = State(access_token=None, browser_session_handle=None)
    monkeypatch.setattr(browser_session.st, "session_state", state)
    monkeypatch.setattr(browser_session, "_cookie_handle", lambda: handle)
    monkeypatch.setattr(browser_session, "browser_session_store", lambda: store)

    browser_session.restore_browser_session()

    assert state.access_token == "restored.jwt"
    assert state.browser_session_handle == handle
