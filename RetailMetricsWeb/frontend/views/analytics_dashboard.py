from __future__ import annotations

from decimal import Decimal

import pandas as pd
import streamlit as st

from frontend.api_client import APIClient, APIError
from frontend.auth import current_role
from frontend.ui import data_page_header, display_rows, format_money, section_label, show_api_error


def render(client: APIClient) -> None:
    role = current_role()
    data_page_header("Analytics Dashboard", "Business Intelligence & Performance Analysis", "analytics_dashboard")
    scope = st.selectbox(
        "Reporting scope", ["imported", "application", "combined"],
        format_func=lambda value: {"imported": "Historical Data", "application": "Application-Created", "combined": "Combined"}[value],
    )
    try:
        report = client.get("/analytics/dashboard", {"scope": scope})
    except APIError as exc:
        show_api_error(exc)
        return
    metrics = report["metrics"]
    if role == "analyst":
        refund_count = sum(int(row["refunds"]) for row in report["refund_trend"])
        cards = (
            ("Gross Revenue", format_money(metrics["gross_revenue"])),
            ("Net Revenue", format_money(metrics["net_revenue"])),
            ("Gross Profit", format_money(metrics["gross_profit"])),
            ("Orders", f"{metrics['orders']:,}"),
            ("Sessions", f"{metrics['sessions']:,}"),
            ("Conversion Rate", "Not applicable" if metrics["conversion_rate"] is None else f"{float(metrics['conversion_rate']):.2f}%"),
            ("Refund Count", f"{refund_count:,}"),
            ("Refunded Amount", format_money(metrics["refund_amount"])),
            ("COGS", format_money(metrics["cogs"])),
        )
        columns_per_row = 3
    else:
        cards = (
            ("Gross Revenue", format_money(metrics["gross_revenue"])),
            ("Net Revenue", format_money(metrics["net_revenue"])),
            ("Gross Profit", format_money(metrics["gross_profit"])),
            ("COGS", format_money(metrics["cogs"])),
            ("Orders", f"{metrics['orders']:,}"),
            ("Conversion Rate", "Not applicable" if metrics["conversion_rate"] is None else f"{float(metrics['conversion_rate']):.2f}%"),
            ("Refund Amount", format_money(metrics["refund_amount"])),
            ("Sessions", f"{metrics['sessions']:,}"),
        )
        columns_per_row = 4
    for start in range(0, len(cards), columns_per_row):
        for column, (label, value) in zip(st.columns(columns_per_row), cards[start:start + columns_per_row]):
            column.metric(label, value)
    st.caption("Conversion is calculated for historical website activity. Application orders are not linked to historical website sessions.")
    left, right = st.columns(2)
    time_frame = pd.DataFrame(report["time_series"])
    with left:
        section_label("Trend")
        st.subheader("Revenue over time")
        if time_frame.empty:
            st.info("No orders are available for this scope.")
        else:
            st.line_chart(time_frame.set_index("period")[["revenue"]], color="#0f766e", height=285)
    with right:
        section_label("Trend")
        st.subheader("Orders over time")
        if time_frame.empty:
            st.info("No orders are available for this scope.")
        else:
            st.bar_chart(time_frame.set_index("period")[["orders"]], color="#274c77", height=285)
    products = pd.DataFrame(report["products"])
    st.subheader("Product performance")
    if products.empty:
        st.info("No product performance is available for this scope.")
    else:
        st.bar_chart(products.set_index("product_name")[["revenue", "net_revenue"]], color=["#274c77", "#0f766e"], height=320)
        if role == "analyst":
            display_rows([{
                "Product": row["product_name"],
                "Orders": row["orders"],
                "Units": row["units"],
                "Revenue": format_money(row["revenue"]),
                "Net revenue": format_money(row["net_revenue"]),
                "Gross profit": format_money(Decimal(str(row["revenue"])) - Decimal(str(row["cogs"]))),
                "Refunds": format_money(row["refunds"]),
            } for row in report["products"]], "Product")
        else:
            st.dataframe(products.rename(columns={"product_name": "Product", "orders": "Orders", "units": "Units", "revenue": "Revenue", "cogs": "COGS", "refunds": "Refunds", "net_revenue": "Net Revenue"}), use_container_width=True, hide_index=True)
    if report["traffic_sources"]:
        traffic, devices = st.columns([1.4, 1])
        with traffic:
            st.subheader("Traffic-source performance")
            if role == "analyst":
                display_rows([{
                    "Traffic source": row["source"],
                    "Sessions": row["sessions"],
                    "Orders": row["orders"],
                    "Conversion rate": f"{float(row['conversion_rate']):.2f}%",
                    "Revenue": format_money(row["revenue"]),
                } for row in report["traffic_sources"]], "Traffic source")
            else:
                st.dataframe(pd.DataFrame(report["traffic_sources"]), use_container_width=True, hide_index=True)
        with devices:
            st.subheader("Device breakdown")
            st.bar_chart(pd.DataFrame(report["devices"]).set_index("device"), color="#627d98", height=285)
    if report["refund_trend"]:
        st.subheader("Refund trend")
        st.line_chart(pd.DataFrame(report["refund_trend"]).set_index("period")[["amount"]], color="#c05640", height=250)
