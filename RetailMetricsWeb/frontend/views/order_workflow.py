from __future__ import annotations

import streamlit as st

from frontend.api_client import APIClient, APIError
from frontend.auth import current_role
from frontend.ui import display_rows, format_datetime, format_money, format_status, pagination_controls, show_api_error


def _order_rows(items: list[dict]) -> list[dict]:
    return [
        {
            "Order #": row["order_id"],
            "Customer": f"Customer #{row['customer_account_id']}",
            "Date": format_datetime(row["created_at"]),
            "Total": format_money(row["total_usd"]),
            "Payment": format_status(row["payment_status"]),
            "Status": format_status(row["order_status"]),
        }
        for row in items
    ]


def _render_order_action(client: APIClient, order: dict) -> None:
    order_id = order["order_id"]
    with st.container(border=True):
        st.subheader(f"Next: Order #{order_id}")
        st.caption(
            f"Placed {format_datetime(order['created_at'])} · "
            f"{format_status(order['order_status'])} · {format_status(order['payment_status'])}"
        )
        st.write(
            f"**Customer #{order['customer_account_id']}**  \n"
            f"Order total: **{format_money(order['total_usd'])}**"
        )
        if order["order_status"] == "pending":
            start, cancel = st.columns(2)
            if start.button("Start Processing", type="primary", use_container_width=True, key=f"start_{order_id}"):
                try:
                    client.post(f"/orders/{order_id}/start-processing", {"row_version": order["row_version"]})
                    st.success("Order moved to Processing.")
                    st.rerun()
                except APIError as exc:
                    show_api_error(exc)
            if cancel.button("Cancel Pending Order", use_container_width=True, key=f"staff_cancel_{order_id}"):
                try:
                    client.post(f"/orders/{order_id}/cancel", {"row_version": order["row_version"]})
                    st.success("Pending order cancelled.")
                    st.rerun()
                except APIError as exc:
                    show_api_error(exc)
        elif st.button(
            "Mark Ready / Shipped", type="primary", use_container_width=True, key=f"ready_shipped_{order_id}"
        ):
            try:
                client.post(f"/orders/{order_id}/ready-shipped", {"row_version": order["row_version"]})
                st.success("Order marked Ready / Shipped.")
                st.rerun()
            except APIError as exc:
                show_api_error(exc)


def render(client: APIClient) -> None:
    st.divider()
    st.subheader("Orders to process")
    st.caption("Work from the oldest outstanding customer order first. Every pending or processing order is listed below.")
    role = current_role()
    can_transition = role in {"admin", "operations_staff"}

    action_limit = 25
    action_offset = st.session_state.setdefault("order_action_offset", 0)
    try:
        action_result = client.get(
            "/order-workflow/orders",
            {"actionable_only": True, "limit": action_limit, "offset": action_offset},
        )
    except APIError as exc:
        show_api_error(exc)
        return

    actionable = sorted(
        (row for row in action_result["items"] if row["order_status"] in {"pending", "processing"}),
        key=lambda row: (str(row.get("created_at") or ""), row["order_id"]),
    )
    if actionable:
        selected_id = st.selectbox(
            "Order to process",
            [row["order_id"] for row in actionable],
            format_func=lambda value: next(
                f"Order #{row['order_id']} · {format_datetime(row['created_at'])}"
                for row in actionable
                if row["order_id"] == value
            ),
            key="order_workflow_selected",
        )
        selected = next(row for row in actionable if row["order_id"] == selected_id)
        if can_transition:
            _render_order_action(client, selected)
        else:
            st.info("Analyst access is read-only. Order status actions are available only to Admin and Operations Staff.")

        st.markdown("**Full action queue · oldest first**")
        display_rows(_order_rows(actionable), "Order #")
        pagination_controls("order_action", action_result["total"], action_limit)
    else:
        st.success("The order action queue is clear.")

def render_history(client: APIClient) -> None:
    st.subheader("Customer order history")
    st.caption("Browse every customer order or filter the historical list by status.")
    filters, page_size = st.columns([2, 1])
    selected_status = filters.selectbox(
        "History filter",
        ["all", "pending", "processing", "ready_shipped", "delivered", "cancelled", "refunded"],
        format_func=lambda value: "All customer orders" if value == "all" else f"{format_status(value)} orders",
        key="order_workflow_status",
    )
    limit = page_size.selectbox("History rows per page", [10, 25, 50, 100], index=1, key="order_workflow_limit")
    offset = st.session_state.setdefault("order_workflow_offset", 0)
    params = {"limit": limit, "offset": offset}
    if selected_status != "all":
        params["status_filter"] = selected_status
    try:
        result = client.get("/order-workflow/orders", params)
        display_rows(_order_rows(result["items"]), "Order #")
        pagination_controls("order_workflow", result["total"], limit)
    except APIError as exc:
        show_api_error(exc)
