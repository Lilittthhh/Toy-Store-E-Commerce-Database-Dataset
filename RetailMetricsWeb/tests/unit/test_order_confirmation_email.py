from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from email.message import EmailMessage
from html.parser import HTMLParser

from core.config import Settings
from services.notifications.outbox import render_message
from services.notifications.password_reset import password_reset_message
from services.notifications.providers import SmtpEmailProvider


class OrderCursor:
    def __init__(self, status: str = "pending"):
        self.query_count = 0
        self.status = status

    def execute(self, query, params):
        self.query_count += 1
        assert params == (4312,)

    def fetchone(self):
        assert self.query_count == 1
        return {
            "order_id": 4312,
            "created_at": datetime(2026, 9, 19, 2, 45, tzinfo=timezone.utc),
            "order_status": self.status,
            "price_usd": Decimal("129.97"),
            "recipient_first_name": "Ada",
            "recipient_last_name": "Lovelace",
            "address_line_1": "42 Toy Lane",
            "address_line_2": None,
            "city": "Manila",
            "province_region": "Metro Manila",
            "postal_code": "1000",
            "country_code": "PH",
            "payment_display_snapshot": "Simulated Visa ending 4242",
            "payment_status": "paid",
        }

    def fetchall(self):
        assert self.query_count == 2
        return [
            {"product_name": "Mr. Fuzzy & Friends", "price_usd": Decimal("49.99"),
             "quantity": 2, "line_total": Decimal("99.98")},
            {"product_name": "Mini bear", "price_usd": Decimal("29.99"),
             "quantity": 1, "line_total": Decimal("29.99")},
        ]


class RefundCursor:
    def __init__(self, event: str):
        self.event = event

    def execute(self, query, params):
        assert params == (77,)

    def fetchone(self):
        return {
            "refund_request_id": 77,
            "order_id": 4312,
            "request_status": "rejected" if self.event == "refund_rejected" else "processed",
            "requested_amount_usd": Decimal("9.99"),
            "reviewed_at": datetime(2026, 9, 19, 2, 45, tzinfo=timezone.utc),
            "product_name": "Mr. Fuzzy & Friends",
            "first_name": "Ada",
            "last_name": "Lovelace",
            "refund_amount_usd": None if self.event == "refund_rejected" else Decimal("9.99"),
            "refund_date": None if self.event == "refund_rejected" else datetime(2026, 9, 19, 2, 45, tzinfo=timezone.utc),
        }


class ItemTableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_body = False
        self.in_row = False
        self.in_cell = False
        self.current_cell = ""
        self.current_row = []
        self.rows = []

    def handle_starttag(self, tag, attrs):
        if tag == "tbody":
            self.in_body = True
        elif self.in_body and tag == "tr":
            self.in_row = True
            self.current_row = []
        elif self.in_row and tag == "td":
            self.in_cell = True
            self.current_cell = ""

    def handle_data(self, data):
        if self.in_cell:
            self.current_cell += data

    def handle_endtag(self, tag):
        if tag == "td" and self.in_cell:
            self.current_row.append(self.current_cell.strip())
            self.in_cell = False
        elif tag == "tr" and self.in_row:
            self.rows.append(self.current_row)
            self.in_row = False
        elif tag == "tbody":
            self.in_body = False


def confirmation_message():
    return render_message(OrderCursor(), {
        "event_type": "order_confirmation",
        "channel": "email",
        "order_id": 4312,
        "recipient_address": "customer@example.invalid",
    })


def status_message(event: str, status: str):
    return render_message(OrderCursor(status), {
        "event_type": event,
        "channel": "email",
        "order_id": 4312,
        "recipient_address": "customer@example.invalid",
    })


def test_order_status_emails_use_branded_html_and_plain_text_without_network():
    for event, status, subject, heading, message_text in (
        ("order_processing", "processing", "RetailMetrics Order Update #4312",
         "Your order is being processed", "We've started preparing your order."),
        ("order_ready_shipped", "ready_shipped", "RetailMetrics Order Shipped #4312",
         "Your order is ready / shipped", "Mark as Received"),
        ("order_delivered", "delivered", "RetailMetrics Delivery Confirmation #4312",
         "Order received", "Thank you for confirming that you received your order."),
        ("order_cancelled", "cancelled", "RetailMetrics Cancellation Confirmation #4312",
         "Order cancelled", "Your order has been cancelled."),
    ):
        rendered = status_message(event, status)
        assert rendered.subject == subject
        assert rendered.plain_body is not None
        for value in ("RetailMetrics", "Toy Store Intelligence", heading, "#4312", "$129.97"):
            assert value in rendered.body
            assert value in rendered.plain_body
        assert message_text in rendered.plain_body
        for value in ("background:#f6f8f8", "background:#ffffff", "color:#0f766e", "border-radius:12px"):
            assert value in rendered.body
        assert "19 Sep 2026, 02:45 AM" in rendered.body
        assert "Simulated Visa ending 4242" in rendered.body
        assert "<script" not in rendered.body.lower()
    assert "Ready / Shipped" in status_message("order_ready_shipped", "ready_shipped").body


def test_legacy_completed_event_renders_as_shipped_not_final_receipt():
    rendered = status_message("order_completed", "ready_shipped")
    assert rendered.subject == "RetailMetrics Order Shipped #4312"
    assert "Your order is ready / shipped" in rendered.body


def test_transaction_email_preparer_footer_is_last_and_has_plain_text():
    messages = [confirmation_message()] + [
        status_message(event, status)
        for event, status in (
            ("order_processing", "processing"),
            ("order_ready_shipped", "ready_shipped"),
            ("order_delivered", "delivered"),
            ("order_cancelled", "cancelled"),
        )
    ]
    for event in ("refund_rejected", "refund_processed"):
        messages.append(render_message(RefundCursor(event), {
            "event_type": event, "channel": "email", "refund_request_id": 77,
            "recipient_address": "customer@example.invalid",
        }))
    for message in messages:
        assert message.body.count("Prepared by Rehanie Utto") == 1
        assert message.body.rfind("Prepared by Rehanie Utto") > message.body.rfind("Please keep this email")
        assert '<strong style="color:#0f766e;">Prepared by Rehanie Utto</strong><br>RetailMetrics' in message.body
        assert message.plain_body is not None
        assert message.plain_body.endswith("Prepared by Rehanie Utto\nRetailMetrics")
    assert "RetailMetrics Refund Decision #77" == messages[-2].subject
    assert "RetailMetrics Refund Receipt #77" == messages[-1].subject
    assert "Mr. Fuzzy &amp; Friends" in messages[-1].body
    assert "Mr. Fuzzy & Friends" in messages[-1].plain_body


def test_password_reset_email_has_no_transaction_preparer_footer():
    reset = password_reset_message("customer@example.invalid", "unit-test-token", 15, "customer")
    assert "Prepared by Rehanie Utto" not in reset.body
    assert reset.plain_body is None or "Prepared by Rehanie Utto" not in reset.plain_body


def test_order_confirmation_html_has_all_real_fields_and_aligned_item_rows():
    message = confirmation_message()
    assert message.subject == "RetailMetrics Order Confirmation #4312"
    assert message.recipient == "customer@example.invalid"
    assert "RetailMetrics" in message.body
    assert "Toy Store Intelligence" in message.body
    assert "Order confirmed" in message.body
    assert "Thank you for your order. We've received your purchase and it is now being processed." in message.body
    for value in (
        "Ada Lovelace", "#4312", "19 Sep 2026, 02:45 AM", "Pending",
        "$129.97", "42 Toy Lane, Manila, Metro Manila, 1000, PH",
        "Simulated Visa ending 4242", "Paid", "Shipping address",
        "Simulated payment method", "Please keep this email for your records.",
    ):
        assert value in message.body
    assert "Mr. Fuzzy &amp; Friends" in message.body
    assert "background:#f6f8f8" in message.body
    assert "background:#ffffff" in message.body
    assert "color:#0f766e" in message.body
    assert "<script" not in message.body.lower()

    parser = ItemTableParser()
    parser.feed(message.body)
    assert parser.rows == [
        ["Mr. Fuzzy & Friends", "2", "$49.99", "$99.98"],
        ["Mini bear", "1", "$29.99", "$29.99"],
    ]


def test_order_confirmation_plain_text_fallback_contains_complete_invoice():
    message = confirmation_message()
    assert message.plain_body is not None
    for value in (
        "Order confirmed", "Ada Lovelace", "#4312", "19 Sep 2026, 02:45 AM",
        "Pending", "Mr. Fuzzy & Friends | Qty 2 | Unit $49.99 | Total $99.98",
        "Mini bear | Qty 1 | Unit $29.99 | Total $29.99",
        "Order total: $129.97", "42 Toy Lane, Manila, Metro Manila, 1000, PH",
        "Simulated Visa ending 4242", "Payment status: Paid",
        "This email was generated automatically by RetailMetrics.",
        "Please keep this email for your records.",
    ):
        assert value in message.plain_body


def test_smtp_builds_multipart_email_with_invoice_fallback_without_network():
    captured: list[EmailMessage] = []

    class FakeSmtp:
        def __init__(self, host, port, timeout):
            assert (host, port, timeout) == ("smtp.gmail.com", 587, 10)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def ehlo(self):
            pass

        def starttls(self, *, context):
            assert context is not None

        def login(self, username, password):
            assert (username, password) == ("sender@example.invalid", "unit-test-only")

        def send_message(self, email):
            captured.append(email)

    settings = Settings(
        smtp_host="smtp.gmail.com", smtp_port=587,
        smtp_username="sender@example.invalid", smtp_password="unit-test-only",
        smtp_from_email="sender@example.invalid", smtp_live_send_enabled=True,
    )
    SmtpEmailProvider(settings, smtp_factory=FakeSmtp).send_email(confirmation_message())
    assert len(captured) == 1
    email = captured[0]
    assert email["Subject"] == "RetailMetrics Order Confirmation #4312"
    plain, html = email.iter_parts()
    assert plain.get_content_type() == "text/plain"
    assert "Order total: $129.97" in plain.get_content()
    assert html.get_content_type() == "text/html"
    assert "Order confirmed" in html.get_content()
