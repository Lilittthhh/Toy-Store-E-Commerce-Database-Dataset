from __future__ import annotations

from html import escape

import streamlit as st

from frontend.api_client import APIClient, APIError
from frontend.customer_auth import customer_sign_out
from frontend.ui import format_datetime, section_label, show_api_error
from frontend.views.customer_resources import render_addresses, render_payment_methods


def render(client: APIClient, customer: dict) -> None:
    try:
        profile = client.get("/customer/profile")
    except APIError as exc:
        show_api_error(exc)
        return
    st.title("My Account")
    st.markdown(
        f"""
        <section class="rm-account-hero">
          <div>
            <span class="rm-account-eyebrow">Customer account</span>
            <h1>{escape(profile['first_name'])} {escape(profile['last_name'])}</h1>
            <p>{escape(customer['email'])}</p>
          </div>
          <dl>
            <div><dt>Member since</dt><dd>{escape(format_datetime(customer['created_at']).split(' · ')[0])}</dd></div>
            <div><dt>Account</dt><dd>{'Active' if customer['is_active'] else 'Inactive'}</dd></div>
          </dl>
        </section>
        """,
        unsafe_allow_html=True,
    )
    st.caption("Manage your profile, delivery information, simulated payment methods, and account security.")

    profile_tab, addresses_tab, payments_tab, security_tab = st.tabs(
        ["Profile", "Addresses", "Payment Methods", "Security"]
    )
    with profile_tab:
        section_label("Personal details")
        _, profile_content, _ = st.columns([.55, 2.4, .55])
        with profile_content:
            with st.form("customer_profile_form"):
                first_name = st.text_input("First name", value=profile["first_name"])
                last_name = st.text_input("Last name", value=profile["last_name"])
                phone = st.text_input("Phone (optional)", value=profile.get("phone") or "")
                submitted = st.form_submit_button("Save profile", type="primary", use_container_width=True)
        if submitted:
            try:
                profile = client.put("/customer/profile", {
                    "first_name": first_name, "last_name": last_name, "phone": phone or None,
                    "row_version": profile["row_version"],
                })
                st.session_state.current_customer.update({
                    "first_name": profile["first_name"], "last_name": profile["last_name"],
                    "phone": profile["phone"], "profile_row_version": profile["row_version"],
                })
                st.success("Profile updated.")
                st.rerun()
            except APIError as exc:
                show_api_error(exc)
    with addresses_tab:
        render_addresses(client)
    with payments_tab:
        render_payment_methods(client)
    with security_tab:
        section_label("Change password")
        st.caption("Changing your password signs your account out on every device.")
        _, security_content, _ = st.columns([.55, 2.4, .55])
        with security_content:
            with st.form("customer_change_password_form"):
                current = st.text_input("Current password", type="password")
                new = st.text_input("New password", type="password")
                confirmation = st.text_input("Confirm new password", type="password")
                submitted = st.form_submit_button("Change password", type="primary", use_container_width=True)
        if submitted:
            if new != confirmation:
                st.error("New passwords do not match.")
                return
            try:
                result = client.post("/customer/auth/change-password", {"current_password": current, "new_password": new})
                st.success(result["message"] + " Please sign in again.")
                customer_sign_out()
                st.rerun()
            except APIError as exc:
                show_api_error(exc)
