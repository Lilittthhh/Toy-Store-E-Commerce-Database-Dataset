from __future__ import annotations

from html import escape
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd
import streamlit as st

from frontend.api_client import APIError


def apply_theme() -> None:
    st.markdown(
        """
        <style>
        :root {--rm-navy:#102a43;--rm-teal:#0f766e;--rm-teal-dark:#0b5f59;
          --rm-border:#d9e2ec;--rm-canvas:#f7f9fc;}
        [data-testid="stSidebarNav"], #MainMenu, footer {display:none !important;}
        [data-testid="stHeader"] {background:rgba(247,249,252,.88);}
        .stApp {background:linear-gradient(180deg,#f7f9fc 0%,#fff 34rem);}
        .block-container {padding:1.45rem 2.25rem 2.25rem;max-width:1500px;}
        h1 {color:var(--rm-navy);font-size:2rem !important;font-weight:750 !important;
          letter-spacing:-.035em;line-height:1.12 !important;margin:0 0 .2rem !important;}
        h2 {color:var(--rm-navy);font-size:1.35rem !important;}
        h3 {color:#243b53;font-size:1.05rem !important;}
        h2,h3 {letter-spacing:-.018em;}
        p,label,[data-testid="stCaptionContainer"] {line-height:1.45;}
        [data-testid="stCaptionContainer"] {color:#627d98;}

        [data-testid="stSidebar"] {background:linear-gradient(180deg,#102a43 0%,#163b54 100%);
          border-right:0;box-shadow:8px 0 30px rgba(16,42,67,.10);}
        [data-testid="stSidebar"] > div:first-child {padding-top:1.15rem;}
        [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] {color:#bcccdc !important;}
        [data-testid="stSidebar"] div[role="radiogroup"] {gap:.18rem;}
        [data-testid="stSidebar"] div[role="radiogroup"] label {border:1px solid transparent;
          border-radius:9px;color:#e6eef5;padding:.46rem .58rem;
          transition:background .12s ease,border-color .12s ease;}
        [data-testid="stSidebar"] div[role="radiogroup"] label:hover {background:rgba(255,255,255,.075);}
        [data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {
          background:rgba(45,212,191,.14);border-color:rgba(94,234,212,.27);color:#fff;}
        [data-testid="stSidebar"] .stRadio label p {color:inherit !important;}
        .rm-brand {padding:.35rem .25rem 1rem;}
        .rm-brand-row {display:flex;align-items:center;gap:.72rem;}
        .rm-brand-mark {align-items:center;background:linear-gradient(145deg,#2dd4bf,#0f766e);
          border-radius:10px;box-shadow:0 5px 14px rgba(0,0,0,.18);color:#fff;display:flex;
          font-weight:800;height:38px;justify-content:center;letter-spacing:-.04em;width:38px;}
        .rm-brand-name {color:#fff;font-size:1.08rem;font-weight:750;letter-spacing:-.02em;}
        .rm-brand-subtitle {color:#9fb3c8;font-size:.73rem;margin-top:.05rem;}
        .rm-user-card {background:rgba(255,255,255,.065);border:1px solid rgba(255,255,255,.10);
          border-radius:10px;margin:.1rem .15rem .85rem;padding:.65rem .72rem;}
        .rm-user-name {color:#f0f4f8;font-size:.83rem;font-weight:650;overflow:hidden;text-overflow:ellipsis;}
        .rm-role-badge {background:rgba(45,212,191,.14);border:1px solid rgba(94,234,212,.24);
          border-radius:999px;color:#99f6e4;display:inline-block;font-size:.67rem;font-weight:700;
          letter-spacing:.04em;margin-top:.35rem;padding:.16rem .48rem;text-transform:uppercase;}
        .rm-nav-section {color:#7dd3c7;font-size:.64rem;font-weight:800;letter-spacing:.13em;
          margin:.82rem .45rem .28rem;text-transform:uppercase;}
        [data-testid="stSidebar"] .stButton button {background:transparent;border-color:transparent;
          color:#e6eef5;justify-content:flex-start;min-height:2.15rem;padding:.34rem .62rem;}
        [data-testid="stSidebar"] .stButton button:hover {background:rgba(255,255,255,.075);border-color:rgba(255,255,255,.08);}
        [data-testid="stSidebar"] .stButton button[kind="primary"] {background:rgba(45,212,191,.14);
          border-color:rgba(94,234,212,.27);color:#fff;box-shadow:none;}

        [data-testid="stMetric"] {background:rgba(255,255,255,.96);border:1px solid var(--rm-border);
          border-radius:13px;box-shadow:0 4px 16px rgba(16,42,67,.055);min-height:106px;padding:.9rem 1rem;}
        [data-testid="stMetricLabel"] {color:#627d98;font-weight:650;}
        [data-testid="stMetricValue"] {color:var(--rm-navy);font-size:1.7rem;font-weight:760;}
        div[data-testid="stForm"] {background:rgba(255,255,255,.98);border:1px solid var(--rm-border);
          border-radius:12px;box-shadow:0 3px 14px rgba(16,42,67,.035);max-width:900px;
          padding:1rem 1.1rem .9rem;}
        [data-testid="stVerticalBlockBorderWrapper"] {background:rgba(255,255,255,.78);
          border-color:var(--rm-border) !important;border-radius:12px !important;}
        [data-baseweb="tab-list"] {background:#eaf0f5;border-radius:10px;gap:.25rem;padding:.25rem;}
        [data-baseweb="tab"] {border-radius:8px;color:#486581;font-weight:650;min-height:2.55rem;padding:.55rem 1rem;}
        [aria-selected="true"][data-baseweb="tab"] {background:#fff;color:var(--rm-teal);}
        [data-baseweb="tab-highlight"] {display:none;}
        [data-testid="stDataFrame"] {background:#fff;border:1px solid var(--rm-border);border-radius:11px;
          box-shadow:0 3px 14px rgba(16,42,67,.04);overflow:auto;}
        [data-testid="stAlert"] {border:1px solid rgba(98,125,152,.22);border-radius:10px;
          box-shadow:0 2px 8px rgba(16,42,67,.025);padding-block:.65rem;}
        .stButton > button,[data-testid="stFormSubmitButton"] > button {border-radius:8px;
          font-weight:650;min-height:2.45rem;transition:transform .08s ease,box-shadow .12s ease;}
        .stButton > button:hover,[data-testid="stFormSubmitButton"] > button:hover {
          box-shadow:0 4px 10px rgba(16,42,67,.12);transform:translateY(-1px);}
        button[kind="primary"] {background:var(--rm-teal);border-color:var(--rm-teal);}
        button[kind="primary"]:hover {background:var(--rm-teal-dark);border-color:var(--rm-teal-dark);}
        [class*="st-key-"][class*="_refresh"] button {background:#ecfdf5;border-color:#99d5ca;
          color:var(--rm-teal-dark);white-space:nowrap;}
        [class*="st-key-"][class*="_refresh"] button:hover {background:#d9f5ed;border-color:var(--rm-teal);}
        [class*="st-key-"][class*="_delete"] button {background:#fff7f7;border-color:#efb6b2;color:#a61b1b;}
        [class*="st-key-"][class*="_delete"] button:hover {background:#feeeee;border-color:#cf5c55;color:#861414;}
        .rm-source-legend {display:flex;flex-wrap:wrap;gap:.45rem;margin:.2rem 0 .8rem;}
        .rm-source-pill {align-items:center;border-radius:999px;display:inline-flex;font-size:.72rem;
          font-weight:700;gap:.35rem;padding:.25rem .62rem;}
        .rm-source-pill:before {border-radius:50%;content:"";height:7px;width:7px;}
        .rm-source-imported {background:#eef2f6;color:#486581;}
        .rm-source-imported:before {background:#627d98;}
        .rm-source-application {background:#e7f8f3;color:#0b625b;}
        .rm-source-application:before {background:#0f9d8a;}
        .rm-status-pill {border-radius:999px;display:inline-block;font-size:.7rem;font-weight:750;
          letter-spacing:.025em;padding:.22rem .58rem;text-transform:capitalize;}
        .rm-status-pending {background:#fff7df;color:#8a5b00;}.rm-status-processing {background:#e7f1fb;color:#245a8d;}
        .rm-status-completed,.rm-status-ready-shipped,.rm-status-delivered,.rm-status-paid,.rm-status-approved,.rm-status-available {background:#e7f8f3;color:#0b625b;}
        .rm-status-cancelled,.rm-status-rejected,.rm-status-failed {background:#feeeee;color:#9b2c2c;}
        .rm-status-refunded,.rm-status-partially-refunded,.rm-status-processed {background:#f1ebff;color:#6842a0;}
        .rm-store-hero {background:linear-gradient(120deg,#102a43,#0f766e);border-radius:18px;color:#fff;
          margin-bottom:1.15rem;padding:1.45rem 1.65rem;box-shadow:0 10px 28px rgba(16,42,67,.15);}
        .rm-store-hero h1 {color:#fff!important;font-size:1.75rem!important}.rm-store-hero p {color:#d8f3ee;margin:.3rem 0 0;}
        .rm-section-label {color:#829ab1;font-size:.69rem;font-weight:750;letter-spacing:.09em;
          margin:.45rem 0 .1rem;text-transform:uppercase;}
        .rm-auth-kicker {color:var(--rm-teal);font-size:.72rem;font-weight:800;
          letter-spacing:.12em;text-transform:uppercase;}
        .rm-account-detail {color:#486581;font-size:.9rem;padding:.2rem 0;}
        hr {border-color:#e6edf3 !important;margin:1rem 0 !important;}
        @media (max-width:1400px) {.block-container {padding:1.15rem 1.45rem 1.75rem;}
          [data-testid="stMetric"] {min-height:94px;padding:.72rem .82rem;}
          [data-testid="stMetricValue"] {font-size:1.45rem;}}
        @media (max-width:900px) {.block-container {padding:1rem 1rem 1.5rem;}
          h1 {font-size:1.72rem !important;}}
        </style>
        """,
        unsafe_allow_html=True,
    )


def apply_anonymous_theme() -> None:
    """Hide application navigation and center the public authentication experience."""
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"],
        [data-testid="stSidebarCollapsedControl"],
        [data-testid="stExpandSidebarButton"],
        [data-testid="collapsedControl"] {display:none !important;}
        [data-testid="stAppViewContainer"] {margin-left:0 !important;}
        [data-testid="stHeader"] {background:transparent;height:0;min-height:0;}
        [data-testid="stToolbar"],[data-testid="stDecoration"] {display:none !important;}
        .block-container {max-width:1040px;padding:clamp(1.5rem,5vh,3.5rem) 1.25rem 2rem;}
        .rm-auth-card-marker {display:none;}
        [data-testid="stVerticalBlockBorderWrapper"]:has(.rm-auth-card-marker) {
          background:rgba(255,255,255,.98);border:1px solid #d9e2ec !important;
          border-radius:18px !important;box-shadow:0 18px 48px rgba(16,42,67,.11);
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(.rm-auth-card-marker) > div {
          padding:1.7rem 1.85rem 1.55rem !important;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(.rm-auth-card-marker) [data-testid="stForm"] {
          background:transparent;border:0;box-shadow:none;padding:.35rem 0 0;
        }
        .rm-auth-brand {align-items:center;display:flex;flex-direction:column;margin-bottom:.9rem;text-align:center;}
        .rm-auth-brand-mark {align-items:center;background:linear-gradient(145deg,#2dd4bf,#0f766e);
          border-radius:13px;box-shadow:0 7px 18px rgba(15,118,110,.22);color:#fff;display:flex;
          font-size:1rem;font-weight:800;height:48px;justify-content:center;letter-spacing:-.04em;width:48px;}
        .rm-auth-brand-name {color:#102a43;font-size:1rem;font-weight:760;margin-top:.5rem;}
        .rm-auth-brand-subtitle {color:#829ab1;font-size:.72rem;margin-top:.05rem;}
        [data-testid="stVerticalBlockBorderWrapper"]:has(.rm-auth-card-marker) h1 {
          font-size:1.8rem !important;margin:.15rem 0 .12rem !important;text-align:center;}
        [data-testid="stVerticalBlockBorderWrapper"]:has(.rm-auth-card-marker) [data-testid="stCaptionContainer"] {
          margin-bottom:.75rem;text-align:center;}
        [data-testid="stVerticalBlockBorderWrapper"]:has(.rm-auth-card-marker) input {
          min-height:2.65rem;}
        [class*="st-key-unified_forgot_password"] button {border:0;box-shadow:none;color:#0f766e;
          min-height:1.8rem;padding:.15rem 0;}
        [class*="st-key-unified_forgot_password"] button:hover {background:transparent;box-shadow:none;
          color:#0b5f59;text-decoration:underline;transform:none;}
        .rm-auth-footer-label {color:#627d98;font-size:.82rem;text-align:right;}
        @media (max-width:700px) {
          .block-container {padding:1rem .75rem 1.5rem;}
          [data-testid="stVerticalBlockBorderWrapper"]:has(.rm-auth-card-marker) > div {
            padding:1.25rem 1rem 1.15rem !important;
          }
          [data-testid="stVerticalBlockBorderWrapper"]:has(.rm-auth-card-marker) h1 {font-size:1.55rem !important;}
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def auth_card_header(title: str, subtitle: str, portal_label: str | None = None):
    _, content, _ = st.columns([1, 1.55, 1])
    card = content.container(border=True)
    card.markdown('<span class="rm-auth-card-marker"></span>', unsafe_allow_html=True)
    card.markdown(
        f"""
        <div class="rm-auth-brand">
          <div class="rm-auth-brand-mark">RM</div>
          <div class="rm-auth-brand-name">RetailMetrics</div>
          <div class="rm-auth-brand-subtitle">Toy Store Intelligence</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    card.title(title)
    card.caption(subtitle)
    return card


def apply_customer_theme() -> None:
    """Apply presentation styling only while the authenticated customer portal renders."""
    st.markdown(
        """
        <style>
        :root {--rm-customer-ink:#0b2740;--rm-customer-muted:#526b7a;
          --rm-customer-teal:#07877d;--rm-customer-teal-dark:#056b64;
          --rm-customer-line:#ccd9df;--rm-customer-surface:#ffffff;
          --rm-customer-canvas:#f7f9fb;}
        [data-testid="stHeader"] {background:transparent;height:0;min-height:0;}
        [data-testid="stToolbar"],[data-testid="stDecoration"],#MainMenu,footer {display:none!important;}
        .stApp {background:var(--rm-customer-canvas);}
        .block-container {max-width:1320px;margin-left:0;margin-right:auto;padding:.5rem 1.5rem 1.15rem;}
        h1 {color:var(--rm-customer-ink);font-size:1.78rem!important;line-height:1.08!important;
          margin:0 0 .1rem!important;}
        h2 {color:var(--rm-customer-ink);font-size:1.28rem!important;margin:.15rem 0!important;}
        h3 {color:#173f55;font-size:1rem!important;line-height:1.2!important;margin:.1rem 0!important;}
        p,label,[data-testid="stCaptionContainer"] {color:var(--rm-customer-muted);}
        [data-testid="stVerticalBlock"] {gap:.55rem;}

        [data-testid="stSidebar"] {background:#0a3448;box-shadow:5px 0 20px rgba(8,42,55,.14);
          min-width:208px!important;width:208px!important;}
        [data-testid="stSidebar"] > div:first-child {padding:.68rem .55rem .65rem;width:208px!important;}
        [data-testid="stSidebarUserContent"] {min-height:calc(100vh - 1.35rem);position:relative;}
        [data-testid="stSidebar"] .rm-brand {padding:.05rem .16rem .48rem;}
        [data-testid="stSidebar"] .rm-brand-row {gap:.52rem;}
        [data-testid="stSidebar"] .rm-brand-mark {background:#0ca99a;border-radius:7px;height:29px;width:29px;}
        [data-testid="stSidebar"] .rm-brand-name {font-size:.84rem;}
        [data-testid="stSidebar"] .rm-brand-subtitle {color:#b5cbd4!important;font-size:.59rem;}
        [data-testid="stSidebar"] .rm-user-card {background:rgba(255,255,255,.075);
          border-color:rgba(255,255,255,.13);margin:.01rem .06rem .46rem;padding:.43rem .5rem;}
        [data-testid="stSidebar"] .rm-user-name {color:#fff!important;font-size:.72rem;}
        [data-testid="stSidebar"] .rm-role-badge {color:#b9fff3!important;font-size:.56rem;margin-top:.2rem;padding:.12rem .38rem;}
        [data-testid="stSidebar"] [class*="st-key-customer_nav_"] {margin:.06rem 0;}
        [data-testid="stSidebar"] [class*="st-key-customer_nav_"] button {border:1px solid transparent;
          border-radius:7px;color:rgba(245,251,252,.86);font-size:.76rem;font-weight:560;
          justify-content:flex-start;min-height:1.96rem;padding:.28rem .48rem;box-shadow:none;}
        [data-testid="stSidebar"] [class*="st-key-customer_nav_"] button:hover {
          background:rgba(255,255,255,.075);border-color:rgba(255,255,255,.08);color:#fff;transform:none;}
        [data-testid="stSidebar"] [class*="st-key-customer_nav_"] button[kind="primary"] {
          background:#087f78;border-color:#159b91;color:#fff;font-weight:700;box-shadow:0 3px 9px rgba(0,0,0,.12);}
        [data-testid="stSidebar"] [class*="st-key-customer_nav_"] button:before {
          display:inline-block;font-size:.78rem;margin-right:.5rem;text-align:center;width:.92rem;}
        [class*="st-key-customer_nav_home"] button:before {content:"⌂";}
        [class*="st-key-customer_nav_cart"] button:before {content:"▣";}
        [class*="st-key-customer_nav_orders"] button:before {content:"◉";}
        [class*="st-key-customer_nav_account"] button:before {content:"♙";}
        [class*="st-key-customer_nav_logout"] {bottom:3.55rem;left:.55rem;position:absolute;right:.55rem;}
        [class*="st-key-customer_nav_logout"] button:before {content:"↪";}
        .rm-customer-sidebar-footer {color:#9ddbd4;font-size:.62rem;line-height:1.38;
          border-top:1px solid rgba(255,255,255,.1);bottom:.2rem;left:.4rem;margin:0;padding:.52rem .08rem 0;
          position:absolute;right:.4rem;}

        .rm-shop-hero {background:linear-gradient(110deg,#dff3f0 0%,#f8fbfb 74%,#e8f3f1 100%);
          border:1px solid #c8dfdc;border-left:5px solid var(--rm-customer-teal);border-radius:12px;
          box-shadow:0 4px 13px rgba(11,39,64,.055);margin:.08rem 0 .45rem;
          min-height:124px;padding:.82rem 1.15rem;}
        .rm-shop-hero h2 {font-size:1.78rem!important;line-height:1.08!important;margin:0 0 .32rem!important;max-width:430px;}
        .rm-shop-hero p {color:#365d69;font-size:.88rem;line-height:1.4;margin:0;max-width:520px;}
        .rm-shop-kicker {color:var(--rm-customer-teal-dark);font-size:.65rem;font-weight:800;
          letter-spacing:.11em;margin-bottom:.32rem;text-transform:uppercase;}
        .rm-section-heading {align-items:end;display:flex;justify-content:space-between;margin:.08rem 0 .18rem;}
        .rm-section-heading strong {color:var(--rm-customer-ink);font-size:1.02rem;}
        .rm-section-heading span {color:#617b88;font-size:.72rem;}
        .rm-trust-row {background:#f8fbfb;border:1px solid var(--rm-customer-line);border-radius:12px;
          display:grid;gap:.6rem;grid-template-columns:repeat(3,1fr);margin-top:1rem;padding:.8rem;}
        .rm-trust-item {color:#476473;font-size:.76rem;text-align:center;}
        .rm-trust-item b {color:var(--rm-customer-teal-dark);display:block;font-size:.82rem;margin-bottom:.12rem;}

        .rm-product-card-marker,.rm-cart-row-marker,.rm-summary-card-marker,
        .rm-checkout-card-marker,.rm-order-card-marker,.rm-account-card-marker,
        .rm-refund-card-marker,.rm-product-detail-marker {display:none;}
        [data-testid="stVerticalBlockBorderWrapper"]:has(.rm-product-card-marker),
        [data-testid="stVerticalBlockBorderWrapper"]:has(.rm-cart-row-marker),
        [data-testid="stVerticalBlockBorderWrapper"]:has(.rm-summary-card-marker),
        [data-testid="stVerticalBlockBorderWrapper"]:has(.rm-checkout-card-marker),
        [data-testid="stVerticalBlockBorderWrapper"]:has(.rm-order-card-marker),
        [data-testid="stVerticalBlockBorderWrapper"]:has(.rm-account-card-marker),
        [data-testid="stVerticalBlockBorderWrapper"]:has(.rm-refund-card-marker),
        [data-testid="stVerticalBlockBorderWrapper"]:has(.rm-product-detail-marker) {
          background:var(--rm-customer-surface);border:1px solid var(--rm-customer-line)!important;
          border-radius:10px!important;box-shadow:0 3px 10px rgba(11,39,64,.04);}
        [data-testid="stVerticalBlockBorderWrapper"]:has(.rm-product-card-marker) {height:320px;
          border-color:#d8e1e6!important;box-shadow:0 2px 8px rgba(11,39,64,.045);}
        [data-testid="stVerticalBlockBorderWrapper"]:has(.rm-product-card-marker) > div {height:100%;padding:.55rem!important;}
        [data-testid="stVerticalBlockBorderWrapper"]:has(.rm-product-card-marker) [data-testid="stVerticalBlock"] {gap:.34rem;}
        [data-testid="stVerticalBlockBorderWrapper"]:has(.rm-product-card-marker) h3 {align-items:center;display:flex;
          font-size:.94rem!important;min-height:2.25rem;}
        [data-testid="stVerticalBlockBorderWrapper"]:has(.rm-product-card-marker) [data-testid="stImage"] img {
          height:96px!important;object-fit:cover;width:100%;}
        [data-testid="stVerticalBlockBorderWrapper"]:has(.rm-product-card-marker) button {font-size:.76rem!important;
          min-height:2rem!important;padding:.25rem .5rem!important;}
        [data-testid="stVerticalBlockBorderWrapper"]:has(.rm-product-detail-marker) > div {padding:.75rem!important;}
        [data-testid="stVerticalBlockBorderWrapper"]:has(.rm-product-detail-marker) [data-testid="stForm"] {
          background:#f8fbfb;margin-top:.35rem;padding:.55rem .65rem .48rem;}
        .rm-product-visual {align-items:center;background:#f1f5f7;border:1px dashed #b7c9d2;
          border-radius:9px;color:#728d9d;display:flex;flex-direction:column;gap:.24rem;justify-content:center;}
        .rm-product-visual span {color:#8ca6b4;font-size:1.25rem;line-height:1;}
        .rm-product-visual small {font-size:.67rem;font-weight:650;}
        .rm-product-description {color:#607985;font-size:.73rem;line-height:1.34;min-height:1.96rem;
          max-height:1.96rem;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden;}
        [class*="st-key-view_product_"] {margin-top:auto;}
        [data-testid="stVerticalBlockBorderWrapper"]:has(.rm-summary-card-marker) {background:#fbfdfd;}
        [data-testid="stVerticalBlockBorderWrapper"]:has(.rm-checkout-card-marker) {padding:.1rem;}
        [data-testid="stVerticalBlockBorderWrapper"]:has(.rm-order-card-marker) {margin-bottom:.55rem;}
        [data-testid="stVerticalBlockBorderWrapper"]:has(.rm-refund-card-marker) {margin-bottom:.48rem;}
        [data-testid="stVerticalBlockBorderWrapper"]:has(.rm-refund-card-marker) > div {padding:.62rem .72rem!important;}
        [data-testid="stVerticalBlockBorderWrapper"]:has(.rm-refund-card-marker) [data-testid="stForm"] {
          background:#f8fbfb;margin-top:.25rem;padding:.5rem .58rem .42rem;}
        [data-testid="stVerticalBlockBorderWrapper"]:has(.rm-refund-card-marker) [data-testid="stFormSubmitButton"] {
          max-width:190px;}

        .rm-price {color:var(--rm-customer-ink);font-size:1.2rem;font-weight:800;letter-spacing:-.025em;}
        .rm-cart-summary-line {display:flex;justify-content:space-between;padding:.26rem 0;color:#476473;font-size:.82rem;}
        .rm-cart-summary-line.rm-total {border-top:1px solid var(--rm-customer-line);color:var(--rm-customer-ink);
          font-size:1.02rem;font-weight:800;margin-top:.25rem;padding-top:.72rem;}
        .rm-checkout-steps {display:flex;flex-direction:column;gap:.75rem;padding:.15rem 0;}
        .rm-checkout-step {align-items:flex-start;color:#58717e;display:flex;font-size:.76rem;gap:.52rem;}
        .rm-checkout-step span {align-items:center;background:#e4f4f1;border-radius:50%;color:#08766f;
          display:flex;flex:0 0 25px;font-size:.72rem;font-weight:800;height:25px;justify-content:center;}
        .rm-checkout-step b {color:var(--rm-customer-ink);display:block;font-size:.78rem;margin-bottom:.08rem;}
        .rm-confirmation {background:#e9f8f3;border:1px solid #bfe8dc;border-radius:13px;
          color:#155e57;margin:.45rem 0 .8rem;padding:.85rem 1rem;}
        .rm-confirmation strong {color:#0a514c;display:block;font-size:1rem;margin-bottom:.12rem;}
        .rm-order-meta {color:#6a8390;font-size:.76rem;}

        [data-baseweb="tab-list"] {background:#edf4f3;border:1px solid #dfebea;border-radius:9px;padding:.2rem;}
        [aria-selected="true"][data-baseweb="tab"] {color:var(--rm-customer-teal-dark);box-shadow:0 2px 7px rgba(11,39,64,.06);}
        [data-testid="stMetric"] {border-color:var(--rm-customer-line);box-shadow:0 3px 10px rgba(11,39,64,.045);
          min-height:72px;padding:.55rem .7rem;}
        [data-testid="stMetricValue"] {font-size:1.25rem!important;}
        div[data-testid="stForm"] {border-color:var(--rm-customer-line);box-shadow:none;max-width:none;padding:.68rem .75rem .58rem;}
        [data-testid="stTextInput"] input,[data-testid="stNumberInput"] input {min-height:2.25rem!important;}
        [class*="st-key-store_search"] input {font-size:.82rem;min-height:2.05rem!important;padding:.32rem .7rem;}
        [data-testid="stTextInput"] {margin-bottom:0;}
        .stButton > button,[data-testid="stFormSubmitButton"] > button {min-height:2.15rem;}
        button[kind="primary"] {background:var(--rm-customer-teal);border-color:var(--rm-customer-teal);}
        button[kind="primary"]:hover {background:var(--rm-customer-teal-dark);border-color:var(--rm-customer-teal-dark);}
        [class*="st-key-cancel_order_"] button,[class*="st-key-address_deactivate_"] button,
        [class*="st-key-payment_deactivate_"] button {background:#fff5f5;border-color:#efc2c2;color:#a52a2a;}

        @media (max-width:1600px) {
          .block-container {max-width:1220px;padding:.45rem 1.5rem 1rem;}
          [data-testid="stSidebar"],[data-testid="stSidebar"] > div:first-child {min-width:204px!important;width:204px!important;}
          .rm-shop-hero {min-height:118px;padding:.72rem 1rem;}
          .rm-shop-hero h2 {font-size:1.55rem!important;}
          [data-testid="stVerticalBlockBorderWrapper"]:has(.rm-product-card-marker) {height:306px;}
          [data-testid="stVerticalBlockBorderWrapper"]:has(.rm-product-card-marker) > div {padding:.48rem!important;}
        }
        @media (max-width:900px) {
          .block-container {padding:.5rem .65rem 1rem;}
          .rm-shop-hero {min-height:auto;padding:1rem;}
          .rm-trust-row {grid-template-columns:1fr;}
          .rm-section-heading {align-items:flex-start;flex-direction:column;gap:.15rem;}
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def show_api_error(error: APIError) -> None:
    labels = {
        0: "Connection problem",
        401: "Your session has expired. Please log in again.",
        403: "You are not authorized to perform this action.",
        404: "The requested record was not found.",
        409: "The record changed or conflicts with existing data.",
        422: "Please correct the submitted values.",
    }
    heading = labels.get(error.status_code, "Request failed")
    st.error(f"**{heading}**  \n{error.message}")


def render_sidebar_brand(username: str | None = None, role: str | None = None) -> None:
    st.sidebar.markdown(
        """
        <div class="rm-brand">
          <div class="rm-brand-row">
            <div class="rm-brand-mark">RM</div>
            <div>
              <div class="rm-brand-name">RetailMetrics</div>
              <div class="rm-brand-subtitle">Toy Store Intelligence</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if username and role:
        role_label = role.replace("_", " ").title()
        st.sidebar.markdown(
            f"""
            <div class="rm-user-card">
              <div class="rm-user-name">{escape(username)}</div>
              <div class="rm-role-badge">{escape(role_label)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def page_header(title: str, caption: str) -> None:
    st.title(title)
    st.caption(caption)


def format_value(value: Any, unavailable: str = "—") -> Any:
    """Normalize empty presentation values without changing stored data."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return unavailable
    return value


def format_status(value: str | None, unavailable: str = "—") -> str:
    if value is None or not str(value).strip():
        return unavailable
    if str(value).strip().lower() == "ready_shipped":
        return "Ready / Shipped"
    return str(value).strip().replace("_", " ").title()


def format_money(value: Any, unavailable: str = "—") -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        return unavailable
    try:
        return f"${Decimal(str(value)):,.2f}"
    except (InvalidOperation, ValueError):
        return str(value)


def status_badge(value: str | None) -> None:
    label = format_status(value)
    css = str(value).strip().lower().replace("_", "-") if value else "unknown"
    st.markdown(f'<span class="rm-status-pill rm-status-{escape(css)}">{escape(label)}</span>', unsafe_allow_html=True)


def data_page_header(title: str, caption: str, key: str) -> None:
    heading, action = st.columns([6, 1.15], vertical_alignment="bottom")
    with heading:
        st.title(title)
        st.caption(caption)
    with action:
        if st.button(
            "Refresh Data",
            key=f"{key}_refresh",
            help="Fetch the latest available records",
            use_container_width=True,
        ):
            st.toast("Data refreshed successfully.")


def section_label(text: str) -> None:
    st.markdown(
        f'<div class="rm-section-label">{escape(text)}</div>',
        unsafe_allow_html=True,
    )


def source_legend(origins: tuple[str, ...] = ("imported", "web", "customer")) -> None:
    labels = {
        "imported": ('rm-source-imported', 'Historical data'),
        "web": ('rm-source-application', 'Application-created'),
        "staff": ('rm-source-application', 'Application-created'),
        "customer": ('rm-source-application', 'Customer-created'),
    }
    pills = "".join(
        f'<span class="rm-source-pill {labels[origin][0]}">{labels[origin][1]}</span>'
        for origin in origins
    )
    st.markdown(
        f'<div class="rm-source-legend">{pills}</div>',
        unsafe_allow_html=True,
    )


def source_label(row: dict[str, Any]) -> str:
    labels = {
        "imported": "Historical data",
        "customer": "Customer-created",
        "web": "Application-created",
        "staff": "Application-created",
    }
    return labels.get(row.get("origin"), "Application-created")


def format_datetime(value: Any) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        return "—"
    try:
        parsed = pd.to_datetime(value)
        return parsed.strftime("%b %d, %Y · %I:%M %p")
    except (TypeError, ValueError):
        return str(value)


def display_rows(rows: list[dict[str, Any]], id_column: str) -> None:
    if not rows:
        st.info("No records match the current filters.")
        return
    normalized = []
    for row in rows:
        item = dict(row)
        if "origin" in item:
            item["Source"] = source_label(item)
            item.pop("origin", None)
        item.pop("created_by_app_user_id", None)
        item.pop("row_version", None)
        for column in tuple(item):
            if column.lower().endswith("status") or column.lower() == "status":
                item[column] = format_status(item[column])
            elif column.endswith("_at"):
                item[column] = format_datetime(item[column])
            else:
                item[column] = format_value(item[column])
        normalized.append(item)
    frame = pd.DataFrame(normalized)
    columns = [id_column, *[column for column in frame.columns if column != id_column]]
    frame = frame[columns]
    frame.columns = [column.replace("_", " ").title().replace("Usd", "USD").replace("Id", "ID") for column in frame.columns]
    configs = {
        column: st.column_config.TextColumn(column, width="large")
        for column in {"Http Referer", "Pageview Url", "Product Name"}
        if column in frame.columns
    }
    if "Source" in frame.columns:
        configs["Source"] = st.column_config.TextColumn("Source", width="medium")
    for column in frame.columns:
        if column.endswith(" ID") or column == "ID":
            configs[column] = st.column_config.NumberColumn(column, width="small", format="%d")
        elif column.endswith(" USD"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
            configs[column] = st.column_config.NumberColumn(column, width="small", format="$%.2f")
    st.dataframe(
        frame,
        use_container_width=True,
        hide_index=True,
        height=max(170, min(510, 38 + len(frame) * 34)),
        column_config=configs,
    )


def pagination_controls(key: str, total: int, limit: int) -> int:
    offset_key = f"{key}_offset"
    st.session_state.setdefault(offset_key, 0)
    offset = min(st.session_state[offset_key], max(0, ((max(total, 1) - 1) // limit) * limit))
    st.session_state[offset_key] = offset
    left, middle, right = st.columns([1.15, 3, 1.15], vertical_alignment="center")
    if left.button(
        "← Previous",
        key=f"{key}_previous",
        disabled=offset == 0,
        use_container_width=True,
    ):
        st.session_state[offset_key] = max(0, offset - limit)
        st.rerun()
    page_number = offset // limit + 1
    pages = max(1, (total + limit - 1) // limit)
    middle.caption(f"Page {page_number} of {pages} · {total:,} records")
    if right.button(
        "Next →",
        key=f"{key}_next",
        disabled=offset + limit >= total,
        use_container_width=True,
    ):
        st.session_state[offset_key] = offset + limit
        st.rerun()
    return offset
