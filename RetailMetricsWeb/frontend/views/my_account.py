from __future__ import annotations

import streamlit as st

from frontend.api_client import APIClient, APIError
from frontend.auth import sign_out
from frontend.ui import format_datetime, page_header, section_label, show_api_error


def render(client: APIClient, user: dict) -> None:
    page_header("My Account", "Review your profile and maintain your account security.")
    section_label("Account summary")
    first, second, third = st.columns(3)
    first.metric("Username", user["username"])
    second.metric("Role", user["role"].replace("_", " ").title())
    third.metric("Status", "Active" if user["is_active"] else "Inactive")
    with st.container(border=True):
        detail_one, detail_two = st.columns(2)
        detail_one.markdown(f"**Email address**  \n{user['email']}")
        detail_two.markdown(
            f"**Last login**  \n{format_datetime(user.get('last_login_at')) if user.get('last_login_at') else 'First session'}"
        )

    st.divider()
    section_label("Security")
    st.subheader("Change password")
    st.caption("Changing your password signs out all active sessions for this account.")
    form_column, _ = st.columns([1.6, 1])
    with form_column:
        with st.form("change_password"):
            current = st.text_input("Current password", type="password")
            new = st.text_input("New password", type="password")
            confirm = st.text_input("Confirm new password", type="password")
            submitted = st.form_submit_button("Change password", type="primary", use_container_width=True)
    if submitted:
        if new != confirm:
            st.error("New passwords do not match.")
            return
        try:
            result = client.post("/auth/change-password", {"current_password": current, "new_password": new})
            st.success(result["message"] + " Please sign in again.")
            sign_out()
            st.rerun()
        except APIError as exc:
            show_api_error(exc)
