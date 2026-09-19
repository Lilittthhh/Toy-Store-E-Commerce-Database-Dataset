from __future__ import annotations

import streamlit as st

from frontend.api_client import APIClient, APIError
from frontend.auth import current_role
from frontend.ui import data_page_header, display_rows, format_datetime, format_money, pagination_controls, show_api_error


def _money(value) -> str:
    return format_money(value)


def render(client: APIClient) -> None:
    role = current_role()
    caption = (
        "Review registered customers and the purchase context needed for daily support."
        if role == "operations_staff"
        else (
            "Compare deidentified historical shoppers with registered-customer activity."
            if role == "analyst"
            else "Historical shopper intelligence and registered customer activity remain clearly separated."
        )
    )
    data_page_header("Customers", caption, "staff_customers")
    if role == "operations_staff":
        registered, historical = st.tabs(["Registered Customers", "Historical Reference"])
    elif role == "analyst":
        historical, registered = st.tabs(["Historical Customers", "Registered Customers"])
    else:
        historical, registered = st.tabs(["Historical Dataset Customers", "Registered Customers"])
    with historical:
        analyst_or_operations = role in {"analyst", "operations_staff"}
        search_label = "Find historical shopper" if analyst_or_operations else "Find dataset customer ID"
        search = st.text_input(search_label, placeholder="Shopper number" if analyst_or_operations else "Example: 394316")
        limit = st.selectbox("Rows per page", [10, 25, 50, 100], index=1, key="historical_customers_limit")
        offset = st.session_state.setdefault("historical_customers_offset", 0)
        try:
            result = client.get("/staff/customers/historical", {"search": search or None, "limit": limit, "offset": offset})
            rows = [{
                "Customer": f"Historical Shopper #{row['dataset_user_id']}",
                "Orders": row["order_count"],
                "Total spent": _money(row["total_spent"]),
                "Refunds": _money(row["refund_total"]),
                "Last activity": format_datetime(row["last_visit"]),
            } for row in result["items"]]
            display_rows(rows, "Customer")
            pagination_controls("historical_customers", result["total"], limit)
            if result["items"]:
                selected = st.selectbox("Customer detail", [r["dataset_user_id"] for r in result["items"]], format_func=lambda value: f"Customer #{value}")
                detail_button = "View activity" if analyst_or_operations else "Open customer profile"
                if st.button(detail_button, use_container_width=True):
                    st.session_state.historical_customer_detail = selected
                detail_id = st.session_state.get("historical_customer_detail")
                if detail_id:
                    detail = client.get(f"/staff/customers/historical/{detail_id}")
                    detail_heading = f"Historical Shopper #{detail_id}" if analyst_or_operations else f"Customer #{detail_id}"
                    st.subheader(detail_heading)
                    for column, pair in zip(st.columns(4), (("Sessions", detail["session_count"]), ("Orders", detail["order_count"]), ("Total Spent", _money(detail["total_spent"])), ("Refunds", _money(detail["refund_total"])))):
                        column.metric(*pair)
                    st.markdown("#### Recent Orders")
                    display_rows(detail["recent_orders"], "order_id")
                    st.markdown("#### Recent Sessions")
                    display_rows(detail["recent_sessions"], "session_id")
                    st.markdown("#### Product Purchases")
                    display_rows(detail["product_purchases"], "product_id")
            elif search:
                st.info("No historical customer matches that dataset ID.")
        except APIError as exc:
            show_api_error(exc)
    with registered:
        if role == "operations_staff":
            st.caption("Customer contact and purchase summaries are read-only in this workspace.")
        elif role == "analyst":
            st.caption("Registered-customer activity is deidentified for analysis.")
        else:
            st.caption("Registered application customers. Analyst output is deidentified; Admin receives approved account details.")
        try:
            result = client.get("/staff/customers/registered", {"limit": 25, "offset": 0})
            registered_rows = result["items"]
            if role == "analyst":
                registered_rows = [{
                    "Customer": f"Customer #{row['customer_account_id']}",
                    "Orders": row["order_count"],
                    "Total spent": _money(row["total_spent"]),
                    "Account since": format_datetime(row["created_at"]),
                } for row in result["items"]]
            elif role == "operations_staff":
                registered_rows = [{
                    "Customer": row["customer_label"],
                    "Email": row["email"],
                    "Orders": row["order_count"],
                    "Total spent": _money(row["total_spent"]),
                    "Account status": "Active" if row["is_active"] else "Inactive",
                } for row in result["items"]]
            elif role == "admin":
                registered_rows = [{
                    "Customer": row["customer_label"],
                    "Email": row["email"],
                    "Orders": row["order_count"],
                    "Total spent": _money(row["total_spent"]),
                    "Account since": format_datetime(row["created_at"]),
                    "Status": "Active" if row["is_active"] else "Inactive",
                } for row in result["items"]]
            display_rows(registered_rows, "Customer")
            if not result["items"]:
                st.info("No registered customer accounts are available.")
            elif role == "admin":
                st.info("Account activation, lockout recovery, and full safe profile review remain under Customer Accounts.")
        except APIError as exc:
            show_api_error(exc)
