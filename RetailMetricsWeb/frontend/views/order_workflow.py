from __future__ import annotations

import streamlit as st

from frontend.api_client import APIClient, APIError
from frontend.auth import current_role
from frontend.ui import display_rows, format_datetime, format_money, format_status, pagination_controls, show_api_error


def render(client: APIClient) -> None:
    st.divider()
    st.subheader("Customer Orders")
    st.caption("Review customer purchases and move eligible orders through fulfillment.")
    role = current_role()
    can_transition = role in {"admin", "operations_staff"}
    filters, page_size = st.columns([2, 1])
    selected_status = filters.selectbox(
        "Workflow queue",
        ["all", "pending", "processing", "ready_shipped", "delivered", "cancelled", "refunded"],
        format_func=lambda value: "All customer orders" if value == "all" else f"{format_status(value)} orders",
        key="order_workflow_status",
    )
    limit = page_size.selectbox("Workflow rows per page", [10, 25, 50, 100], index=1, key="order_workflow_limit")
    offset = st.session_state.setdefault("order_workflow_offset", 0)
    params = {"limit": limit, "offset": offset}
    if selected_status != "all":
        params["status_filter"] = selected_status
    try:
        result = client.get("/order-workflow/orders", params)
        display_rows([
            {
                "Order #": row["order_id"],
                "Customer": f"Customer #{row['customer_account_id']}",
                "Date": format_datetime(row["created_at"]),
                "Total": format_money(row["total_usd"]),
                "Payment": format_status(row["payment_status"]),
                "Status": format_status(row["order_status"]),
            }
            for row in result["items"]
        ], "Order #")
        pagination_controls("order_workflow", result["total"], limit)
    except APIError as exc:
        show_api_error(exc)
        return
    if not can_transition:
        st.info("Analyst access is read-only. Order status actions are available only to Admin and Operations Staff.")
        return
    actionable = [row for row in result["items"] if row["order_status"] in {"pending", "processing"}]
    if not actionable:
        st.info("No orders on this page currently have an available lifecycle action.")
        return
    selected_id = st.selectbox(
        "Order to process",
        [row["order_id"] for row in actionable],
        format_func=lambda value: f"Order #{value}",
        key="order_workflow_selected",
    )
    order = next(row for row in actionable if row["order_id"] == selected_id)
    action_panel, _ = st.columns([2.2, 1])
    with action_panel:
        with st.container(border=True):
            st.write(
                f"**Order #{order['order_id']} · Customer #{order['customer_account_id']}**  \n"
                f"{format_status(order['order_status'])} · {format_status(order['payment_status'])} · {format_money(order['total_usd'])}"
            )
            if order["order_status"] == "pending":
                start, cancel = st.columns(2)
                if start.button("Start Processing", type="primary", use_container_width=True, key=f"start_{selected_id}"):
                    try:
                        client.post(f"/orders/{selected_id}/start-processing", {"row_version": order["row_version"]})
                        st.success("Order moved to Processing.")
                        st.rerun()
                    except APIError as exc:
                        show_api_error(exc)
                if cancel.button("Cancel Pending Order", use_container_width=True, key=f"staff_cancel_{selected_id}"):
                    try:
                        client.post(f"/orders/{selected_id}/cancel", {"row_version": order["row_version"]})
                        st.success("Pending order cancelled.")
                        st.rerun()
                    except APIError as exc:
                        show_api_error(exc)
            elif order["order_status"] == "processing":
                if st.button("Mark Ready / Shipped", type="primary", use_container_width=True, key=f"ready_shipped_{selected_id}"):
                    try:
                        client.post(f"/orders/{selected_id}/ready-shipped", {"row_version": order["row_version"]})
                        st.success("Order marked Ready / Shipped.")
                        st.rerun()
                    except APIError as exc:
                        show_api_error(exc)
