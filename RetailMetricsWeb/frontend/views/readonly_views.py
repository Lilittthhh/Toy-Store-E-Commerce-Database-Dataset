from __future__ import annotations

import streamlit as st

from frontend.api_client import APIClient, APIError
from frontend.ui import data_page_header, display_rows, format_datetime, pagination_controls, section_label, show_api_error


def _display_value(value) -> str:
    return "—" if value is None or value == "" else str(value)


def _session_rows(rows: list[dict]) -> list[dict]:
    return [{
        "Session #": row["website_session_id"],
        "Date": format_datetime(row.get("created_at")),
        "Historical Shopper": f"#{row['user_id']}" if row.get("user_id") is not None else "—",
        "Repeat Visit": "Yes" if row.get("is_repeat_session") else "No",
        "Traffic Source": _display_value(row.get("utm_source")),
        "Campaign": _display_value(row.get("utm_campaign")),
        "Content": _display_value(row.get("utm_content")),
        "Device": _display_value(row.get("device_type")),
        "Referrer": _display_value(row.get("http_referer")),
    } for row in rows]


def _pageview_rows(rows: list[dict]) -> list[dict]:
    return [{
        "Pageview #": row["website_pageview_id"],
        "Date": format_datetime(row.get("created_at")),
        "Session #": row["website_session_id"],
        "Page": _display_value(row.get("pageview_url")),
    } for row in rows]


def render_sessions(client: APIClient, embedded: bool = False) -> None:
    if not embedded:
        data_page_header(
            "Website Sessions",
            "Read-only browsing of imported acquisition and device activity.",
            "sessions",
        )
    else:
        st.subheader("Website Sessions")
        st.caption("Read-only imported acquisition and device activity.")
    section_label("Read-only filters")
    with st.container(border=True):
        first, second, third, fourth = st.columns(4)
        user_id = first.number_input("Shopper user ID", min_value=0, value=0, step=1)
        source = second.text_input("Traffic source")
        device = third.text_input("Device type")
        order_filter = fourth.selectbox("Order status", ["all", "with", "without"])
        limit = st.selectbox("Rows per page", [10, 25, 50, 100], index=1, key="sessions_limit")
    offset = st.session_state.setdefault("sessions_offset", 0)
    params = {"limit": limit, "offset": offset}
    if user_id:
        params["user_id"] = int(user_id)
    if source:
        params["utm_source"] = source
    if device:
        params["device_type"] = device
    if order_filter != "all":
        params["has_order"] = order_filter == "with"
    try:
        result = client.get("/website-sessions", params)
        display_rows(_session_rows(result["items"]), "Session #")
        pagination_controls("sessions", result["total"], limit)
    except APIError as exc:
        show_api_error(exc)


def render_pageviews(client: APIClient, embedded: bool = False) -> None:
    if not embedded:
        data_page_header(
            "Website Pageviews",
            "Read-only browsing of page-level activity and session journeys.",
            "pageviews",
        )
    else:
        st.subheader("Website Pageviews")
        st.caption("Read-only page-level activity and session journeys.")
    section_label("Read-only filters")
    with st.container(border=True):
        first, second, third = st.columns([1, 2, 1])
        session_id = first.number_input("Website session ID", min_value=0, value=0, step=1)
        search = second.text_input("URL contains")
        limit = third.selectbox("Rows per page", [10, 25, 50, 100], index=1, key="pageviews_limit")
    offset = st.session_state.setdefault("pageviews_offset", 0)
    params = {"limit": limit, "offset": offset}
    if session_id:
        params["website_session_id"] = int(session_id)
    if search:
        params["search"] = search
    try:
        result = client.get("/website-pageviews", params)
        display_rows(_pageview_rows(result["items"]), "Pageview #")
        pagination_controls("pageviews", result["total"], limit)
    except APIError as exc:
        show_api_error(exc)
