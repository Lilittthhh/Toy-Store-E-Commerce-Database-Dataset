from __future__ import annotations

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
    heading, membership = st.columns([4.5, 1.15], vertical_alignment="bottom")
    with heading:
        st.title("My Account")
        st.caption("Review your profile, manage saved information, and keep your account secure.")
    membership.metric("Member since", format_datetime(customer["created_at"]).split(" · ")[0])
    with st.container(border=True):
        st.markdown('<span class="rm-account-card-marker"></span>', unsafe_allow_html=True)
        identity, email, status = st.columns([1.4, 2.3, 1])
        identity.markdown(f"**Name**  \n{profile['first_name']} {profile['last_name']}")
        email.markdown(f"**Email address**  \n{customer['email']}")
        status.markdown(f"**Status**  \n{'Active' if customer['is_active'] else 'Inactive'}")
        st.caption("Your email address is used to sign in and is managed separately from your profile.")

    profile_tab, addresses_tab, payments_tab, security_tab = st.tabs(
        ["Profile", "Addresses", "Payment Methods", "Security"]
    )
    with profile_tab:
        section_label("Personal details")
        profile_content, _ = st.columns([2.3, 1])
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
        security_content, _ = st.columns([2.3, 1])
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
