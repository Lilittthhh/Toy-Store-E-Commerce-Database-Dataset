from __future__ import annotations

import pandas as pd
import streamlit as st

from frontend.api_client import APIClient, APIError
from frontend.auth import current_role
from frontend.ui import data_page_header, format_datetime, format_money, format_status, section_label, show_api_error


def _money(value) -> str:
    return format_money(value)


def _queue_table(rows: list[dict], empty: str) -> None:
    if not rows:
        st.info(empty)
        return
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=min(330, 38 + len(rows) * 35))


def _open_staff_page(page: str) -> None:
    st.session_state.staff_page = page


def render(client: APIClient) -> None:
    role = current_role()
    title = "System Management & Business Oversight" if role == "admin" else "Daily E-Commerce Operations"
    data_page_header("Admin Dashboard" if role == "admin" else "Operations Dashboard", title, "dashboard")
    try:
        workspace = client.get("/analytics/workspace")
        baseline = client.get("/analytics/dashboard", {"scope": "imported"}) if role == "admin" else None
    except APIError as exc:
        show_api_error(exc)
        return
    if role == "admin":
        statuses = workspace["orders_by_status"]
        customer_orders = sum(statuses.values())
        pending_processing = statuses.get("pending", 0) + statuses.get("processing", 0)
        cards = (
            ("Staff Users", workspace["active_staff"]),
            ("Registered Customers", workspace["active_customers"]),
            ("Locked Accounts", workspace["locked_accounts"]),
            ("Historical Orders", baseline["metrics"]["orders"]),
            ("Customer Orders", customer_orders),
            ("Pending / Processing", pending_processing),
            ("Pending Refund Requests", workspace["pending_refunds"]),
            ("Ready / Shipped Orders · 7 days", workspace["recent_completed_orders"]),
            ("Recent Customers · 7 days", workspace["recent_customers"]),
        )
        for start in range(0, 9, 3):
            for col, pair in zip(st.columns(3), cards[start:start + 3]): col.metric(*pair)
        section_label("Global business summary")
        for col, pair in zip(st.columns(4), (("Gross Revenue", _money(baseline["metrics"]["gross_revenue"])),
                                             ("Net Revenue", _money(baseline["metrics"]["net_revenue"])),
                                             ("Gross Profit", _money(baseline["metrics"]["gross_profit"])),
                                             ("Sessions", f"{baseline['metrics']['sessions']:,}"))):
            col.metric(*pair)
        st.subheader("Customer orders by status")
        if statuses:
            st.bar_chart(pd.DataFrame([{"Status": k.title(), "Orders": v} for k, v in statuses.items()]).set_index("Status"), color="#274c77", height=245)
        else:
            st.info("No customer orders are currently recorded.")
    else:
        status = workspace["orders_by_status"]
        cards = (("Pending Orders", status.get("pending", 0)), ("Processing Orders", status.get("processing", 0)),
                 ("Pending Refund Requests", workspace["pending_refunds"]), ("Approved Awaiting Processing", workspace["approved_refunds"]),
                 ("Ready / Shipped Orders · 7 days", workspace["recent_completed_orders"]), ("Recent Customers · 7 days", workspace["recent_customers"]))
        for start in range(0, 6, 3):
            for col, pair in zip(st.columns(3), cards[start:start + 3]): col.metric(*pair)
    left, right = st.columns(2)
    with left:
        st.subheader("Orders Needing Action")
        rows = [{"Order": f"#{r['order_id']}", "Customer": f"Customer #{r['customer_account_id']}", "Status": format_status(r["status"]), "Payment": format_status(r["payment_status"]), "Total": _money(r["total"]), "Placed": format_datetime(r["created_at"])} for r in workspace["orders_needing_action"]]
        _queue_table(rows, "No customer orders currently need action.")
        if role in {"admin", "operations_staff"} and rows:
            st.button("Open Orders", key="dashboard_open_orders", on_click=_open_staff_page, args=("Orders",))
    with right:
        st.subheader("Refund Requests Needing Action")
        rows = [{"Request": f"#{r['request_id']}", "Order": f"#{r['order_id']}", "Product": r["product"], "Status": format_status(r["status"]), "Amount": _money(r["amount"])} for r in workspace["refunds_needing_action"]]
        _queue_table(rows, "No refund requests currently need action.")
        if role in {"admin", "operations_staff"} and rows:
            st.button("Open Refund Requests", key="dashboard_open_refunds", on_click=_open_staff_page, args=("Refund Requests",))
