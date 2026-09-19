from __future__ import annotations

import streamlit as st

from frontend.api_client import APIClient, APIError
from frontend.ui import data_page_header, format_datetime, pagination_controls, section_label, show_api_error


ROLE_LABELS = {
    "admin": "Admin",
    "operations_staff": "Operations Staff",
    "analyst": "Analyst",
}


def render(client: APIClient, current_user: dict) -> None:
    data_page_header(
        "User Management",
        "Create accounts and manage access without physically deleting users.",
        "users",
    )
    section_label("Directory filters")
    with st.container(border=True):
        filters = st.columns([2, 1, 1, 1])
        search = filters[0].text_input("Search username or email")
        role = filters[1].selectbox("Role", ["all", *ROLE_LABELS], format_func=lambda value: "All roles" if value == "all" else ROLE_LABELS[value])
        status = filters[2].selectbox("Status", ["all", "active", "inactive"])
        limit = filters[3].selectbox("Rows", [10, 25, 50, 100], index=1)
    offset = st.session_state.setdefault("users_offset", 0)
    params = {"limit": limit, "offset": offset}
    if search:
        params["search"] = search
    if role != "all":
        params["role"] = role
    if status != "all":
        params["is_active"] = status == "active"
    try:
        result = client.get("/admin/users", params)
        rows = result["items"]
        if rows:
            table = [
                {
                    "Username": row["username"],
                    "Role": ROLE_LABELS[row["role"]],
                    "Status": "Active" if row["is_active"] else "Inactive",
                    "Email": row["email"],
                    "Last login": format_datetime(row["last_login_at"]),
                }
                for row in rows
            ]
            st.dataframe(
                table,
                use_container_width=True,
                hide_index=True,
                height=max(170, min(440, 38 + len(table) * 34)),
                column_config={
                    "Username": st.column_config.TextColumn("Username", width="medium"),
                    "Email": st.column_config.TextColumn("Email", width="large"),
                    "Role": st.column_config.TextColumn("Role", width="medium"),
                },
            )
        else:
            st.info("No users match the current filters.")
        pagination_controls("users", result["total"], limit)

        st.divider()
        section_label("Account controls")
        create_tab, manage_tab = st.tabs(["Create user", "Manage user"])
        with create_tab:
            st.subheader("Create application user")
            st.caption("Assign the initial role now; access can be changed later without deleting the account.")
            with st.form("admin_create_user"):
                username = st.text_input("Username")
                email = st.text_input("Email")
                password = st.text_input("Temporary password", type="password")
                selected_role = st.selectbox("Role", list(ROLE_LABELS), format_func=ROLE_LABELS.get)
                submitted = st.form_submit_button("Create user", type="primary", use_container_width=True)
            if submitted:
                try:
                    client.post("/admin/users", {"username": username, "email": email, "password": password, "role": selected_role})
                    st.success("User created.")
                    st.rerun()
                except APIError as exc:
                    show_api_error(exc)
        with manage_tab:
            st.subheader("Manage account access")
            if not rows:
                return
            selected_id = st.selectbox("User", [row["app_user_id"] for row in rows], format_func=lambda value: next(f"{row['username']} · {ROLE_LABELS[row['role']]}" for row in rows if row["app_user_id"] == value))
            selected = next(row for row in rows if row["app_user_id"] == selected_id)
            lock_text = format_datetime(selected["locked_until"]) if selected["locked_until"] else "Not locked"
            st.caption(f"Current status: {'Active' if selected['is_active'] else 'Inactive'} · Lock status: {lock_text}")

            with st.container(border=True):
                new_role = st.selectbox("New role", list(ROLE_LABELS), index=list(ROLE_LABELS).index(selected["role"]), format_func=ROLE_LABELS.get, key="manage_role")
                role_action, status_action = st.columns(2)
                change_role = role_action.button(
                    "Change role",
                    disabled=selected_id == current_user["app_user_id"],
                    use_container_width=True,
                )
                status_label = "Deactivate" if selected["is_active"] else "Activate"
                change_status = status_action.button(
                    status_label,
                    disabled=selected_id == current_user["app_user_id"] and selected["is_active"],
                    use_container_width=True,
                )
            if change_role:
                try:
                    client.put(f"/admin/users/{selected_id}/role", {"role": new_role, "row_version": selected["row_version"]})
                    st.success("Role updated.")
                    st.rerun()
                except APIError as exc:
                    show_api_error(exc)

            if change_status:
                try:
                    client.put(f"/admin/users/{selected_id}/status", {"is_active": not selected["is_active"], "row_version": selected["row_version"]})
                    st.success(f"User {status_label.lower()}d.")
                    st.rerun()
                except APIError as exc:
                    show_api_error(exc)

            if selected["locked_until"]:
                unlock_column, _ = st.columns([1, 2])
                if unlock_column.button("Unlock account", use_container_width=True):
                    try:
                        client.post(f"/admin/users/{selected_id}/unlock", {"row_version": selected["row_version"]})
                        st.success("Account unlocked.")
                        st.rerun()
                    except APIError as exc:
                        show_api_error(exc)
            st.caption("Staff accounts are retained for accountability and can be deactivated when access is no longer needed.")
    except APIError as exc:
        show_api_error(exc)
