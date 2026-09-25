from __future__ import annotations

from decimal import Decimal
from html import escape

import streamlit as st

from frontend.api_client import APIClient, APIError
from frontend.product_assets import product_image_path
from frontend.ui import format_money, show_api_error
from frontend.views.unified_auth import render as render_unified_auth


PUBLIC_VIEW_KEY = "public_store_view"
GUEST_CART_KEY = "guest_cart"


def _set_view(view: str) -> None:
    st.session_state[PUBLIC_VIEW_KEY] = view


def _back_to_store() -> None:
    st.query_params.clear()
    _set_view("shop")


def _guest_cart() -> dict[str, dict]:
    return st.session_state.setdefault(GUEST_CART_KEY, {})


def _cart_quantity() -> int:
    return sum(int(item["quantity"]) for item in _guest_cart().values())


def _add_to_cart(product: dict) -> None:
    cart = _guest_cart()
    key = str(product["product_id"])
    if key in cart:
        cart[key]["quantity"] = min(99, int(cart[key]["quantity"]) + 1)
    else:
        cart[key] = {"product": dict(product), "quantity": 1}


def _remove_from_cart(product_id: int) -> None:
    _guest_cart().pop(str(product_id), None)


def _open_checkout_login() -> None:
    st.session_state["guest_checkout_intent"] = True
    st.session_state["anonymous_auth_view"] = "login"
    _set_view("auth")


def _product_visual(product: dict) -> None:
    bundled_image = product_image_path(product["product_name"])
    if bundled_image:
        st.image(str(bundled_image), use_container_width=True)
        return
    image_url = product.get("image_url")
    if image_url:
        st.image(image_url, use_container_width=True)
        return
    st.markdown(
        '<div class="rm-public-product-visual"><span>RM</span>'
        '<strong>Toy Store favorite</strong><small>Made for everyday play</small></div>',
        unsafe_allow_html=True,
    )


def _header() -> None:
    st.markdown(
        '<div class="rm-public-ribbon">Free browsing · Simulated checkout · Order tracking with an account</div>',
        unsafe_allow_html=True,
    )
    with st.container(key="public_store_header"):
        brand, links, cart, account = st.columns([2.1, 2.3, .9, 1.05], vertical_alignment="center")
        brand.markdown(
            '<div class="rm-site-brand"><span class="rm-site-brand-mark">RM</span><div>'
            '<strong>RetailMetrics</strong><small>Toy Store · Find a little joy</small></div></div>',
            unsafe_allow_html=True,
        )
        links.markdown(
            '<nav class="rm-public-links"><a href="#shop">Shop</a>'
            '<a href="#why-us">Why us</a><a href="#reviews">Reviews</a></nav>',
            unsafe_allow_html=True,
        )
        cart.button(
            f"Bag · {_cart_quantity()}", key="public_cart", use_container_width=True,
            on_click=_set_view, args=("cart",),
        )
        account.button(
            "Sign in", key="public_sign_in", type="primary", use_container_width=True,
            on_click=_set_view, args=("auth",),
        )


def _hero() -> None:
    st.markdown(
        """
        <section class="rm-public-hero">
          <div class="rm-public-hero-copy">
            <div class="rm-shop-kicker">Play starts here</div>
            <h1>Small toys.<br>Big adventures.</h1>
            <p>Discover cheerful favorites for curious minds, cozy afternoons, and every little story in between.</p>
            <div class="rm-public-hero-actions">
              <a class="rm-public-primary-link" href="#shop">Shop the collection →</a>
              <a class="rm-public-secondary-link" href="#reviews">See shopper reviews</a>
            </div>
            <div class="rm-public-proof"><b>4.9/5</b><span>Store preview rating</span><i>★ ★ ★ ★ ★</i></div>
          </div>
          <div class="rm-public-hero-art" aria-hidden="true">
            <span class="rm-public-orbit orbit-one">JOY</span>
            <span class="rm-public-orbit orbit-two">PLAY</span>
            <span class="rm-public-orbit orbit-three">RM</span>
            <strong>Pick a favorite.<br>Make a memory.</strong>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def _benefits() -> None:
    st.markdown(
        """
        <section class="rm-public-benefits" id="why-us">
          <article><span>01</span><div><strong>Browse before joining</strong><p>Explore every available toy and build your bag without an account.</p></div></article>
          <article><span>02</span><div><strong>Simple checkout</strong><p>Sign in only when you are ready to continue with delivery and payment.</p></div></article>
          <article><span>03</span><div><strong>Follow the fun</strong><p>Track each order from confirmation through delivery in one place.</p></div></article>
        </section>
        """,
        unsafe_allow_html=True,
    )


def _reviews() -> None:
    st.markdown(
        """
        <section class="rm-public-review-section" id="reviews">
          <div class="rm-public-section-intro"><div class="rm-shop-kicker">Loved at first sight</div>
          <h2>What shoppers enjoy</h2><p>Friendly feedback from the RetailMetrics store preview.</p></div>
          <div class="rm-public-reviews">
            <blockquote><div>★★★★★</div><p>“The shop feels cheerful and finding the right toy takes no time at all.”</p><footer>Mara · Parent shopper</footer></blockquote>
            <blockquote><div>★★★★★</div><p>“I love that I can browse first and only sign in when I’m ready to check out.”</p><footer>Jamie · Gift buyer</footer></blockquote>
            <blockquote><div>★★★★★</div><p>“Order tracking is clear, and the collection feels small enough to be thoughtfully chosen.”</p><footer>Alex · Returning shopper</footer></blockquote>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def _render_products(client: APIClient) -> None:
    search = st.text_input(
        "Search the collection", placeholder="Search toys, bears, and more…",
        key="public_store_search", label_visibility="collapsed",
    ).strip()
    try:
        products = client.get("/store/products", {"search": search} if search else None)
    except APIError as exc:
        show_api_error(exc)
        return

    label = "product" if len(products) == 1 else "products"
    st.markdown(
        f'<div class="rm-public-section-heading" id="shop"><div><span>Our favorites</span>'
        f'<h2>{"Search results" if search else "The toy collection"}</h2></div>'
        f'<p>{len(products)} available {label}</p></div>', unsafe_allow_html=True,
    )
    if not products:
        st.info("No toys match that search. Try another name or clear the search.")
        return

    columns = st.columns(4, gap="medium")
    for index, product in enumerate(products):
        with columns[index % 4]:
            with st.container(border=True):
                st.markdown('<span class="rm-public-product-marker"></span>', unsafe_allow_html=True)
                _product_visual(product)
                st.subheader(product["product_name"])
                st.markdown(
                    f'<div class="rm-public-product-meta"><strong>{format_money(product["current_price_usd"])}</strong>'
                    '<span>In stock</span></div>', unsafe_allow_html=True,
                )
                st.markdown(
                    f'<p class="rm-public-product-description">{escape(product["description"] or "A cheerful toy-store favorite.")}</p>',
                    unsafe_allow_html=True,
                )
                if st.button(
                    "Add to bag", key=f"public_add_{product['product_id']}",
                    type="primary", use_container_width=True,
                ):
                    _add_to_cart(product)
                    st.toast(f"{product['product_name']} added to your bag.")
                    st.rerun()


def _render_landing(client: APIClient) -> None:
    _header()
    _hero()
    _benefits()
    _render_products(client)
    _reviews()
    st.markdown(
        """
        <section class="rm-public-cta">
          <div><span>Ready when you are</span><h2>Save your bag and follow every order.</h2>
          <p>Create an account or sign in when you are ready to check out.</p></div>
          <a href="#shop">Keep shopping ↑</a>
        </section>
        """,
        unsafe_allow_html=True,
    )


def _render_cart() -> None:
    _header()
    st.markdown(
        '<div class="rm-public-cart-head"><div class="rm-shop-kicker">Your picks</div>'
        '<h1>Your shopping bag</h1><p>You can keep browsing without an account. Sign in only when you are ready to check out.</p></div>',
        unsafe_allow_html=True,
    )
    cart = _guest_cart()
    if not cart:
        st.info("Your bag is empty. Explore the collection to find a favorite.")
        st.button("Browse toys", type="primary", on_click=_set_view, args=("shop",))
        return

    total = Decimal("0.00")
    for key, item in list(cart.items()):
        product = item["product"]
        quantity = int(item["quantity"])
        subtotal = Decimal(str(product["current_price_usd"])) * quantity
        total += subtotal
        with st.container(border=True):
            details, quantity_col, subtotal_col, remove_col = st.columns(
                [3.2, .8, 1, .8], vertical_alignment="center"
            )
            details.markdown(f"**{escape(product['product_name'])}**  \n{format_money(product['current_price_usd'])} each")
            quantity_col.markdown(f"**Qty {quantity}**")
            subtotal_col.markdown(f"**{format_money(subtotal)}**")
            remove_col.button(
                "Remove", key=f"public_remove_{key}", use_container_width=True,
                on_click=_remove_from_cart, args=(product["product_id"],),
            )

    summary, actions = st.columns([2.4, 1], vertical_alignment="bottom")
    summary.markdown(
        f'<div class="rm-public-bag-total"><span>Bag total</span><strong>{format_money(total)}</strong>'
        '<small>Delivery and payment are confirmed after sign-in.</small></div>', unsafe_allow_html=True,
    )
    actions.button(
        "Sign in to checkout", type="primary", use_container_width=True,
        on_click=_open_checkout_login,
    )
    st.button("← Continue shopping", on_click=_set_view, args=("shop",))


def _render_auth() -> None:
    back, _ = st.columns([1, 4])
    back.button("← Back to store", key="public_back_to_store", on_click=_back_to_store)
    if st.session_state.get("guest_checkout_intent"):
        st.info("Your bag is saved. Sign in or create an account to continue checkout.")
    render_unified_auth(APIClient())


def render(client: APIClient) -> None:
    st.markdown('<span class="rm-public-store-marker"></span>', unsafe_allow_html=True)
    view = st.session_state.get(PUBLIC_VIEW_KEY, "shop")
    if st.query_params.get("reset_token") or view == "auth":
        _render_auth()
    elif view == "cart":
        _render_cart()
    else:
        _render_landing(client)
