"""Admin-only, read-only audit inspection UI."""
from __future__ import annotations

import streamlit as st

from frontend.api_client import APIClient, APIError
from frontend.ui import data_page_header, format_datetime, pagination_controls, show_api_error


def render(client: APIClient) -> None:
    data_page_header("Audit Trail", "Review security and business changes. Entries cannot be edited or removed.", "audit_trail")
    with st.container(border=True):
        first = st.columns([2, 1, 1, 1])
        search = first[0].text_input("Search action or entity", key="audit_search")
        role = first[1].selectbox("Actor role", ["All", "admin", "operations_staff", "analyst", "customer"], key="audit_role")
        action = first[2].text_input("Action", key="audit_action")
        limit = first[3].selectbox("Rows", [10, 25, 50, 100], index=1, key="audit_limit")
        second = st.columns(3)
        entity = second[0].text_input("Entity type", key="audit_entity")
        from_date = second[1].date_input("From", value=None, key="audit_from")
        to_date = second[2].date_input("To", value=None, key="audit_to")
    offset = st.session_state.setdefault("audit_trail_offset", 0)
    params = {"limit": limit, "offset": offset}
    if search:
        params["search"] = search
    if role != "All":
        params["actor_role"] = role
    if action:
        params["action"] = action.strip().upper()
    if entity:
        params["entity_type"] = entity.strip().lower()
    if from_date:
        params["from_date"] = from_date.isoformat() + "T00:00:00"
    if to_date:
        params["to_date"] = to_date.isoformat() + "T23:59:59.999999"
    try:
        result = client.get("/admin/audit-logs", params)
    except APIError as exc:
        show_api_error(exc)
        return
    rows = result["items"]
    if not rows:
        st.info("No audit events match these filters.")
    else:
        st.dataframe([{
            "Date / Time": format_datetime(row["created_at"]),
            "User": row.get("actor_display") or "Anonymous / System",
            "Role": row.get("actor_role") or "—",
            "Action": row["action"].replace("_", " ").title(),
            "Entity": row.get("entity_type") or "—",
            "Entity ID": row.get("entity_id") or "—",
            "Description": row.get("description") or "—",
        } for row in rows], use_container_width=True, hide_index=True)
        selected = st.selectbox("Inspect event", [None, *[row["audit_log_id"] for row in rows]],
                                format_func=lambda value: "Select an event" if value is None else f"Event #{value}")
        if selected is not None:
            row = next(row for row in rows if row["audit_log_id"] == selected)
            with st.container(border=True):
                st.subheader(f"Event #{selected}")
                st.write(f"{format_datetime(row['created_at'])} · {row['action']} · {row.get('actor_display') or 'Anonymous / System'}")
                st.write(f"Entity: {row.get('entity_type') or '—'} #{row.get('entity_id') or '—'}")
                if row.get("old_values"):
                    st.caption("Previous safe state")
                    st.json(row["old_values"])
                if row.get("new_values"):
                    st.caption("New safe state")
                    st.json(row["new_values"])
                st.caption(f"IP: {row.get('ip_address') or 'Not captured'}")
    pagination_controls("audit_trail", result["total"], limit)
