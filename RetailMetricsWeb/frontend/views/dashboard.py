from __future__ import annotations

from html import escape

import pandas as pd
import streamlit as st

from frontend.api_client import APIClient, APIError
from frontend.auth import current_role
from frontend.ui import data_page_header, format_datetime, format_money, format_status, section_label, show_api_error, summary_strip


def _queue_list(rows: list[dict], empty: str, *, refund: bool = False) -> None:
    if not rows:
        st.info(empty)
        return
    visible = rows[:6]
    markup = []
    for row in visible:
        if refund:
            primary = f"{row['Request']} · {row['Order']}"
            secondary = f"{row['Product']} · {row['Status']}"
            meta = row["Amount"]
        else:
            primary = f"{row['Order']} · {row['Customer']}"
            secondary = f"{row['Status']} · {row['Payment']} · {row['Placed']}"
            meta = row["Total"]
        markup.append(
            '<div class="rm-record-row"><div class="rm-record-main">'
            f'<strong>{escape(primary)}</strong><span>{escape(secondary)}</span></div>'
            '<div class="rm-record-meta">Requires review</div>'
            f'<div class="rm-record-value">{escape(meta)}</div></div>'
        )
    st.markdown(f'<div class="rm-record-list">{"".join(markup)}</div>', unsafe_allow_html=True)
    if len(rows) > len(visible):
        st.caption(f"Showing {len(visible)} of {len(rows)} records needing action.")


def _open_staff_page(page: str) -> None:
    st.session_state.staff_page = page


def render(client: APIClient) -> None:
    role = current_role()
    title = "System management and business oversight" if role == "admin" else "Daily e-commerce operations"
    data_page_header("Admin Dashboard" if role == "admin" else "Operations Dashboard", title, "dashboard")
    actions = (("Manage catalog", "Storefront Catalog", "Configure products and availability"),
               ("Manage people", "User Management", "Manage staff access"),
               ("View reports", "Business Reports", "Explore store performance")) if role == "admin" else (
                   ("Work on orders", "Orders", "Review purchases and update fulfillment"),
                   ("Review refunds", "Refund Requests", "Review and process customer requests"),
                   ("Find a customer", "Customers", "Look up customer activity"))
    with st.container(key="workspace_quick_actions"):
        for column, (label, destination, description) in zip(st.columns(3), actions):
            column.button(label, key=f"dashboard_quick_{destination}", use_container_width=True,
                          on_click=_open_staff_page, args=(destination,))
            column.caption(description)
    try:
        workspace = client.get("/analytics/workspace")
        baseline = client.get("/analytics/dashboard", {"scope": "imported"}) if role == "admin" else None
    except APIError as exc:
        show_api_error(exc)
        return

    if role == "admin":
        statuses = workspace["orders_by_status"]
        customer_orders = sum(statuses.values())
        headline = (
            ("Customer Orders", customer_orders),
            ("Pending / Processing", statuses.get("pending", 0) + statuses.get("processing", 0)),
            ("Pending Refund Requests", workspace["pending_refunds"]),
        )
        for column, pair in zip(st.columns(3), headline):
            column.metric(*pair)
        summary_strip((("Active staff", workspace["active_staff"]),
                       ("Registered customers", workspace["active_customers"]),
                       ("Locked accounts", workspace["locked_accounts"]),
                       ("Ready / Shipped · 7 days", workspace["recent_completed_orders"]),
                       ("New customers · 7 days", workspace["recent_customers"])))
        section_label("Historical business baseline")
        summary_strip((("Historical orders", f"{baseline['metrics']['orders']:,}"),
                       ("Gross revenue", format_money(baseline["metrics"]["gross_revenue"])),
                       ("Net revenue", format_money(baseline["metrics"]["net_revenue"])),
                       ("Gross profit", format_money(baseline["metrics"]["gross_profit"])),
                       ("Sessions", f"{baseline['metrics']['sessions']:,}")))
        st.subheader("Customer order workload")
        if statuses:
            chart = pd.DataFrame([{"Status": format_status(status), "Orders": count}
                                  for status, count in statuses.items()]).set_index("Status")
            st.bar_chart(chart, color="#e6533d", height=235)
        else:
            st.info("No customer orders are currently recorded.")
    else:
        status = workspace["orders_by_status"]
        headline = (("Pending Orders", status.get("pending", 0)),
                    ("Processing Orders", status.get("processing", 0)),
                    ("Pending Refund Requests", workspace["pending_refunds"]),
                    ("Approved Awaiting Processing", workspace["approved_refunds"]))
        for column, pair in zip(st.columns(4), headline):
            column.metric(*pair)
        summary_strip((("Ready / Shipped · 7 days", workspace["recent_completed_orders"]),
                       ("New customers · 7 days", workspace["recent_customers"])))

    section_label("Operational queues")
    left, right = st.columns(2)
    with left:
        st.subheader("Orders needing action")
        order_rows = [{"Order": f"#{row['order_id']}", "Customer": f"Customer #{row['customer_account_id']}",
                       "Status": format_status(row["status"]), "Payment": format_status(row["payment_status"]),
                       "Total": format_money(row["total"]), "Placed": format_datetime(row["created_at"])}
                      for row in workspace["orders_needing_action"]]
        _queue_list(order_rows, "No customer orders currently need action.")
        if role in {"admin", "operations_staff"} and order_rows:
            st.button("Open Orders", key="dashboard_open_orders", on_click=_open_staff_page, args=("Orders",))
    with right:
        st.subheader("Refund requests needing action")
        refund_rows = [{"Request": f"#{row['request_id']}", "Order": f"#{row['order_id']}",
                        "Product": row["product"], "Status": format_status(row["status"]),
                        "Amount": format_money(row["amount"])}
                       for row in workspace["refunds_needing_action"]]
        _queue_list(refund_rows, "No refund requests currently need action.", refund=True)
        if role in {"admin", "operations_staff"} and refund_rows:
            st.button("Open Refund Requests", key="dashboard_open_refunds", on_click=_open_staff_page, args=("Refund Requests",))
