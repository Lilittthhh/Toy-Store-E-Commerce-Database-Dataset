from __future__ import annotations

from decimal import Decimal

import streamlit as st

from frontend.api_client import APIClient, APIError
from frontend.auth import current_role
from frontend.ui import data_page_header, display_rows, format_money, show_api_error


def render(client: APIClient) -> None:
    role = current_role()
    caption = (
        "Review store prices, availability, and customer-facing product information."
        if role == "operations_staff"
        else "Manage the product information shown in the customer storefront."
    )
    data_page_header("Storefront Catalog", caption, "catalog")
    try:
        products = client.get("/admin/catalog")
    except APIError as exc:
        show_api_error(exc)
        return
    if not products:
        st.info("No products are available.")
        return
    if role == "operations_staff":
        st.info("Storefront configuration is read-only for Operations Staff.")
    table = [{
        "Product": product["product_name"],
        "Store price": format_money(product.get("current_price_usd")),
        "COGS": format_money(product.get("current_cogs_usd")),
        "Availability": "Available" if product.get("is_available") else "Unavailable",
        "Description": product.get("description") or "No description available.",
        "Catalog status": "Configured" if product.get("is_configured") else "Not configured",
    } for product in products]
    display_rows(table, "Product")
    if role != "admin":
        return

    selected_id = st.selectbox(
        "Product to configure",
        [product["product_id"] for product in products],
        format_func=lambda value: next(product["product_name"] for product in products if product["product_id"] == value),
    )
    product = next(product for product in products if product["product_id"] == selected_id)
    with st.expander("Configure storefront details"):
        with st.form(f"catalog_{product['product_id']}"):
            description = st.text_area(
                "Description", value=product.get("description") or "", max_chars=4000, height=100
            )
            first, second = st.columns(2)
            price_value = first.number_input("Store price (USD)", min_value=0.01, value=float(product.get("current_price_usd") or 0.01), step=0.01, format="%.2f")
            cogs_value = second.number_input("COGS (USD)", min_value=0.0, value=float(product.get("current_cogs_usd") or 0), step=0.01, format="%.2f")
            image_url = st.text_input("Product image URL (optional)", value=product.get("image_url") or "")
            available = st.checkbox("Available in customer storefront", value=bool(product.get("is_available")))
            save = st.form_submit_button("Save catalog configuration", type="primary", use_container_width=True)
        if save:
            payload = {
                "description": description,
                "current_price_usd": str(Decimal(str(price_value)).quantize(Decimal("0.01"))),
                "current_cogs_usd": str(Decimal(str(cogs_value)).quantize(Decimal("0.01"))),
                "image_url": image_url or None,
                "is_available": available,
                "row_version": product.get("row_version"),
            }
            try:
                client.put(f"/admin/catalog/{product['product_id']}", payload)
                st.success("Catalog configuration saved.")
                st.rerun()
            except APIError as exc:
                show_api_error(exc)
