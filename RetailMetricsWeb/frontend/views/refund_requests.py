from __future__ import annotations

import streamlit as st

from frontend.api_client import APIClient, APIError
from frontend.auth import current_role
from frontend.ui import data_page_header, display_rows, format_datetime, format_money, format_status, pagination_controls, show_api_error


def render(client: APIClient) -> None:
    role = current_role()
    may_review = role in {"admin", "operations_staff"}
    data_page_header(
        "Refund Requests",
        "Review customer requests and process approved simulated refunds.",
        "refund_requests",
    )
    queue = st.selectbox(
        "Queue",
        ["all", "pending", "approved", "rejected", "processed"],
        format_func=lambda value: "All requests" if value == "all" else value.title(),
        key="refund_request_queue",
    )
    limit = st.selectbox("Rows per page", [10, 25, 50, 100], index=1, key="refund_request_limit")
    offset = st.session_state.setdefault("refund_requests_offset", 0)
    params = {"limit": limit, "offset": offset}
    if queue != "all":
        params["status_filter"] = queue
    try:
        result = client.get("/refund-requests", params)
        display_rows([{
            "Request #": row["refund_request_id"],
            "Order #": row["order_id"],
            "Product": row["product_name"],
            "Amount": format_money(row["requested_amount"]),
            "Reason": row["reason"],
            "Status": format_status(row["status"]),
            "Requested": format_datetime(row["created_at"]),
            "Outcome": row.get("resolution_note") or "—",
        } for row in result["items"]], "Request #")
        pagination_controls("refund_requests", result["total"], limit)
    except APIError as exc:
        show_api_error(exc)
        return
    if not may_review:
        st.info("Analyst access is read-only. Approval, rejection, and processing are available only to Admin and Operations Staff.")
        return
    actionable = [row for row in result["items"] if row["status"] in {"pending", "approved"}]
    if not actionable:
        st.info("This page contains no requests awaiting a staff action.")
        return
    st.divider()
    selected_id = st.selectbox(
        "Request to review",
        [row["refund_request_id"] for row in actionable],
        format_func=lambda value: f"Request #{value}",
        key="refund_request_selected",
    )
    selected = next(row for row in actionable if row["refund_request_id"] == selected_id)
    action_panel, _ = st.columns([2.2, 1])
    with action_panel:
        with st.container(border=True):
            st.subheader(f"Refund Request #{selected_id}")
            st.caption(format_status(selected["status"]))
            customer, order = st.columns(2)
            customer.markdown(f"**Customer**  \nLinked to Order #{selected['order_id']}")
            order.markdown(f"**Order**  \n#{selected['order_id']}")
            st.markdown(f"**Product**  \n{selected['product_name']}")
            st.markdown(f"**Requested amount**  \n{format_money(selected['requested_amount'])}")
            st.markdown(f"**Reason**  \n{selected['reason']}")
            if selected["status"] == "pending":
                note = st.text_input("Approval note (optional)", key=f"approve_note_{selected_id}")
                approve, reject = st.columns(2)
                if approve.button("Approve", type="primary", use_container_width=True):
                    try:
                        client.post(f"/refund-requests/{selected_id}/approve", {
                            "row_version": selected["row_version"],
                            "resolution_note": note.strip() or None,
                        })
                        st.success("Refund request approved.")
                        st.rerun()
                    except APIError as exc:
                        show_api_error(exc)
                with reject:
                    with st.form(f"reject_request_{selected_id}"):
                        rejection_note = st.text_area("Rejection reason", height=80)
                        rejected = st.form_submit_button("Reject", use_container_width=True)
                    if rejected:
                        try:
                            client.post(f"/refund-requests/{selected_id}/reject", {
                                "row_version": selected["row_version"],
                                "resolution_note": rejection_note,
                            })
                            st.success("Refund request rejected.")
                            st.rerun()
                        except APIError as exc:
                            show_api_error(exc)
            else:
                st.info("Processing records the refund and updates the simulated payment status.")
                if st.button("Process Refund", type="primary", key=f"process_request_{selected_id}"):
                    try:
                        client.post(f"/refund-requests/{selected_id}/process", {"row_version": selected["row_version"]})
                        st.success("Refund processed successfully.")
                        st.rerun()
                    except APIError as exc:
                        show_api_error(exc)
