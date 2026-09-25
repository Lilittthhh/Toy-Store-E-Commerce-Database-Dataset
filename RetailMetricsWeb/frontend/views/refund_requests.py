from __future__ import annotations

import streamlit as st

from frontend.api_client import APIClient, APIError
from frontend.auth import current_role
from frontend.ui import data_page_header, display_rows, format_datetime, format_money, format_status, pagination_controls, show_api_error
from frontend.views.entity_views import _refund_table_rows


def _request_rows(items: list[dict]) -> list[dict]:
    return [{
        "Request #": row["refund_request_id"],
        "Order #": row["order_id"],
        "Product": row["product_name"],
        "Amount": format_money(row["requested_amount"]),
        "Reason": row["reason"],
        "Status": format_status(row["status"]),
        "Requested": format_datetime(row["created_at"]),
        "Outcome": row.get("resolution_note") or "—",
    } for row in items]


def _render_refund_action(client: APIClient, selected: dict) -> None:
    request_id = selected["refund_request_id"]
    with st.container(border=True):
        st.subheader(f"Next: Refund Request #{request_id}")
        st.caption(
            f"Requested {format_datetime(selected['created_at'])} · {format_status(selected['status'])}"
        )
        customer, order = st.columns(2)
        customer.markdown(f"**Product**  \n{selected['product_name']}")
        order.markdown(f"**Order**  \n#{selected['order_id']}")
        st.markdown(f"**Requested amount**  \n{format_money(selected['requested_amount'])}")
        st.markdown(f"**Reason**  \n{selected['reason']}")
        if selected["status"] == "pending":
            note = st.text_input("Approval note (optional)", key=f"approve_note_{request_id}")
            approve, reject = st.columns(2)
            if approve.button("Approve", type="primary", use_container_width=True, key=f"approve_{request_id}"):
                try:
                    client.post(f"/refund-requests/{request_id}/approve", {
                        "row_version": selected["row_version"],
                        "resolution_note": note.strip() or None,
                    })
                    st.success("Refund request approved.")
                    st.rerun()
                except APIError as exc:
                    show_api_error(exc)
            with reject:
                with st.form(f"reject_request_{request_id}"):
                    rejection_note = st.text_area("Rejection reason", height=80)
                    rejected = st.form_submit_button("Reject", use_container_width=True)
                if rejected:
                    try:
                        client.post(f"/refund-requests/{request_id}/reject", {
                            "row_version": selected["row_version"],
                            "resolution_note": rejection_note,
                        })
                        st.success("Refund request rejected.")
                        st.rerun()
                    except APIError as exc:
                        show_api_error(exc)
        else:
            st.info("Processing records the refund and updates the simulated payment status.")
            if st.button("Process Refund", type="primary", key=f"process_request_{request_id}"):
                try:
                    client.post(f"/refund-requests/{request_id}/process", {"row_version": selected["row_version"]})
                    st.success("Refund processed successfully.")
                    st.rerun()
                except APIError as exc:
                    show_api_error(exc)


def render(client: APIClient) -> None:
    role = current_role()
    may_review = role in {"admin", "operations_staff"}
    data_page_header(
        "Refund Requests",
        "Review the oldest outstanding customer request first, then browse the complete request history.",
        "refund_requests",
    )

    st.subheader("Requests awaiting action")
    st.caption("Pending and approved requests are ordered from oldest to newest.")
    action_limit = 25
    action_offset = st.session_state.setdefault("refund_action_offset", 0)
    try:
        action_result = client.get(
            "/refund-requests",
            {"actionable_only": True, "limit": action_limit, "offset": action_offset},
        )
    except APIError as exc:
        show_api_error(exc)
        return

    actionable = sorted(
        (row for row in action_result["items"] if row["status"] in {"pending", "approved"}),
        key=lambda row: (str(row.get("created_at") or ""), row["refund_request_id"]),
    )
    if actionable:
        selected_id = st.selectbox(
            "Request to review",
            [row["refund_request_id"] for row in actionable],
            format_func=lambda value: next(
                f"Request #{row['refund_request_id']} · {format_datetime(row['created_at'])}"
                for row in actionable
                if row["refund_request_id"] == value
            ),
            key="refund_request_selected",
        )
        selected = next(row for row in actionable if row["refund_request_id"] == selected_id)
        if may_review:
            _render_refund_action(client, selected)
        else:
            st.info("Analyst access is read-only. Approval, rejection, and processing are available only to Admin and Operations Staff.")

        st.markdown("**Full action queue · oldest first**")
        display_rows(_request_rows(actionable), "Request #")
        pagination_controls("refund_action", action_result["total"], action_limit)
    else:
        st.success("The refund request queue is clear.")

    st.divider()
    with st.expander("All refund history and records", expanded=False):
        st.caption("Open this section to browse completed request history and the full refund record table.")
        st.subheader("Request history")
        history_filters, history_size = st.columns([2, 1])
        queue = history_filters.selectbox(
            "History filter",
            ["all", "pending", "approved", "rejected", "processed"],
            format_func=lambda value: "All requests" if value == "all" else value.title(),
            key="refund_request_queue",
        )
        limit = history_size.selectbox("Request rows per page", [10, 25, 50, 100], index=1, key="refund_request_limit")
        offset = st.session_state.setdefault("refund_requests_offset", 0)
        params = {"limit": limit, "offset": offset}
        if queue != "all":
            params["status_filter"] = queue
        try:
            result = client.get("/refund-requests", params)
            display_rows(_request_rows(result["items"]), "Request #")
            pagination_controls("refund_requests", result["total"], limit)
        except APIError as exc:
            show_api_error(exc)

        st.divider()
        st.subheader("Complete refund records")
        record_filters, record_size = st.columns([2, 1])
        origin = record_filters.selectbox(
            "Refund source",
            ["all", "imported", "web", "customer"],
            format_func=lambda value: {
                "all": "All refund records",
                "imported": "Earlier imported records",
                "web": "Application-created records",
                "customer": "Customer request refunds",
            }[value],
            key="refund_records_origin",
        )
        record_limit = record_size.selectbox(
            "Refund rows per page", [10, 25, 50, 100], index=1, key="refund_records_limit"
        )
        record_offset = st.session_state.setdefault("refund_records_offset", 0)
        try:
            records = client.get(
                "/refunds",
                {"origin": origin, "limit": record_limit, "offset": record_offset},
            )
            display_rows(_refund_table_rows(records["items"], role), "Refund #")
            pagination_controls("refund_records", records["total"], record_limit)
            st.info("Refund records are read-only. New refunds are created through the request workflow above.")
        except APIError as exc:
            show_api_error(exc)
