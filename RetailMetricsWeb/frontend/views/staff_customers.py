from __future__ import annotations

import streamlit as st

from frontend.api_client import APIClient, APIError
from frontend.auth import current_role
from frontend.ui import data_page_header, display_rows, format_datetime, format_money, pagination_controls, show_api_error


def _money(value) -> str:
    return format_money(value)


def _render_registered_customers(client: APIClient, role: str) -> None:
    st.subheader("Registered customers")
    if role == "operations_staff":
        st.caption("Customer contact and purchase summaries for daily support.")
    elif role == "analyst":
        st.caption("Registered-customer activity is deidentified for analysis.")
    else:
        st.caption("Current customer accounts and their store activity.")

    limit = st.selectbox("Registered rows per page", [10, 25, 50, 100], index=1, key="registered_customers_limit")
    offset = st.session_state.setdefault("registered_customers_offset", 0)
    try:
        result = client.get("/staff/customers/registered", {"limit": limit, "offset": offset})
        if role == "analyst":
            rows = [{
                "Customer": f"Customer #{row['customer_account_id']}",
                "Orders": row["order_count"],
                "Total spent": _money(row["total_spent"]),
                "Account since": format_datetime(row["created_at"]),
            } for row in result["items"]]
        elif role == "operations_staff":
            rows = [{
                "Customer": row["customer_label"],
                "Email": row["email"],
                "Orders": row["order_count"],
                "Total spent": _money(row["total_spent"]),
                "Account status": "Active" if row["is_active"] else "Inactive",
            } for row in result["items"]]
        else:
            rows = [{
                "Customer": row["customer_label"],
                "Email": row["email"],
                "Orders": row["order_count"],
                "Total spent": _money(row["total_spent"]),
                "Account since": format_datetime(row["created_at"]),
                "Status": "Active" if row["is_active"] else "Inactive",
            } for row in result["items"]]
        display_rows(rows, "Customer")
        pagination_controls("registered_customers", result["total"], limit)
        if not result["items"]:
            st.info("No registered customer accounts are available.")
        elif role == "admin":
            st.info("Account activation, lockout recovery, and full safe profile review remain under Customer Accounts.")
    except APIError as exc:
        show_api_error(exc)


def _render_earlier_customer_activity(client: APIClient, role: str) -> None:
    analyst_or_operations = role in {"analyst", "operations_staff"}
    st.subheader("Earlier customer activity")
    st.caption("These customer purchase records come from the earlier dataset and remain part of the same customer view.")
    search = st.text_input(
        "Find earlier customer",
        placeholder="Customer number",
        key="historical_customer_search",
    )
    limit = st.selectbox("Earlier activity rows per page", [10, 25, 50, 100], index=1, key="historical_customers_limit")
    offset = st.session_state.setdefault("historical_customers_offset", 0)
    try:
        result = client.get(
            "/staff/customers/historical",
            {"search": search or None, "limit": limit, "offset": offset},
        )
        rows = [{
            "Customer": f"Customer #{row['dataset_user_id']}",
            "Orders": row["order_count"],
            "Total spent": _money(row["total_spent"]),
            "Refunds": _money(row["refund_total"]),
            "Last activity": format_datetime(row["last_visit"]),
        } for row in result["items"]]
        display_rows(rows, "Customer")
        pagination_controls("historical_customers", result["total"], limit)
        if result["items"]:
            selected = st.selectbox(
                "Customer detail",
                [row["dataset_user_id"] for row in result["items"]],
                format_func=lambda value: f"Customer #{value}",
            )
            detail_button = "View activity" if analyst_or_operations else "Open customer profile"
            if st.button(detail_button, use_container_width=True):
                st.session_state.historical_customer_detail = selected
            detail_id = st.session_state.get("historical_customer_detail")
            if detail_id:
                detail = client.get(f"/staff/customers/historical/{detail_id}")
                st.subheader(f"Customer #{detail_id}")
                metrics = (
                    ("Sessions", detail["session_count"]),
                    ("Orders", detail["order_count"]),
                    ("Total Spent", _money(detail["total_spent"])),
                    ("Refunds", _money(detail["refund_total"])),
                )
                for column, pair in zip(st.columns(4), metrics):
                    column.metric(*pair)
                st.markdown("#### Recent Orders")
                display_rows(detail["recent_orders"], "order_id")
                st.markdown("#### Recent Sessions")
                display_rows(detail["recent_sessions"], "session_id")
                st.markdown("#### Product Purchases")
                display_rows(detail["product_purchases"], "product_id")
        elif search:
            st.info("No earlier customer matches that customer number.")
    except APIError as exc:
        show_api_error(exc)


def render(client: APIClient) -> None:
    role = current_role()
    data_page_header(
        "Customers",
        "Review current registered customers first, with earlier customer activity available below when needed.",
        "staff_customers",
    )
    _render_registered_customers(client, role)
    st.divider()
    with st.expander("Earlier customer activity", expanded=False):
        _render_earlier_customer_activity(client, role)
