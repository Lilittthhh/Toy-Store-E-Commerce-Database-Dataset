from __future__ import annotations

import streamlit as st

from frontend.api_client import APIClient, APIError
from frontend.ui import data_page_header, format_datetime, pagination_controls, show_api_error


def render(client: APIClient) -> None:
    data_page_header("Customer Accounts", "Review safe customer details and manage account access.", "customers")
    filters = st.columns([2, 1, 1])
    search = filters[0].text_input("Search email or name")
    status = filters[1].selectbox("Status", ["all", "active", "inactive"])
    limit = filters[2].selectbox("Rows", [10, 25, 50, 100], index=1, key="customer_rows")
    params = {"limit": limit, "offset": st.session_state.setdefault("customers_offset", 0)}
    if search:
        params["search"] = search
    if status != "all":
        params["is_active"] = status == "active"
    try:
        result = client.get("/admin/customers", params)
        rows = result["items"]
        table = [{
            "Customer": f"{row['first_name']} {row['last_name']}",
            "Email": row["email"],
            "Status": "Active" if row["is_active"] else "Inactive",
            "Lock status": f"Locked until {format_datetime(row['locked_until'])}" if row.get("locked_until") else "Unlocked",
            "Last login": format_datetime(row.get("last_login_at")),
        } for row in rows]
        if table:
            st.dataframe(table, use_container_width=True, hide_index=True, height=max(170, min(440, 38 + len(table) * 34)))
        else:
            st.info("No customer accounts match the current filters.")
        pagination_controls("customers", result["total"], limit)
        if not rows:
            return
        st.divider()
        selected_id = st.selectbox("Customer account", [row["customer_account_id"] for row in rows], format_func=lambda value: next(f"{row['first_name']} {row['last_name']} · {row['email']}" for row in rows if row["customer_account_id"] == value))
        selected = next(row for row in rows if row["customer_account_id"] == selected_id)
        left, right = st.columns(2)
        action = "Deactivate" if selected["is_active"] else "Reactivate"
        if left.button(action, type="primary", use_container_width=True):
            try:
                client.put(f"/admin/customers/{selected_id}/status", {"is_active": not selected["is_active"], "row_version": selected["account_row_version"]})
                st.success(f"Customer account {action.lower()}d.")
                st.rerun()
            except APIError as exc:
                show_api_error(exc)
        if right.button("Unlock account", disabled=not bool(selected.get("locked_until")), use_container_width=True):
            try:
                client.post(f"/admin/customers/{selected_id}/unlock", {"row_version": selected["account_row_version"]})
                st.success("Customer account unlocked.")
                st.rerun()
            except APIError as exc:
                show_api_error(exc)
        st.caption("Customer accounts are retained for account history. Access changes take effect immediately.")
    except APIError as exc:
        show_api_error(exc)
