from __future__ import annotations

from html import escape
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from frontend.api_client import APIError


DESIGN_SYSTEM_PATH = Path(__file__).resolve().parent / "assets" / "retailmetrics.css"


def _apply_design_system() -> None:
    with DESIGN_SYSTEM_PATH.open(encoding="utf-8") as stylesheet:
        st.markdown(f"<style>{stylesheet.read()}</style>", unsafe_allow_html=True)


def apply_theme() -> None:
    _apply_design_system()


def apply_anonymous_theme() -> None:
    _apply_design_system()


def apply_customer_theme() -> None:
    _apply_design_system()


def auth_card_header(title: str, subtitle: str, portal_label: str | None = None):
    card = st.container(border=True)
    card.markdown('<span class="rm-auth-card-marker"></span>', unsafe_allow_html=True)
    card.markdown(
        """
        <div class="rm-auth-brand">
          <div class="rm-auth-brand-mark">RM</div>
          <div class="rm-auth-brand-name">RetailMetrics</div>
          <div class="rm-auth-brand-subtitle">Toy Store · Shop · Track · Enjoy</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    card.title(title)
    card.caption(subtitle)
    return card


def customer_site_footer() -> None:
    st.markdown(
        """
        <footer class="rm-site-footer">
          <div class="rm-site-footer-inner">
            <div class="rm-site-footer-brand">
              <span class="rm-site-brand-mark">RM</span>
              <div>
                <strong>RetailMetrics Toy Store</strong>
                <small>A little play. A lot of possibility.</small>
              </div>
            </div>
            <p class="rm-site-footer-copy">
              Find your next favorite, save your delivery details, and follow your order all the way home.
              Payments in this demonstration store are simulated.
            </p>
          </div>
        </footer>
        """,
        unsafe_allow_html=True,
    )


def show_api_error(error: APIError) -> None:
    labels = {
        0: "Connection problem",
        401: "Your session has expired. Please log in again.",
        403: "You are not authorized to perform this action.",
        404: "The requested record was not found.",
        409: "The record changed or conflicts with existing data.",
        422: "Please correct the submitted values.",
    }
    heading = labels.get(error.status_code, "Request failed")
    st.error(f"**{heading}**  \n{error.message}")


def render_sidebar_brand(username: str | None = None, role: str | None = None) -> None:
    st.sidebar.markdown(
        """
        <div class="rm-brand">
          <div class="rm-brand-row">
            <div class="rm-brand-mark">RM</div>
            <div>
              <div class="rm-brand-name">RetailMetrics</div>
              <div class="rm-brand-subtitle">Toy Store · Staff Portal</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if username and role:
        role_label = role.replace("_", " ").title()
        st.sidebar.markdown(
            f"""
            <div class="rm-user-card">
              <div class="rm-user-name">{escape(username)}</div>
              <div class="rm-role-badge rm-role-badge-{escape(role)}">{escape(role_label)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_sidebar_footer(customer: bool = False) -> None:
    message = "Making every toy bring a little more joy." if customer else "RetailMetrics · Store workspace"
    class_name = "rm-sidebar-footer rm-sidebar-footer-customer" if customer else "rm-sidebar-footer"
    st.sidebar.markdown(
        f'<div class="{class_name}">{escape(message)}</div>',
        unsafe_allow_html=True,
    )


def render_staff_workspace_banner(role: str) -> None:
    banners = {
        "admin": ("Store administration", "People, products, and performance — all in one place."),
        "operations_staff": ("Fulfillment workspace", "Keep orders moving and customer requests on track."),
        "analyst": ("Business intelligence", "Explore performance, understand trends, and prepare reports. Read-only access."),
    }
    title, caption = banners[role]
    st.markdown(
        f'<div class="rm-staff-welcome rm-staff-welcome-{escape(role)}">'
        f"<strong>{escape(title)}</strong><span>{escape(caption)}</span></div>",
        unsafe_allow_html=True,
    )


def render_mobile_topbar(page: str, identity: str, role: str) -> None:
    """Compact context bar paired with Streamlit's persistent native menu control."""
    role_label = role.replace("_", " ").title()
    st.markdown(
        f"""
        <div class="rm-mobile-topbar rm-mobile-topbar-{escape(role)}">
          <div class="rm-mobile-topbar-brand">RetailMetrics · {escape(role_label)}</div>
          <div class="rm-mobile-topbar-page">{escape(page)}</div>
          <div class="rm-mobile-topbar-user">{escape(identity)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def readiness_checklist(items: tuple[tuple[str, bool], ...]) -> None:
    """Render safe configuration state without presenting it as tabular data."""
    rows = "".join(
        (
            '<li class="rm-check-ready"><span aria-hidden="true">✓</span>'
            f'<strong>{escape(label)}</strong><small>Configured</small></li>'
            if ready else
            '<li class="rm-check-missing"><span aria-hidden="true">!</span>'
            f'<strong>{escape(label)}</strong><small>Not configured</small></li>'
        )
        for label, ready in items
    )
    st.markdown(f'<ul class="rm-readiness-list">{rows}</ul>', unsafe_allow_html=True)


def detail_summary(title: str, subtitle: str, facts: tuple[tuple[str, Any], ...]) -> None:
    """Compact selected-record context panel for actions and one-record details."""
    fact_markup = "".join(
        f'<div><span>{escape(str(label))}</span><strong>{escape(str(value))}</strong></div>'
        for label, value in facts
    )
    st.markdown(
        f'<section class="rm-detail-summary"><header><strong>{escape(title)}</strong>'
        f'<span>{escape(subtitle)}</span></header><div class="rm-detail-facts">{fact_markup}</div></section>',
        unsafe_allow_html=True,
    )


def page_header(title: str, caption: str) -> None:
    role = (st.session_state.get("current_user") or {}).get("role")
    customer = st.session_state.get("active_portal") == "customer"
    label = "Your store" if customer else {
        "admin": "Store management", "operations_staff": "Daily operations", "analyst": "Insights & reports",
    }.get(role, "RetailMetrics")
    st.markdown(
        f'<span class="rm-page-marker"></span><div class="rm-page-kicker">{escape(label)}</div>',
        unsafe_allow_html=True,
    )
    st.title(title)
    st.caption(caption)
    st.markdown('<div class="rm-page-rule"></div>', unsafe_allow_html=True)


def format_value(value: Any, unavailable: str = "—") -> Any:
    """Normalize empty presentation values without changing stored data."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return unavailable
    return value


def format_status(value: str | None, unavailable: str = "—") -> str:
    if value is None or not str(value).strip():
        return unavailable
    if str(value).strip().lower() == "ready_shipped":
        return "Ready / Shipped"
    return str(value).strip().replace("_", " ").title()


def format_money(value: Any, unavailable: str = "—") -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        return unavailable
    try:
        return f"${Decimal(str(value)):,.2f}"
    except (InvalidOperation, ValueError):
        return str(value)


def status_badge(value: str | None) -> None:
    label = format_status(value)
    css = str(value).strip().lower().replace("_", "-") if value else "unknown"
    st.markdown(f'<span class="rm-status-pill rm-status-{escape(css)}">{escape(label)}</span>', unsafe_allow_html=True)


def data_page_header(title: str, caption: str, key: str) -> None:
    heading, action = st.columns([6, 1.15], vertical_alignment="bottom")
    with heading:
        page_header(title, caption)
    with action:
        if st.button(
            "Refresh Data",
            key=f"{key}_refresh",
            help="Fetch the latest available records",
            use_container_width=True,
        ):
            st.toast("Data refreshed successfully.")


def section_label(text: str) -> None:
    st.markdown(
        f'<div class="rm-section-label">{escape(text)}</div>',
        unsafe_allow_html=True,
    )


def summary_strip(items: tuple[tuple[str, Any], ...]) -> None:
    """Compact secondary facts for dense operational pages."""
    cells = "".join(
        f'<div class="rm-summary-fact"><span>{escape(str(label))}</span><strong>{escape(str(value))}</strong></div>'
        for label, value in items
    )
    st.markdown(f'<div class="rm-summary-strip">{cells}</div>', unsafe_allow_html=True)


def source_legend(origins: tuple[str, ...] = ("imported", "web", "customer")) -> None:
    labels = {
        "imported": ('rm-source-imported', 'Historical data'),
        "web": ('rm-source-application', 'Application-created'),
        "staff": ('rm-source-application', 'Application-created'),
        "customer": ('rm-source-application', 'Customer-created'),
    }
    pills = "".join(
        f'<span class="rm-source-pill {labels[origin][0]}">{labels[origin][1]}</span>'
        for origin in origins
    )
    st.markdown(
        f'<div class="rm-source-legend">{pills}</div>',
        unsafe_allow_html=True,
    )


def source_label(row: dict[str, Any]) -> str:
    labels = {
        "imported": "Historical data",
        "customer": "Customer-created",
        "web": "Application-created",
        "staff": "Application-created",
    }
    return labels.get(row.get("origin"), "Application-created")


def format_datetime(value: Any) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        return "—"
    try:
        parsed = pd.to_datetime(value)
        return parsed.strftime("%b %d, %Y · %I:%M %p")
    except (TypeError, ValueError):
        return str(value)


def display_rows(rows: list[dict[str, Any]], id_column: str) -> None:
    if not rows:
        st.info("No records match the current filters.")
        return
    normalized = []
    for row in rows:
        item = dict(row)
        if "origin" in item:
            item["Source"] = source_label(item)
            item.pop("origin", None)
        item.pop("created_by_app_user_id", None)
        item.pop("row_version", None)
        for column in tuple(item):
            if column.lower().endswith("status") or column.lower() == "status":
                item[column] = format_status(item[column])
            elif column.endswith("_at"):
                item[column] = format_datetime(item[column])
            else:
                item[column] = format_value(item[column])
        normalized.append(item)
    frame = pd.DataFrame(normalized)
    columns = [id_column, *[column for column in frame.columns if column != id_column]]
    frame = frame[columns]
    frame.columns = [column.replace("_", " ").title().replace("Usd", "USD").replace("Id", "ID") for column in frame.columns]
    configs = {
        column: st.column_config.TextColumn(column, width="large")
        for column in {"Http Referer", "Pageview Url", "Product Name"}
        if column in frame.columns
    }
    if "Source" in frame.columns:
        configs["Source"] = st.column_config.TextColumn("Source", width="medium")
    for column in frame.columns:
        if column.endswith(" ID") or column == "ID":
            configs[column] = st.column_config.NumberColumn(column, width="small", format="%d")
        elif column.endswith(" USD"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
            configs[column] = st.column_config.NumberColumn(column, width="small", format="$%.2f")
    st.dataframe(
        frame,
        use_container_width=True,
        hide_index=True,
        height=max(170, min(510, 38 + len(frame) * 34)),
        column_config=configs,
    )


def pagination_controls(key: str, total: int, limit: int) -> int:
    offset_key = f"{key}_offset"
    st.session_state.setdefault(offset_key, 0)
    offset = min(st.session_state[offset_key], max(0, ((max(total, 1) - 1) // limit) * limit))
    st.session_state[offset_key] = offset
    left, middle, right = st.columns([1.15, 3, 1.15], vertical_alignment="center")
    if left.button(
        "← Previous",
        key=f"{key}_previous",
        disabled=offset == 0,
        use_container_width=True,
    ):
        st.session_state[offset_key] = max(0, offset - limit)
        st.rerun()
    page_number = offset // limit + 1
    pages = max(1, (total + limit - 1) // limit)
    middle.caption(f"Page {page_number} of {pages} · {total:,} records")
    if right.button(
        "Next →",
        key=f"{key}_next",
        disabled=offset + limit >= total,
        use_container_width=True,
    ):
        st.session_state[offset_key] = offset + limit
        st.rerun()
    return offset
