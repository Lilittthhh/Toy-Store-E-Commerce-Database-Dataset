from __future__ import annotations

import pandas as pd
import streamlit as st

from frontend.api_client import APIClient, APIError
from frontend.ui import data_page_header, show_api_error


def render(client: APIClient) -> None:
    data_page_header("Project Evidence", "Academic technical validation from stable, read-only Session 1–3 result artifacts.", "project_evidence")
    try:
        report = client.get("/analytics/reports")
    except APIError as exc:
        show_api_error(exc)
        return
    if not report.get("available"):
        st.info(report.get("message", "Report artifacts are unavailable."))
        return
    st.success("Session 3 reconciliation: PASS" if report["reconciliation"].get("passed") else "Session 3 reconciliation requires review")
    st.caption("Source: Verified Session 3 result artifacts. Sessions 1–3 executable modules are never imported or run by this web application.")
    overview, products, diagnostics = st.tabs(["Reconciliation", "Product Performance Evidence", "Communication Diagnostics"])
    with overview:
        with st.expander("Raw reconciliation JSON", expanded=False):
            st.json(report["reconciliation"], expanded=False)
    with products:
        st.caption("Session 3 result only — not presented as a Sessions 1/2 cross-comparison.")
        st.dataframe(pd.DataFrame(report["product_performance"]), use_container_width=True, hide_index=True)
    with diagnostics:
        st.warning(report["observation_note"])
        st.subheader("Measured local latency")
        st.dataframe(pd.DataFrame(report["latency"]), use_container_width=True, hide_index=True)
        st.subheader("Serialized payload size")
        st.dataframe(pd.DataFrame(report["payload_sizes"]), use_container_width=True, hide_index=True)
