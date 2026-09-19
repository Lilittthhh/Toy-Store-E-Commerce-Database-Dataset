from __future__ import annotations

import streamlit as st

from frontend.api_client import APIClient
from frontend.ui import data_page_header
from frontend.views import readonly_views


def render(client: APIClient) -> None:
    data_page_header(
        "Website Traffic",
        "Explore the imported acquisition sessions and page journeys behind conversion performance.",
        "website_traffic",
    )
    sessions, pageviews = st.tabs(["Sessions", "Pageviews"])
    with sessions:
        readonly_views.render_sessions(client, embedded=True)
    with pageviews:
        readonly_views.render_pageviews(client, embedded=True)
