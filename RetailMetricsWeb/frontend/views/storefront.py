from __future__ import annotations

from html import escape

import streamlit as st

from frontend.api_client import APIClient, APIError
from frontend.navigation import request_customer_navigation
from frontend.ui import data_page_header, format_datetime, format_money, format_status, page_header, show_api_error, status_badge


def _money(value) -> str:
    return format_money(value)


def _product_visual(product: dict, height: int = 170) -> None:
    if product.get("image_url"):
        st.image(product["image_url"], use_container_width=True)
    else:
        st.markdown(
            f'<div class="rm-product-visual" style="height:{height}px"><span>&#9635;</span><small>Product image</small></div>',
            unsafe_allow_html=True,
        )


def _add_form(client: APIClient, product: dict, key: str) -> None:
    with st.form(key):
        quantity = st.number_input("Quantity", min_value=1, max_value=99, value=1, step=1)
        add = st.form_submit_button("Add to Cart", type="primary", use_container_width=True)
    if add:
        try:
            client.post("/customer/cart/items", {"product_id": product["product_id"], "quantity": int(quantity)})
            st.success(f"{product['product_name']} added to your cart.")
        except APIError as exc:
            show_api_error(exc)


def render_shop(client: APIClient, customer: dict) -> None:
    search = st.text_input(
        "Search by product name",
        placeholder="Search toys, bears, and more…",
        key="store_search",
        label_visibility="collapsed",
    )
    st.markdown(
        f"""
        <div class="rm-shop-hero">
          <div class="rm-shop-kicker">Hello, {customer['first_name']}</div>
          <h2>Toys for Brighter Days</h2>
          <p>Discover cheerful toys for every occasion and choose something delightful.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    try:
        products = client.get("/customer/store/products", {"search": search} if search else None)
    except APIError as exc:
        show_api_error(exc)
        return
    if not products:
        st.info("No available toys match your search. Try a different product name.")
        return

    selected_id = st.session_state.get("store_product_detail")
    if selected_id:
        try:
            product = client.get(f"/customer/store/products/{selected_id}")
        except APIError as exc:
            st.session_state.pop("store_product_detail", None)
            show_api_error(exc)
        else:
            if st.button("← Back to products", key="store_back"):
                st.session_state.pop("store_product_detail", None)
                st.rerun()
            with st.container(border=True):
                st.markdown('<span class="rm-product-detail-marker"></span>', unsafe_allow_html=True)
                image_col, detail_col = st.columns([1, 1.25], gap="large")
                with image_col:
                    _product_visual(product, 220)
                with detail_col:
                    st.subheader(product["product_name"])
                    st.markdown(f'<div class="rm-price">{_money(product["current_price_usd"])}</div>', unsafe_allow_html=True)
                    status_badge("available")
                    st.write(product["description"] or "More product details are coming soon.")
                    _add_form(client, product, f"detail_add_{selected_id}")
            st.markdown(
                """
                <div class="rm-trust-row">
                  <div class="rm-trust-item"><b>Quality Toys</b>Carefully presented for you</div>
                  <div class="rm-trust-item"><b>Secure Checkout</b>Prices confirmed at checkout</div>
                  <div class="rm-trust-item"><b>Your Account</b>Your saved details stay private</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            return

    st.markdown(
        '<div class="rm-section-heading"><strong>Featured Products</strong><span>Toys ready to explore</span></div>',
        unsafe_allow_html=True,
    )
    columns = st.columns(4, gap="medium")
    for index, product in enumerate(products):
        with columns[index % 4]:
            with st.container(border=True):
                st.markdown('<span class="rm-product-card-marker"></span>', unsafe_allow_html=True)
                _product_visual(product, 96)
                st.subheader(product["product_name"])
                st.markdown(f'<div class="rm-price">{_money(product["current_price_usd"])}</div>', unsafe_allow_html=True)
                description = product["description"] or "More product details are coming soon."
                st.markdown(f'<div class="rm-product-description">{escape(description)}</div>', unsafe_allow_html=True)
                if st.button("View Details", key=f"view_product_{product['product_id']}", use_container_width=True):
                    st.session_state.store_product_detail = product["product_id"]
                    st.rerun()
                with st.popover("Add to Cart", use_container_width=True):
                    _add_form(client, product, f"card_add_{product['product_id']}")


def render_cart(client: APIClient) -> None:
    if st.session_state.pop("resume_checkout_after_account", False):
        st.session_state.show_checkout = True
    if st.session_state.get("show_checkout"):
        render_checkout(client)
        return
    heading, action = st.columns([5, 1.25], vertical_alignment="bottom")
    with heading:
        st.title("Your Cart")
        st.caption("Prices are revalidated securely when you checkout.")
    with action:
        if st.button("Continue Shopping", key="cart_continue_shopping", use_container_width=True):
            request_customer_navigation("Home / Shop")
            st.rerun()
    try:
        cart = client.get("/customer/cart")
    except APIError as exc:
        show_api_error(exc)
        return
    if not cart["items"]:
        st.info("Your cart is empty. Visit Home / Shop to add an available product.")
        if st.button("Browse Products", key="empty_cart_browse"):
            request_customer_navigation("Home / Shop")
            st.rerun()
        return
    items_col, summary_col = st.columns([3.15, 1.15], gap="large")
    with items_col:
        for item in cart["items"]:
            with st.container(border=True):
                st.markdown('<span class="rm-cart-row-marker"></span>', unsafe_allow_html=True)
                visual, details, quantity_col, subtotal_col = st.columns([.72, 2.15, 1.05, .92], gap="small", vertical_alignment="center")
                with visual:
                    _product_visual(item, 68)
                with details:
                    st.markdown(f"**{item['product_name']}**")
                    st.caption(f"Unit price {_money(item['stored_unit_price_usd'])}")
                with quantity_col:
                    with st.form(f"cart_quantity_{item['cart_item_id']}"):
                        quantity = st.number_input("Quantity", min_value=1, max_value=99, value=item["quantity"], step=1)
                        save = st.form_submit_button("Update", use_container_width=True)
                    if save:
                        try:
                            client.put(f"/customer/cart/items/{item['cart_item_id']}", {"quantity": int(quantity), "row_version": item["row_version"]})
                            st.success("Quantity updated.")
                            st.rerun()
                        except APIError as exc:
                            show_api_error(exc)
                with subtotal_col:
                    st.markdown(f"**{_money(item['line_subtotal_usd'])}**")
                    if st.button("Remove", key=f"cart_remove_{item['cart_item_id']}", use_container_width=True):
                        try:
                            client.delete(f"/customer/cart/items/{item['cart_item_id']}", {"row_version": item["row_version"]})
                            st.success("Item removed.")
                            st.rerun()
                        except APIError as exc:
                            show_api_error(exc)
                if item["price_changed"]:
                    st.warning(f"Catalog price changed to {_money(item['current_catalog_price_usd'])}. Checkout will require confirmation.")
                if not item["is_available"]:
                    st.error("This product is currently unavailable. It remains visible so you can remove it.")
    with summary_col:
        with st.container(border=True):
            st.markdown('<span class="rm-summary-card-marker"></span>', unsafe_allow_html=True)
            st.subheader("Cart Summary")
            st.markdown(
                f"""
                <div class="rm-cart-summary-line"><span>Total units</span><b>{cart['total_quantity']}</b></div>
                <div class="rm-cart-summary-line"><span>Subtotal</span><b>{_money(cart['cart_subtotal_usd'])}</b></div>
                <div class="rm-cart-summary-line rm-total"><span>Total</span><span>{_money(cart['cart_subtotal_usd'])}</span></div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("Proceed to Checkout", type="primary", use_container_width=True):
                st.session_state.show_checkout = True
                st.rerun()


def _address_label(value: dict) -> str:
    return f"{value['label']} — {value['address_line_1']}, {value['city']}"


def render_checkout(client: APIClient) -> None:
    page_header("Checkout", "Choose your delivery and payment details, then review your order.")
    if st.button("← Return to Cart", key="checkout_back"):
        st.session_state.show_checkout = False
        st.rerun()
    confirmation = st.session_state.get("checkout_confirmation")
    if confirmation:
        st.markdown(
            f'<div class="rm-confirmation"><strong>Order placed successfully</strong>Your order number is #{confirmation["order_id"]}.</div>',
            unsafe_allow_html=True,
        )
        try:
            notification = client.get(f"/customer/orders/{confirmation['order_id']}/notifications")
        except APIError:
            notification = None
        if isinstance(notification, dict):
            statuses = {item.get("delivery_status") for item in notification.get("items", [])}
            if "failed" in statuses:
                st.warning("Your order was placed successfully, but we could not send the notification right now.")
            elif "sending" in statuses or "pending" in statuses:
                st.info("Your order was placed successfully. Notification delivery is pending.")
            elif statuses and notification.get("mode") == "mock":
                st.info("Order notification prepared in test mode.")
            elif statuses and notification.get("mode") == "infobip" and statuses == {"sent"}:
                st.info("Order confirmation sent to your registered contact information.")
        with st.container(border=True):
            st.markdown('<span class="rm-checkout-card-marker"></span>', unsafe_allow_html=True)
            first, second, third = st.columns(3)
            first.metric("Order status", format_status(confirmation["order_status"]))
            second.metric("Payment status", format_status(confirmation["payment"]["payment_status"]))
            third.metric("Total", _money(confirmation["total_usd"]))
            detail_col, shipping_col = st.columns(2, gap="large")
            detail_col.markdown(f"**Payment**  \n{confirmation['payment']['display_label']}")
            shipping_col.markdown(
                f"**Shipping to**  \n{confirmation['shipping']['recipient_first_name']} "
                f"{confirmation['shipping']['recipient_last_name']} · {confirmation['shipping']['city']}"
            )
            view_col, shop_col = st.columns(2)
            if view_col.button("View Order", type="primary", use_container_width=True):
                st.session_state.order_detail_id = confirmation["order_id"]
                st.session_state.show_checkout = False
                st.session_state.pop("checkout_confirmation", None)
                request_customer_navigation("My Orders")
                st.rerun()
            if shop_col.button("Continue Shopping", use_container_width=True):
                st.session_state.pop("checkout_confirmation", None)
                st.session_state.show_checkout = False
                st.session_state.store_product_detail = None
                request_customer_navigation("Home / Shop")
                st.rerun()
        return
    try:
        cart = client.get("/customer/cart")
        addresses = [value for value in client.get("/customer/addresses") if value["is_active"]]
        payments = [value for value in client.get("/customer/payment-methods") if value["is_active"]]
    except APIError as exc:
        show_api_error(exc)
        return
    if not cart["items"] or cart.get("row_version") is None:
        st.warning("Your cart is empty. Return to the shop before checkout.")
        return
    if not addresses:
        st.warning("Add an active shipping address under My Account → Addresses before checkout.")
        if st.button("Go to My Account", key="checkout_address_account"):
            st.session_state.show_checkout = False
            st.session_state.resume_checkout_after_account = True
            request_customer_navigation("My Account")
            st.rerun()
        return
    if not payments:
        st.warning("Add an active simulated payment method under My Account → Payment Methods before checkout.")
        if st.button("Go to My Account", key="checkout_payment_account"):
            st.session_state.show_checkout = False
            st.session_state.resume_checkout_after_account = True
            request_customer_navigation("My Account")
            st.rerun()
        return
    if any(item["price_changed"] for item in cart["items"]):
        st.warning("A catalog price changed. Review and reconfirm the cart before checkout.")
    if any(not item["is_available"] for item in cart["items"]):
        st.error("An item is unavailable. Remove it before checkout.")
    address_map = {item["customer_address_id"]: item for item in addresses}
    default_address = next((item["customer_address_id"] for item in addresses if item["is_default"]), addresses[0]["customer_address_id"])
    payment_map = {item["payment_method_id"]: item for item in payments}
    default_payment = next((item["payment_method_id"] for item in payments if item["is_default"]), payments[0]["payment_method_id"])
    blocked = any(item["price_changed"] or not item["is_available"] for item in cart["items"])
    steps_col, details_col, summary_col = st.columns([.85, 2.15, 1.3], gap="large")
    with steps_col:
        st.markdown(
            """
            <div class="rm-checkout-steps">
              <div class="rm-checkout-step"><span>1</span><div><b>Shipping Address</b>Select a saved address</div></div>
              <div class="rm-checkout-step"><span>2</span><div><b>Payment Method</b>Choose a saved method</div></div>
              <div class="rm-checkout-step"><span>3</span><div><b>Review Order</b>Confirm your details</div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with details_col:
        with st.container(border=True):
            st.markdown('<span class="rm-checkout-card-marker"></span>', unsafe_allow_html=True)
            st.subheader("Shipping Address")
            address_id = st.selectbox("Shipping address", list(address_map), index=list(address_map).index(default_address), format_func=lambda key: _address_label(address_map[key]))
            st.divider()
            st.subheader("Simulated Payment Method")
            payment_id = st.selectbox("Payment method", list(payment_map), index=list(payment_map).index(default_payment), format_func=lambda key: payment_map[key]["display_label"])
            st.caption("Classroom simulation only — no real payment credential is transmitted or processed.")
    with summary_col:
        with st.container(border=True):
            st.markdown('<span class="rm-summary-card-marker"></span>', unsafe_allow_html=True)
            st.subheader("Order Summary")
            for item in cart["items"]:
                st.markdown(f"**{item['product_name']}**")
                st.caption(f"{item['quantity']} × {_money(item['stored_unit_price_usd'])} · {_money(item['line_subtotal_usd'])}")
            st.markdown(
                f'<div class="rm-cart-summary-line rm-total"><span>Total</span><span>{_money(cart["cart_subtotal_usd"])}</span></div>',
                unsafe_allow_html=True,
            )
            if st.button("Place Order", type="primary", disabled=blocked, use_container_width=True):
                try:
                    order = client.post("/customer/checkout", {
                        "address_id": address_id, "payment_method_id": payment_id,
                        "cart_row_version": cart["row_version"],
                    })
                    st.session_state.checkout_confirmation = order
                    st.rerun()
                except APIError as exc:
                    show_api_error(exc)


def _delivery_confirmation_control(client: APIClient, order: dict, location: str) -> None:
    if order["order_status"] != "ready_shipped":
        return
    order_id = order["order_id"]
    pending_key = "customer_delivery_confirmation_id"
    if st.session_state.get(pending_key) != order_id:
        if st.button("Mark as Received", key=f"mark_received_{location}_{order_id}"):
            st.session_state[pending_key] = order_id
            st.rerun()
        return
    st.warning("Confirm that you have received this order?")
    confirm, dismiss = st.columns(2)
    if confirm.button("Confirm receipt", type="primary", key=f"confirm_received_{location}_{order_id}"):
        try:
            client.post(f"/customer/orders/{order_id}/confirm-delivery", {"row_version": order["row_version"]})
            st.session_state.pop(pending_key, None)
            st.session_state["delivery_confirmation_message"] = f"Order #{order_id} has been marked as delivered."
            st.rerun()
        except APIError as exc:
            show_api_error(exc)
    if dismiss.button("Not yet", key=f"dismiss_received_{location}_{order_id}"):
        st.session_state.pop(pending_key, None)
        st.rerun()


def _render_order_detail(client: APIClient, order_id: int) -> None:
    try:
        order = client.get(f"/customer/orders/{order_id}")
    except APIError as exc:
        show_api_error(exc)
        return
    if st.button("← Back to My Orders", key="orders_back"):
        st.session_state.pop("order_detail_id", None)
        st.rerun()
    page_header("Order Details", f"Order #{order['order_id']} · Placed {format_datetime(order['created_at'])}")
    with st.container(border=True):
        st.markdown('<span class="rm-order-card-marker"></span>', unsafe_allow_html=True)
        st.caption("Order Summary")
        st.subheader(f"Order #{order['order_id']}")
        status, payment, total = st.columns(3)
        with status:
            st.caption("Order status")
            status_badge(order["order_status"])
        with payment:
            st.caption("Payment status")
            status_badge(order["payment"]["payment_status"])
        total.metric("Total", _money(order["total_usd"]))
        if order["order_status"] == "delivered" and order.get("delivered_at"):
            st.caption(f"Received {format_datetime(order['delivered_at'])}")
        _delivery_confirmation_control(client, order, "detail")
    with st.container(border=True):
        st.markdown('<span class="rm-order-card-marker"></span>', unsafe_allow_html=True)
        st.subheader("Items")
        for item in order["items"]:
            product_col, quantity_col, total_col = st.columns([2.5, 1, 1], vertical_alignment="center")
            product_col.markdown(f"**{item['product_name']}**")
            quantity_col.caption(f"{item['quantity']} × {_money(item['unit_price_usd'])}")
            total_col.markdown(f"**{_money(item['line_total_usd'])}**")
    shipping = order["shipping"]
    shipping_col, payment_col = st.columns(2, gap="large")
    with shipping_col:
        with st.container(border=True):
            st.markdown('<span class="rm-account-card-marker"></span>', unsafe_allow_html=True)
            st.subheader("Shipping")
            st.markdown(f"**{shipping['recipient_first_name']} {shipping['recipient_last_name']}**")
            st.write(f"{shipping['address_line_1']}{', ' + shipping['address_line_2'] if shipping.get('address_line_2') else ''}")
            st.caption(f"{shipping['city']}, {shipping['province_region']} {shipping['postal_code']} · {shipping['country_code']}")
            st.caption("Shipping details saved with this order")
    with payment_col:
        with st.container(border=True):
            st.markdown('<span class="rm-account-card-marker"></span>', unsafe_allow_html=True)
            st.subheader("Payment")
            st.markdown(f"**{order['payment']['display_label']}**")
            status_badge(order["payment"]["payment_status"])
            st.caption("Payment method used · classroom simulation")
    order_status = order["order_status"]
    st.markdown("### Refund and cancellation")
    if order_status == "cancelled":
        st.info("Refund requests are not available for cancelled orders. Any prepaid simulated payment has already followed the cancellation refund policy.")
    elif order_status == "refunded":
        st.success("This order has been fully refunded. No further refund requests are available.")
    elif order_status in {"ready_shipped", "delivered"}:
        with st.expander("Review item eligibility or request a refund", expanded=False):
            try:
                candidates = client.get(f"/customer/orders/{order_id}/refund-eligibility")
            except APIError as exc:
                show_api_error(exc)
                candidates = []
            for candidate in candidates:
                with st.container(border=True):
                    st.markdown('<span class="rm-refund-card-marker"></span>', unsafe_allow_html=True)
                    st.markdown(f"**{candidate['product_name']}**")
                    purchased, remaining = st.columns(2)
                    purchased.caption("Purchased amount")
                    purchased.markdown(f"**{_money(candidate['item_price_usd'])}**")
                    remaining.caption("Remaining refundable")
                    remaining.markdown(f"**{_money(candidate['remaining_refundable_usd'])}**")
                    if candidate["eligible"]:
                        with st.form(f"refund_request_{candidate['order_item_id']}"):
                            amount_col, reason_col = st.columns([1, 2.2], vertical_alignment="bottom")
                            requested = amount_col.number_input(
                                "Requested amount",
                                min_value=0.01,
                                max_value=float(candidate["remaining_refundable_usd"]),
                                value=float(candidate["remaining_refundable_usd"]),
                                step=0.01,
                            )
                            reason = reason_col.text_input(
                                "Reason",
                                max_chars=1000,
                                placeholder="Briefly tell us what went wrong",
                            )
                            submit = st.form_submit_button("Request Refund", type="primary")
                        if submit:
                            try:
                                client.post("/customer/refund-requests", {
                                    "order_item_id": candidate["order_item_id"],
                                    "requested_amount": f"{requested:.2f}",
                                    "reason": reason,
                                })
                                st.success("Refund request submitted for review.")
                                st.rerun()
                            except APIError as exc:
                                show_api_error(exc)
                    elif candidate.get("current_request_status") == "pending":
                        st.info("Refund request pending")
                    else:
                        if candidate.get("current_request_status"):
                            status_badge(candidate["current_request_status"])
                        st.caption(candidate["reason"] or "This item is not currently eligible for a refund.")
    else:
        st.info("Refund requests become available once an eligible order is Ready / Shipped or Delivered.")
    if order["order_status"] == "pending":
        st.warning("Cancellation is allowed only while this order remains pending.")
        if st.button("Cancel pending order", key=f"cancel_order_{order_id}"):
            try:
                changed = client.post(f"/customer/orders/{order_id}/cancel", {"row_version": order["row_version"]})
                st.success(f"Order cancelled. Payment status: {format_status(changed['payment']['payment_status'])}.")
                st.rerun()
            except APIError as exc:
                show_api_error(exc)


def render_orders(client: APIClient) -> None:
    confirmation_message = st.session_state.pop("delivery_confirmation_message", None)
    if confirmation_message:
        st.success(confirmation_message)
    detail_id = st.session_state.get("order_detail_id")
    if detail_id:
        _render_order_detail(client, int(detail_id))
        return
    data_page_header("My Orders", "Review purchases, delivery details, payment status, and available actions.", "customer_orders")
    try:
        orders = client.get("/customer/orders")
    except APIError as exc:
        show_api_error(exc)
        return
    if not orders:
        st.info("You have not placed any orders yet.")
        return
    filters = ("All", "Pending", "Processing", "Ready / Shipped", "Delivered", "Cancelled", "Refunded")
    selected_status = st.radio(
        "Order status",
        filters,
        horizontal=True,
        label_visibility="collapsed",
        key="customer_order_status_filter",
    )
    visible_orders = orders if selected_status == "All" else [
        order for order in orders if format_status(order["order_status"]) == selected_status
    ]
    if not visible_orders:
        st.info(f"No {selected_status.lower()} orders.")
    for order in visible_orders:
        with st.container(border=True):
            st.markdown('<span class="rm-order-card-marker"></span>', unsafe_allow_html=True)
            heading, status, payment, total, action = st.columns([2.1, .85, 1.05, .85, .9], vertical_alignment="center")
            heading.markdown(f"**Order #{order['order_id']}**")
            heading.caption(f"{format_datetime(order['created_at'])} · {order['total_quantity']} unit(s)")
            with status:
                status_badge(order["order_status"])
            with payment:
                status_badge(order["payment_status"])
            total.markdown(f"**{_money(order['total_usd'])}**")
            if action.button("View Order", key=f"view_order_{order['order_id']}", use_container_width=True):
                st.session_state.order_detail_id = order["order_id"]
                st.rerun()
            _delivery_confirmation_control(client, order, "list")
    try:
        requests = client.get("/customer/refund-requests")
    except APIError as exc:
        show_api_error(exc)
        return
    with st.expander(f"Refund request history ({len(requests)})", expanded=False):
        if not requests:
            st.caption("You have not submitted any refund requests.")
        for request in requests:
            with st.container(border=True):
                st.markdown('<span class="rm-order-card-marker"></span>', unsafe_allow_html=True)
                title, request_status, amount = st.columns([2.4, 1, 1])
                title.write(f"**Request #{request['refund_request_id']} · {request['product_name']}**")
                title.caption(f"Order #{request['order_id']} · Submitted {format_datetime(request['created_at'])}")
                with request_status:
                    status_badge(request["status"])
                amount.write(f"**{_money(request['requested_amount'])}**")
                st.write(request["reason"])
                if request.get("resolution_note"):
                    st.info(f"Resolution: {request['resolution_note']}")
