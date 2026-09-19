from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import streamlit as st

from frontend.api_client import APIClient, APIError
from frontend.auth import can_mutate, current_role
from frontend.ui import (
    data_page_header,
    display_rows,
    format_datetime,
    format_money,
    format_status,
    pagination_controls,
    section_label,
    show_api_error,
    source_label,
    source_legend,
)
from frontend.views import order_workflow


PATHS = {
    "products": ("Products", "/products", "product_id"),
    "orders": ("Orders", "/orders", "order_id"),
    "refunds": ("Refunds", "/refunds", "order_item_refund_id"),
}


def _timestamp(prefix: str, value: str | None = None) -> str:
    initial = datetime.fromisoformat(value) if value else datetime.now().replace(microsecond=0)
    date_column, time_column = st.columns(2)
    selected_date = date_column.date_input("Created date", initial.date(), key=f"{prefix}_date")
    selected_time = time_column.time_input("Created time", initial.time(), key=f"{prefix}_time")
    return datetime.combine(selected_date, selected_time).isoformat()


def _product_payload(prefix: str, row: dict | None = None) -> dict:
    return {
        "created_at": _timestamp(prefix, row.get("created_at") if row else None),
        "product_name": st.text_input("Product name", value=row.get("product_name", "") if row else "", key=f"{prefix}_name"),
    }


BUILDERS = {
    "products": _product_payload,
}


def _order_customer_label(row: dict, role: str | None) -> str:
    """Return an origin-aware, role-safe customer label without exposing PII."""
    if row.get("origin") == "imported":
        dataset_user_id = row.get("user_id")
        return f"Historical Shopper #{dataset_user_id}" if dataset_user_id is not None else "Historical shopper"
    if row.get("origin") == "customer":
        customer_id = row.get("customer_account_id")
        # A pseudonymous account identifier is appropriate for every staff role,
        # including the deliberately deidentified Analyst projection.
        return f"Customer #{customer_id}" if customer_id is not None else "Registered customer"
    customer_id = row.get("customer_account_id")
    if customer_id is not None:
        return f"Customer #{customer_id}"
    dataset_user_id = row.get("user_id")
    return f"Historical Shopper #{dataset_user_id}" if dataset_user_id is not None else "Application-created order"


def _not_applicable(value) -> str | int:
    return "Not applicable" if value is None else value


def _display_identifier(value) -> str:
    return "Not applicable" if value is None else str(value)


def _order_table_rows(rows: list[dict], role: str | None) -> list[dict]:
    """Create the presentation projection used by the staff Orders table."""
    projected = []
    for row in rows:
        customer_origin = row.get("origin") == "customer"
        status_label = "Historical record" if row.get("origin") == "imported" else format_status(row.get("order_status"))
        if role == "analyst":
            item = {
                "Order #": row["order_id"],
                "Customer": _order_customer_label(row, role),
                "Date": format_datetime(row.get("created_at")),
                "Total": format_money(row.get("price_usd")),
                "Status": status_label,
                "Source": source_label(row),
            }
        else:
            item = {
                "order_id": row["order_id"],
                "created_at": row.get("created_at"),
                "Customer": _order_customer_label(row, role),
                "Website Session": "Not applicable" if customer_origin else _display_identifier(row.get("website_session_id")),
                "Primary Product": _display_identifier(row.get("primary_product_id")),
                "Items": row.get("items_purchased", 0),
                "price_usd": row.get("price_usd"),
                "cogs_usd": row.get("cogs_usd"),
                "Status": status_label,
                "origin": row.get("origin"),
            }
        projected.append(item)
    return projected


def _refund_table_rows(rows: list[dict], role: str | None) -> list[dict]:
    if role in {"admin", "operations_staff"}:
        return [{
            "Refund #": row["order_item_refund_id"],
            "Order #": row["order_id"],
            "Product": row.get("product_name") or "Related order item",
            "Amount": format_money(row["refund_amount_usd"]),
            "Date": format_datetime(row.get("created_at")),
            "Source": source_label(row),
        } for row in rows]
    if role != "analyst":
        return rows
    return [{
        "Refund #": row["order_item_refund_id"],
        "Order #": row["order_id"],
        "Amount": format_money(row["refund_amount_usd"]),
        "Date": format_datetime(row.get("created_at")),
        "Source": source_label(row),
    } for row in rows]


def _analyst_product_rows(products: list[dict], performance: list[dict]) -> list[dict]:
    metrics = {row["product_id"]: row for row in performance}
    projected = []
    for product in products:
        row = metrics.get(product["product_id"], {})
        revenue = Decimal(str(row.get("revenue", 0)))
        cogs = Decimal(str(row.get("cogs", 0)))
        projected.append({
            "Product": product["product_name"],
            "Revenue": format_money(revenue),
            "Orders": int(row.get("orders", 0)),
            "Units": int(row.get("units", 0)),
            "Gross profit": format_money(revenue - cogs),
            "Refunds": format_money(row.get("refunds", 0)),
            "Source": source_label(product),
        })
    return projected


def _render_analyst_products(client: APIClient) -> None:
    data_page_header(
        "Products",
        "Compare combined historical and application sales in a read-only view. Source identifies where each product record originated.",
        "products",
    )
    source_legend(("imported", "web"))
    section_label("Product performance")
    filters = st.columns([2, 1, 1])
    search = filters[0].text_input("Search products", key="products_search")
    origin = filters[1].selectbox(
        "Source",
        ["all", "imported", "web"],
        format_func=lambda value: {
            "all": "All sources",
            "imported": "Historical data",
            "web": "Application-created",
        }[value],
        key="products_origin",
    )
    limit = filters[2].selectbox("Rows per page", [10, 25, 50, 100], index=1, key="products_limit")
    offset = st.session_state.setdefault("products_offset", 0)
    params = {"origin": origin, "limit": limit, "offset": offset}
    if search:
        params["search"] = search
    try:
        products = client.get("/products", params)
        report = client.get("/analytics/dashboard", {"scope": "combined"})
        display_rows(_analyst_product_rows(products["items"], report["products"]), "Product")
        pagination_controls("products", products["total"], limit)
        st.info("Product performance is read-only for Analyst.")
    except APIError as exc:
        show_api_error(exc)


def _operations_product_rows(rows: list[dict]) -> list[dict]:
    return [{
        "Product": row["product_name"],
        "Created": format_datetime(row.get("created_at")),
        "Source": source_label(row),
    } for row in rows]


def _admin_product_rows(rows: list[dict], catalog: list[dict]) -> list[dict]:
    catalog_by_product = {row["product_id"]: row for row in catalog}
    projected = []
    for row in rows:
        catalog_row = catalog_by_product.get(row["product_id"])
        if catalog_row is None or not catalog_row.get("is_configured"):
            storefront_status = "Not configured"
        else:
            storefront_status = "Available" if catalog_row.get("is_available") else "Unavailable"
        projected.append({
            "Product": row["product_name"],
            "Created": format_datetime(row.get("created_at")),
            "Source": source_label(row),
            "Storefront status": storefront_status,
        })
    return projected


def _operations_historical_order_rows(rows: list[dict]) -> list[dict]:
    return [{
        "Order #": row["order_id"],
        "Shopper": _order_customer_label(row, "operations_staff"),
        "Date": format_datetime(row.get("created_at")),
        "Items": row.get("items_purchased", 0),
        "Total": format_money(row.get("price_usd")),
    } for row in rows]


def _render_commerce_orders(client: APIClient, role: str) -> None:
    data_page_header(
        "Orders",
        "Oversee customer orders and consult historical purchases when needed."
        if role == "admin"
        else "Process customer orders and consult historical purchases when needed.",
        "orders",
    )
    order_workflow.render(client)
    st.divider()
    with st.expander("Historical order reference", expanded=False):
        st.caption("Past imported purchases are available here for read-only reference.")
        limit = st.selectbox("Rows per page", [10, 25, 50, 100], index=1, key="operations_historical_orders_limit")
        offset = st.session_state.setdefault("operations_historical_orders_offset", 0)
        try:
            result = client.get("/orders", {"origin": "imported", "limit": limit, "offset": offset})
            display_rows(_operations_historical_order_rows(result["items"]), "Order #")
            pagination_controls("operations_historical_orders", result["total"], limit)
            _render_order_details(result["items"], role)
        except APIError as exc:
            show_api_error(exc)


def _render_order_details(rows: list[dict], role: str | None) -> None:
    if not rows:
        return
    st.divider()
    section_label("Order details")
    selected_id = st.selectbox(
        "Order to inspect",
        [row["order_id"] for row in rows],
        format_func=lambda value: f"Order #{value}",
        key="orders_detail_selected",
    )
    order = next(row for row in rows if row["order_id"] == selected_id)
    customer_origin = order.get("origin") == "customer"
    with st.container(border=True):
        st.subheader(f"Order #{selected_id}")
        st.caption(f"Placed {format_datetime(order.get('created_at'))} · {source_label(order)}")
        if role == "analyst":
            customer, total, status = st.columns(3)
            customer.markdown(f"**Customer**  \n{_order_customer_label(order, role)}")
            total.markdown(f"**Total**  \n{format_money(order.get('price_usd'))}")
            status_value = "Historical record" if order.get("origin") == "imported" else format_status(order.get("order_status"))
            status.markdown(f"**Status**  \n{status_value}")
            return
        customer, session, dataset_user = st.columns(3)
        customer.markdown(f"**Customer**  \n{_order_customer_label(order, role)}")
        session_value = "Not applicable" if customer_origin else _not_applicable(order.get("website_session_id"))
        session.markdown(f"**Website Session**  \n{session_value}")
        dataset_value = "Not applicable" if customer_origin else _not_applicable(order.get("user_id"))
        dataset_user.markdown(f"**Dataset User ID**  \n{dataset_value}")
        product, items, status = st.columns(3)
        product.markdown(f"**Primary Product**  \n{_not_applicable(order.get('primary_product_id'))}")
        items.markdown(f"**Items Purchased**  \n{order.get('items_purchased', 0)}")
        status_value = "Not applicable · historical record" if order.get("origin") == "imported" else format_status(order.get("order_status"))
        status.markdown(f"**Order Status**  \n{status_value}")


def render(client: APIClient, entity: str) -> None:
    title, path, id_column = PATHS[entity]
    role = current_role()
    if role in {"admin", "operations_staff"} and entity == "orders":
        _render_commerce_orders(client, role)
        return
    if role == "analyst" and entity == "products":
        _render_analyst_products(client)
        return
    if entity == "orders":
        caption = "Compare historical purchases and customer orders in a read-only business view."
    elif entity == "refunds":
        caption = "Read imported and processed refund records. Actual customer refunds are created only through Refund Requests."
    elif entity == "products" and role == "operations_staff":
        caption = "Use the product list as a read-only reference for customer support and order handling."
    elif entity == "products" and role == "admin":
        caption = "Manage application products while keeping historical products protected."
    else:
        caption = (
            "Browse historical and application-created records. "
            + ("Admin may manage application-created product records." if can_mutate(entity, role) else "Your role has read-only access.")
        )
    data_page_header(title, caption, entity)
    source_legend(("imported", "web") if entity == "products" else ("imported", "web", "customer"))
    if entity == "orders":
        section_label("Order activity")
    else:
        section_label("Browse and filter")
    with st.container(border=True):
        filter_columns = st.columns([2, 1, 1]) if entity == "products" else st.columns(2)
        if entity == "products":
            search = filter_columns[0].text_input("Search products", key=f"{entity}_search")
            source_column, limit_column = filter_columns[1], filter_columns[2]
        else:
            search = None
            source_column, limit_column = filter_columns
        origin_options = ["all", "imported", "web"]
        if entity in {"orders", "order_items", "refunds"}:
            origin_options.append("customer")
        origin = source_column.selectbox(
            "Source",
            origin_options,
            format_func=lambda value: {
                "all": "All sources",
                "imported": "Historical data",
                "web": "Application-created",
                "customer": "Customer-created",
            }[value],
            key=f"{entity}_origin",
        )
        limit = limit_column.selectbox(
            "Rows per page",
            [10, 25, 50, 100],
            index=1,
            key=f"{entity}_limit",
        )
    offset = st.session_state.setdefault(f"{entity}_offset", 0)
    params = {"origin": origin, "limit": limit, "offset": offset}
    if search:
        params["search"] = search
    try:
        result = client.get(path, params)
        rows = result["items"]
        if entity == "orders":
            displayed_rows = _order_table_rows(rows, role)
        elif entity == "refunds":
            displayed_rows = _refund_table_rows(rows, role)
        elif entity == "products" and role == "operations_staff":
            displayed_rows = _operations_product_rows(rows)
        elif entity == "products" and role == "admin":
            catalog = client.get("/admin/catalog")
            displayed_rows = _admin_product_rows(rows, catalog)
        else:
            displayed_rows = rows
        if entity == "refunds" and role in {"admin", "operations_staff"}:
            display_id = "Refund #"
        elif entity == "refunds" and role == "analyst":
            display_id = "Refund #"
        elif entity == "orders" and role == "analyst":
            display_id = "Order #"
        elif entity == "products" and role == "operations_staff":
            display_id = "Product"
        elif entity == "products" and role == "admin":
            display_id = "Product"
        else:
            display_id = id_column
        display_rows(displayed_rows, display_id)
        pagination_controls(entity, result["total"], limit)

        if entity == "orders":
            _render_order_details(rows, role)

        # Generic form CRUD is intentionally restricted to product master data.
        # Transaction records use their validated order/refund workflows even if
        # a future role-permission change accidentally broadens can_mutate().
        if entity not in BUILDERS or not can_mutate(entity, role):
            if entity == "orders":
                st.info("Order information is read-only for Analyst.")
            elif entity == "refunds":
                st.info("Refund history is read-only for Analyst.")
            elif entity == "products" and role == "operations_staff":
                st.info("Product information is read-only for Operations Staff.")
            else:
                st.info("Your role has read-only access to this entity.")
            return
        st.divider()
        section_label("Application record controls")
        create_tab, manage_tab = st.tabs(["Create Product", "Manage Products"])
        builder = BUILDERS[entity]
        with create_tab:
            st.subheader("Create application product")
            st.caption("Historical products remain protected and are never changed by this form.")
            with st.form(f"{entity}_create"):
                payload = builder(client, f"{entity}_create") if entity != "products" else builder(f"{entity}_create")
                submitted = st.form_submit_button(
                    f"Create {title[:-1]}",
                    type="primary",
                    use_container_width=True,
                )
            if submitted and payload is not None:
                try:
                    client.post(path, payload)
                    st.success("Record created.")
                    st.rerun()
                except APIError as exc:
                    show_api_error(exc)
        with manage_tab:
            st.subheader("Manage application-created products")
            web_rows = [row for row in result["items"] if row.get("origin") == "web"]
            if not web_rows:
                st.info("This page contains no application-created records available to modify.")
                return
            selected_id = st.selectbox("Application-created record", [row[id_column] for row in web_rows], key=f"{entity}_selected")
            selected = next(row for row in web_rows if row[id_column] == selected_id)
            st.caption("Historical products are protected and never appear in these controls.")
            with st.form(f"{entity}_update"):
                payload = builder(client, f"{entity}_update", selected) if entity != "products" else builder(f"{entity}_update", selected)
                update = st.form_submit_button("Save changes", type="primary", use_container_width=True)
            if update and payload is not None:
                payload["row_version"] = selected["row_version"]
                try:
                    client.put(f"{path}/{selected_id}", payload)
                    st.success("Record updated.")
                    st.rerun()
                except APIError as exc:
                    show_api_error(exc)
            st.warning("Delete is permanent for this application-created record.")
            delete_column, _ = st.columns([1, 2.5])
            if delete_column.button("Delete record", key=f"{entity}_delete", use_container_width=True):
                try:
                    client.delete(f"{path}/{selected_id}", {"row_version": selected["row_version"]})
                    st.success("Record deleted.")
                    st.rerun()
                except APIError as exc:
                    show_api_error(exc)
    except APIError as exc:
        show_api_error(exc)
