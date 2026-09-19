from __future__ import annotations

from decimal import Decimal

import pandas as pd
import streamlit as st

from frontend.api_client import APIClient, APIError
from frontend.ui import data_page_header, display_rows, format_money, section_label, show_api_error


def _percentage(value) -> str:
    return "Not applicable" if value is None else f"{Decimal(str(value)):.2f}%"


def render(client: APIClient) -> None:
    data_page_header(
        "Business Reports",
        "Decision-ready sales, customer, traffic, product, and refund performance.",
        "business_reports",
    )
    scope = st.selectbox(
        "Reporting scope",
        ["imported", "application", "combined"],
        format_func=lambda value: {
            "imported": "Historical Data",
            "application": "Application-Created",
            "combined": "Combined",
        }[value],
        key="business_reports_scope",
    )
    try:
        report = client.get("/analytics/dashboard", {"scope": scope})
        workspace = client.get("/analytics/workspace")
        historical = client.get("/staff/customers/historical", {"limit": 1, "offset": 0})
        registered = client.get("/staff/customers/registered", {"limit": 1, "offset": 0})
    except APIError as exc:
        show_api_error(exc)
        return

    metrics = report["metrics"]
    order_count = int(metrics["orders"])
    average_order = Decimal(str(metrics["gross_revenue"])) / order_count if order_count else Decimal("0")

    section_label("Sales summary")
    sales_cards = (
        ("Gross Revenue", format_money(metrics["gross_revenue"])),
        ("Net Revenue", format_money(metrics["net_revenue"])),
        ("Gross Profit", format_money(metrics["gross_profit"])),
        ("Orders", f"{order_count:,}"),
        ("Average Order Value", format_money(average_order)),
    )
    for column, (label, value) in zip(st.columns(5), sales_cards):
        column.metric(label, value)

    section_label("Product performance")
    products = []
    for row in report["products"]:
        products.append({
            "Product": row["product_name"],
            "Orders": row["orders"],
            "Units": row["units"],
            "Revenue": format_money(row["revenue"]),
            "Gross Profit": format_money(Decimal(str(row["revenue"])) - Decimal(str(row["cogs"]))),
            "Refunds": format_money(row["refunds"]),
        })
    display_rows(products, "Product")

    section_label("Customer activity")
    customer_cards = (
        ("Historical Shoppers", f"{historical['total']:,}"),
        ("Active Registered Customers", f"{int(workspace['active_customers']):,}"),
        ("Orders in Scope", f"{order_count:,}"),
        ("Revenue per Order", format_money(average_order)),
    )
    for column, (label, value) in zip(st.columns(4), customer_cards):
        column.metric(label, value)
    st.caption("Customer counts are aggregate and deidentified. Open Customers for pseudonymous activity details.")
    if registered["total"] != workspace["active_customers"]:
        st.caption(f"Registered accounts: {registered['total']:,} total, including inactive accounts.")

    section_label("Traffic & conversion")
    traffic_cards = (
        ("Website Sessions", f"{int(metrics['sessions']):,}"),
        ("Conversion Rate", _percentage(metrics["conversion_rate"])),
    )
    for column, (label, value) in zip(st.columns(2), traffic_cards):
        column.metric(label, value)
    if report["traffic_sources"]:
        traffic_rows = [{
            "Source": row["source"],
            "Sessions": row["sessions"],
            "Orders": row["orders"],
            "Conversion": _percentage(row["conversion_rate"]),
            "Revenue": format_money(row["revenue"]),
        } for row in report["traffic_sources"]]
        display_rows(traffic_rows, "Source")
    else:
        st.info("Traffic attribution is not applicable to application-created orders without imported website sessions.")

    section_label("Refund analysis")
    refund_count = sum(int(row["refunds"]) for row in report["refund_trend"])
    refund_rate = Decimal(refund_count) / order_count * 100 if order_count else None
    for column, (label, value) in zip(st.columns(3), (
        ("Refunds", f"{refund_count:,}"),
        ("Refunded Amount", format_money(metrics["refund_amount"])),
        ("Refund Rate", _percentage(refund_rate)),
    )):
        column.metric(label, value)

    section_label("Revenue / activity trends")
    trend, refunds = st.columns(2)
    time_frame = pd.DataFrame(report["time_series"])
    with trend:
        st.subheader("Revenue and orders over time")
        if time_frame.empty:
            st.info("No order trend is available for this scope.")
        else:
            st.line_chart(time_frame.set_index("period")[["revenue", "orders"]], height=280)
    refund_frame = pd.DataFrame(report["refund_trend"])
    with refunds:
        st.subheader("Refund activity over time")
        if refund_frame.empty:
            st.info("No refund trend is available for this scope.")
        else:
            st.line_chart(refund_frame.set_index("period")[["amount", "refunds"]], height=280)

    st.caption("All figures come from existing read-only business analytics. Application orders remain separate from historical website sessions.")
