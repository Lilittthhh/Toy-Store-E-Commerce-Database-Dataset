from __future__ import annotations

import streamlit as st

from frontend.api_client import APIClient, APIError
from frontend.ui import format_datetime, section_label, show_api_error


def _address_form(key: str, current: dict | None = None) -> tuple[bool, dict]:
    value = current or {}
    with st.form(key):
        label = st.text_input("Label", value=value.get("label", "Home"))
        first, last = st.columns(2)
        recipient_first_name = first.text_input("Recipient first name", value=value.get("recipient_first_name", ""))
        recipient_last_name = last.text_input("Recipient last name", value=value.get("recipient_last_name", ""))
        phone = st.text_input("Recipient phone (optional)", value=value.get("phone") or "")
        address_line_1 = st.text_input("Address line 1", value=value.get("address_line_1", ""))
        address_line_2 = st.text_input("Address line 2 (optional)", value=value.get("address_line_2") or "")
        city_col, province_col = st.columns(2)
        city = city_col.text_input("City", value=value.get("city", ""))
        province_region = province_col.text_input("Province / region", value=value.get("province_region", ""))
        postal_col, country_col = st.columns(2)
        postal_code = postal_col.text_input("Postal code", value=value.get("postal_code", ""))
        country_code = country_col.text_input("Country code", value=value.get("country_code", "PH"), max_chars=2)
        if current is None:
            is_default = st.checkbox("Make this my default address")
        else:
            is_default = False
        submitted = st.form_submit_button("Add address" if current is None else "Save address", type="primary", use_container_width=True)
    payload = {
        "label": label, "recipient_first_name": recipient_first_name,
        "recipient_last_name": recipient_last_name, "phone": phone or None,
        "address_line_1": address_line_1, "address_line_2": address_line_2 or None,
        "city": city, "province_region": province_region, "postal_code": postal_code,
        "country_code": country_code,
    }
    if current is None:
        payload["is_default"] = is_default
    else:
        payload["row_version"] = current["row_version"]
    return submitted, payload


def render_addresses(client: APIClient) -> None:
    section_label("Saved shipping addresses")
    st.caption("Only you can view or manage these saved addresses. Shipping details are saved with each order.")
    try:
        addresses = client.get("/customer/addresses")
    except APIError as exc:
        show_api_error(exc)
        return

    with st.expander("+ Add Address", expanded=not addresses):
        submitted, payload = _address_form("add_customer_address")
        if submitted:
            try:
                client.post("/customer/addresses", payload)
                st.success("Address added.")
                st.rerun()
            except APIError as exc:
                show_api_error(exc)
    if not addresses:
        st.info("No saved addresses yet.")
    for address in addresses:
        status = "Default" if address["is_default"] else ("Active" if address["is_active"] else "Inactive")
        with st.container(border=True):
            st.markdown('<span class="rm-account-card-marker"></span>', unsafe_allow_html=True)
            top, badge = st.columns([5, 1])
            top.markdown(f"**{address['label']}** — {address['recipient_first_name']} {address['recipient_last_name']}")
            badge.markdown(f"**{status}**")
            st.write(f"{address['address_line_1']}{', ' + address['address_line_2'] if address.get('address_line_2') else ''}")
            st.caption(f"{address['city']}, {address['province_region']} {address['postal_code']} · {address['country_code']} · Updated {format_datetime(address['updated_at'])}")
            if address["is_active"]:
                edit_col, default_col, deactivate_col = st.columns([1, 1, 1])
                with edit_col.expander("Edit"):
                    submitted, payload = _address_form(f"edit_customer_address_{address['customer_address_id']}", address)
                    if submitted:
                        try:
                            client.put(f"/customer/addresses/{address['customer_address_id']}", payload)
                            st.success("Address updated.")
                            st.rerun()
                        except APIError as exc:
                            show_api_error(exc)
                if default_col.button("Set Default", key=f"address_default_{address['customer_address_id']}", disabled=address["is_default"], use_container_width=True):
                    try:
                        client.post(f"/customer/addresses/{address['customer_address_id']}/set-default", {"row_version": address["row_version"]})
                        st.success("Default address updated.")
                        st.rerun()
                    except APIError as exc:
                        show_api_error(exc)
                if deactivate_col.button("Deactivate", key=f"address_deactivate_{address['customer_address_id']}", use_container_width=True):
                    try:
                        client.post(f"/customer/addresses/{address['customer_address_id']}/deactivate", {"row_version": address["row_version"]})
                        st.success("Address deactivated.")
                        st.rerun()
                    except APIError as exc:
                        show_api_error(exc)


def _payment_form(key: str, current: dict | None = None) -> tuple[bool, dict]:
    value = current or {}
    labels = {"card": "Simulated Card", "gcash": "GCash", "paypal": "PayPal", "cash_on_delivery": "Cash on Delivery"}
    reverse = {label: method for method, label in labels.items()}
    options = list(reverse)
    current_label = labels.get(value.get("method_type", "card"), options[0])
    with st.form(key):
        selected = st.selectbox("Method type", options, index=options.index(current_label))
        method_type = reverse[selected]
        if method_type == "card":
            st.info("Demo metadata only. Never enter a full card number, CVV, expiry date, or real banking credentials.")
            card_brand = st.text_input("Simulated card brand", value=value.get("card_brand") or "Visa")
            card_last_four = st.text_input("Demo last four digits", value=value.get("card_last_four") or "", max_chars=4)
        else:
            st.caption("No account number, email, mobile number, OTP, password, or gateway credential is requested.")
            card_brand = None
            card_last_four = None
        if current is None:
            is_default = st.checkbox("Make this my default payment method")
        else:
            is_default = False
        submitted = st.form_submit_button("Add simulated method" if current is None else "Save safe metadata", type="primary", use_container_width=True)
    payload = {"method_type": method_type, "card_brand": card_brand, "card_last_four": card_last_four}
    if current is None:
        payload["is_default"] = is_default
    else:
        payload["row_version"] = current["row_version"]
    return submitted, payload


def render_payment_methods(client: APIClient) -> None:
    section_label("Saved payment methods")
    st.warning("Classroom simulation only — no real payment details or financial credentials are used or stored.")
    try:
        methods = client.get("/customer/payment-methods")
    except APIError as exc:
        show_api_error(exc)
        return

    with st.expander("+ Add Simulated Payment Method", expanded=not methods):
        submitted, payload = _payment_form("add_customer_payment")
        if submitted:
            try:
                client.post("/customer/payment-methods", payload)
                st.success("Simulated payment method added.")
                st.rerun()
            except APIError as exc:
                show_api_error(exc)
    if not methods:
        st.info("No simulated payment methods saved yet.")
    for method in methods:
        status = "Default" if method["is_default"] else ("Active" if method["is_active"] else "Inactive")
        with st.container(border=True):
            st.markdown('<span class="rm-account-card-marker"></span>', unsafe_allow_html=True)
            label_col, status_col = st.columns([5, 1])
            label_col.markdown(f"**{method['display_label']}**")
            status_col.markdown(f"**{status}**")
            st.caption(f"Updated {format_datetime(method['updated_at'])}")
            if method["is_active"]:
                edit_col, default_col, deactivate_col = st.columns([1, 1, 1])
                with edit_col.expander("Edit"):
                    submitted, payload = _payment_form(f"edit_customer_payment_{method['payment_method_id']}", method)
                    if submitted:
                        try:
                            client.put(f"/customer/payment-methods/{method['payment_method_id']}", payload)
                            st.success("Payment method updated.")
                            st.rerun()
                        except APIError as exc:
                            show_api_error(exc)
                if default_col.button("Set Default", key=f"payment_default_{method['payment_method_id']}", disabled=method["is_default"], use_container_width=True):
                    try:
                        client.post(f"/customer/payment-methods/{method['payment_method_id']}/set-default", {"row_version": method["row_version"]})
                        st.success("Default payment method updated.")
                        st.rerun()
                    except APIError as exc:
                        show_api_error(exc)
                if deactivate_col.button("Deactivate", key=f"payment_deactivate_{method['payment_method_id']}", use_container_width=True):
                    try:
                        client.post(f"/customer/payment-methods/{method['payment_method_id']}/deactivate", {"row_version": method["row_version"]})
                        st.success("Payment method deactivated.")
                        st.rerun()
                    except APIError as exc:
                        show_api_error(exc)
