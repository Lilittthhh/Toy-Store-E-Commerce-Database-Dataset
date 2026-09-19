from __future__ import annotations

import logging
from html import escape
from pathlib import Path
from string import Template

from psycopg2.extras import RealDictCursor

from core.config import Settings
from services.notifications.phone import normalize_ph_mobile
from services.notifications.providers import Message, ProviderFailure, provider_for


logger = logging.getLogger(__name__)
TEMPLATES = Path(__file__).resolve().parent / "templates"
ORDER_EVENTS = {"order_confirmation", "order_processing", "order_completed", "order_ready_shipped", "order_delivered", "order_cancelled"}
REFUND_EVENTS = {"refund_request_submitted", "refund_rejected", "refund_processed"}
EMAIL_EVENTS = {"order_confirmation", "order_processing", "order_completed", "order_ready_shipped", "order_delivered", "order_cancelled", "refund_rejected", "refund_processed"}


class NotificationOutbox:
    """Queue only owner-linked customer events in the caller's business transaction."""

    def __init__(self, conn, pending_ids: list[int]):
        self.conn = conn
        self.pending_ids = pending_ids

    def queue_order(self, event_type: str, order_id: int) -> None:
        if event_type not in ORDER_EVENTS:
            raise ValueError("Unknown order notification event")
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""SELECT o.customer_account_id,a.email,p.phone FROM public.orders o
                           JOIN public.customer_accounts a ON a.customer_account_id=o.customer_account_id
                           JOIN public.customer_profiles p ON p.customer_account_id=a.customer_account_id
                           WHERE o.order_id=%s AND o.record_origin='customer'""", (order_id,))
            owner = cur.fetchone()
            if owner:
                self._queue(cur, owner, event_type, order_id=order_id)

    def queue_refund(self, event_type: str, request_id: int) -> None:
        if event_type not in REFUND_EVENTS:
            raise ValueError("Unknown refund notification event")
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""SELECT a.customer_account_id,a.email,p.phone
                           FROM public.refund_requests rr
                           JOIN public.orders o ON o.order_id=rr.order_id
                             AND o.customer_account_id=rr.customer_account_id AND o.record_origin='customer'
                           JOIN public.customer_accounts a ON a.customer_account_id=rr.customer_account_id
                           JOIN public.customer_profiles p ON p.customer_account_id=a.customer_account_id
                           WHERE rr.refund_request_id=%s""", (request_id,))
            owner = cur.fetchone()
            if owner:
                self._queue(cur, owner, event_type, refund_request_id=request_id)

    def _queue(self, cur, owner, event_type: str, *, order_id: int | None = None,
               refund_request_id: int | None = None) -> None:
        destinations = [("sms", normalize_ph_mobile(owner["phone"]))]
        if event_type in EMAIL_EVENTS:
            destinations.insert(0, ("email", owner["email"]))
        for channel, recipient in destinations:
            if not recipient:
                continue
            cur.execute("""INSERT INTO public.notification_outbox
                       (customer_account_id,order_id,refund_request_id,event_type,channel,recipient_address)
                       VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING notification_id""",
                        (owner["customer_account_id"], order_id, refund_request_id,
                         event_type, channel, recipient))
            inserted = cur.fetchone()
            if inserted:
                self.pending_ids.append(int(inserted["notification_id"]))


def _order_content(cur, order_id: int) -> dict[str, str]:
    cur.execute("""SELECT o.order_id,o.created_at,o.order_status,o.price_usd,
                       s.recipient_first_name,s.recipient_last_name,s.address_line_1,
                       s.address_line_2,s.city,s.province_region,s.postal_code,s.country_code,
                       p.payment_display_snapshot,p.payment_status
                   FROM public.orders o
                   LEFT JOIN public.order_shipping_addresses s ON s.order_id=o.order_id
                   LEFT JOIN public.order_payments p ON p.order_id=o.order_id
                   WHERE o.order_id=%s AND o.record_origin='customer'""", (order_id,))
    row = cur.fetchone()
    if not row:
        raise ValueError("Notification order target unavailable")
    cur.execute("""SELECT pr.product_name,oi.price_usd,COUNT(*) AS quantity,
                          SUM(oi.price_usd) AS line_total
                   FROM public.order_items oi JOIN public.products pr ON pr.product_id=oi.product_id
                   WHERE oi.order_id=%s AND oi.record_origin='customer'
                   GROUP BY pr.product_name,oi.price_usd ORDER BY pr.product_name""", (order_id,))
    items = cur.fetchall()
    lines = "".join(
        f"<tr><td>{escape(str(item['product_name']))}</td><td>{item['quantity']}</td>"
        f"<td>${item['price_usd']:.2f}</td><td>${item['line_total']:.2f}</td></tr>"
        for item in items
    )
    styled_lines = "".join(
        "<tr>"
        f"<td style='padding:11px 8px;border-bottom:1px solid #e6ecef;color:#0b2746;word-break:break-word'>{escape(str(item['product_name']))}</td>"
        f"<td align='center' style='padding:11px 8px;border-bottom:1px solid #e6ecef;white-space:nowrap'>{int(item['quantity'])}</td>"
        f"<td align='right' style='padding:11px 8px;border-bottom:1px solid #e6ecef;white-space:nowrap'>${item['price_usd']:.2f}</td>"
        f"<td align='right' style='padding:11px 8px;border-bottom:1px solid #e6ecef;white-space:nowrap;font-weight:600'>${item['line_total']:.2f}</td>"
        "</tr>"
        for item in items
    )
    plain_lines = "\n".join(
        f"- {item['product_name']} | Qty {int(item['quantity'])} | "
        f"Unit ${item['price_usd']:.2f} | Total ${item['line_total']:.2f}"
        for item in items
    )
    address = ", ".join(str(row[key]) for key in
                        ("address_line_1", "address_line_2", "city", "province_region", "postal_code", "country_code")
                        if row[key])
    return {
        "order_id": str(order_id), "name": escape(
            f"{row['recipient_first_name']} {row['recipient_last_name']}"
            if row["recipient_first_name"] and row["recipient_last_name"] else "Customer"),
        "date": escape(row["created_at"].strftime("%d %b %Y, %I:%M %p")),
        "items": lines, "items_styled": styled_lines, "items_plain": plain_lines,
        "total": f"${row['price_usd']:.2f}",
        "shipping": escape(address or "Not available"),
        "payment": escape(str(row["payment_display_snapshot"] or "Not available")),
        "payment_status": escape(str(row["payment_status"] or "Not available").replace("_", " ").title()),
        "status": escape("Ready / Shipped" if row["order_status"] == "ready_shipped" else str(row["order_status"]).replace("_", " ").title()),
    }


def _refund_content(cur, request_id: int) -> dict[str, str]:
    cur.execute("""SELECT rr.refund_request_id,rr.order_id,rr.request_status,rr.requested_amount_usd,
                          rr.reviewed_at,pr.product_name,a.first_name,a.last_name,
                          rf.refund_amount_usd,rf.created_at AS refund_date
                   FROM public.refund_requests rr
                   JOIN public.customer_profiles a ON a.customer_account_id=rr.customer_account_id
                   JOIN public.order_items oi ON oi.order_item_id=rr.order_item_id
                   JOIN public.products pr ON pr.product_id=oi.product_id
                   LEFT JOIN public.order_item_refunds rf ON rf.refund_request_id=rr.refund_request_id
                   WHERE rr.refund_request_id=%s""", (request_id,))
    row = cur.fetchone()
    if not row:
        raise ValueError("Notification refund target unavailable")
    when = row["refund_date"] or row["reviewed_at"]
    return {
        "request_id": str(request_id), "order_id": str(row["order_id"]),
        "name": escape(f"{row['first_name']} {row['last_name']}"),
        "product": escape(str(row["product_name"])),
        "amount": f"${(row['refund_amount_usd'] or row['requested_amount_usd']):.2f}",
        "date": escape(when.strftime("%d %b %Y, %I:%M %p") if when else "Pending"),
        "status": escape(str(row["request_status"]).title()),
    }


def render_message(cur, row) -> Message:
    event = row["event_type"]
    content = _order_content(cur, row["order_id"]) if event in ORDER_EVENTS else _refund_content(cur, row["refund_request_id"])
    order_number = content["order_id"]
    request_number = content.get("request_id")
    sms = {
        "order_confirmation": f"RetailMetrics: Order #{order_number} has been received and is Pending.",
        "order_processing": f"RetailMetrics: Order #{order_number} is now being processed.",
        "order_completed": f"RetailMetrics: Order #{order_number} is Ready / Shipped. Mark it received after delivery.",
        "order_ready_shipped": f"RetailMetrics: Order #{order_number} is Ready / Shipped. Mark it received after delivery.",
        "order_delivered": f"RetailMetrics: Order #{order_number} has been marked Delivered. Thank you.",
        "order_cancelled": f"RetailMetrics: Order #{order_number} was cancelled.",
        "refund_request_submitted": f"RetailMetrics: Refund request #{request_number} for Order #{order_number} was received.",
        "refund_rejected": f"RetailMetrics: Refund request #{request_number} for Order #{order_number} was not approved. Check My Orders for details.",
        "refund_processed": f"RetailMetrics: Refund request #{request_number} for Order #{order_number} has been Refunded.",
    }
    if row["channel"] == "sms":
        return Message(event, "sms", row["recipient_address"], None, sms[event])
    subjects = {
        "order_confirmation": f"RetailMetrics Order Confirmation #{order_number}",
        "order_processing": f"RetailMetrics Order Update #{order_number}",
        "order_completed": f"RetailMetrics Order Shipped #{order_number}",
        "order_ready_shipped": f"RetailMetrics Order Shipped #{order_number}",
        "order_delivered": f"RetailMetrics Delivery Confirmation #{order_number}",
        "order_cancelled": f"RetailMetrics Cancellation Confirmation #{order_number}",
        "refund_rejected": f"RetailMetrics Refund Decision #{request_number}",
        "refund_processed": f"RetailMetrics Refund Receipt #{request_number}",
    }
    status_copy = {
        "order_processing": (
            "Your order is being processed",
            "We've started preparing your order.",
        ),
        "order_completed": (
            "Your order is ready / shipped",
            "Your order has finished processing and has been released for delivery. Once you receive it, open RetailMetrics and select &quot;Mark as Received&quot;.",
        ),
        "order_ready_shipped": (
            "Your order is ready / shipped",
            "Your order has finished processing and has been released for delivery. Once you receive it, open RetailMetrics and select &quot;Mark as Received&quot;.",
        ),
        "order_delivered": (
            "Order received",
            "Thank you for confirming that you received your order.",
        ),
        "order_cancelled": (
            "Order cancelled",
            "Your order has been cancelled. Review your order in RetailMetrics for its simulated payment status.",
        ),
    }
    if event == "order_confirmation":
        template_file = TEMPLATES / "order_confirmation.html"
        template_content = {**content, "items": content["items_styled"]}
    elif event in status_copy:
        template_file = TEMPLATES / "order_status.html"
        heading, lead = status_copy[event]
        template_content = {**content, "heading": heading, "lead": lead}
    else:
        template_file = TEMPLATES / f"{event}.html"
        template_content = content
    html = Template(template_file.read_text(encoding="utf-8")).substitute(template_content)
    plain_body = None
    if event == "order_confirmation":
        from html import unescape

        plain_body = (
            "RetailMetrics — Toy Store Intelligence\n\n"
            "Order confirmed\n"
            "Thank you for your order. We've received your purchase and it is now being processed.\n\n"
            f"Hello {unescape(content['name'])},\n"
            f"Order number: #{content['order_id']}\n"
            f"Order date/time: {unescape(content['date'])}\n"
            f"Order status: {unescape(content['status'])}\n\n"
            "Items\n"
            f"{content['items_plain']}\n\n"
            f"Order total: {content['total']}\n\n"
            f"Shipping address: {unescape(content['shipping'])}\n"
            f"Simulated payment method: {unescape(content['payment'])}\n"
            f"Payment status: {unescape(content['payment_status'])}\n\n"
            "This email was generated automatically by RetailMetrics.\n"
            "Please keep this email for your records."
        )
    elif event in status_copy:
        from html import unescape

        heading, lead = status_copy[event]
        plain_body = (
            "RetailMetrics — Toy Store Intelligence\n\n"
            f"{heading}\n{unescape(lead)}\n\n"
            f"Hello {unescape(content['name'])},\n"
            f"Order number: #{content['order_id']}\n"
            f"Order date/time: {unescape(content['date'])}\n"
            f"Order total: {content['total']}\n"
            f"Order status: {unescape(content['status'])}\n"
            f"Simulated payment: {unescape(content['payment'])} ({unescape(content['payment_status'])})\n\n"
            "This email was generated automatically by RetailMetrics.\n"
            "Please keep this email for your records."
        )
    elif event in {"refund_rejected", "refund_processed"}:
        from html import unescape

        outcome = (
            f"Refund request #{request_number} for Order #{order_number} was not approved.\n"
            "See My Orders for details."
            if event == "refund_rejected" else
            f"Refund request #{request_number} for Order #{order_number} has been processed."
        )
        amount_label = "Requested amount" if event == "refund_rejected" else "Refund amount"
        date_label = "Decision date" if event == "refund_rejected" else "Processed"
        plain_body = (
            "RetailMetrics — Toy Store Intelligence\n\n"
            f"Hello {unescape(content['name'])},\n{outcome}\n\n"
            f"Product: {unescape(content['product'])}\n"
            f"{amount_label}: {content['amount']}\n"
            f"{date_label}: {unescape(content['date'])}\n"
            f"Status: {unescape(content['status'])}\n\n"
            "This email was generated automatically by RetailMetrics.\n"
            "Please keep this email for your records."
        )
    if plain_body is not None:
        plain_body += "\n\nPrepared by Rehanie Utto\nRetailMetrics"
    return Message(event, "email", row["recipient_address"], subjects[event], html, plain_body)


def dispatch_ids(conn, ids: list[int], settings: Settings) -> dict[int, str]:
    """Claim committed rows once. Never auto-retry failed/uncertain attempts."""
    outcomes: dict[int, str] = {}
    for notification_id in dict.fromkeys(ids):
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""UPDATE public.notification_outbox
                           SET delivery_status='sending',attempt_count=attempt_count+1,last_attempt_at=NOW()
                           WHERE notification_id=%s AND delivery_status='pending'
                           RETURNING *""", (notification_id,))
            row = cur.fetchone()
        conn.commit()  # The claim is durable before any external side effect.
        if not row:
            continue
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                message = render_message(cur, row)
            conn.rollback()  # Rendering is read-only; do not hold a transaction over HTTP.
            provider = provider_for(settings)
            result = provider.send_email(message) if row["channel"] == "email" else provider.send_sms(message)
            status, code, message_id = "sent", None, result.message_id
            logger.info("notification delivered id=%s event=%s channel=%s mode=%s",
                        notification_id, row["event_type"], row["channel"], settings.notification_mode)
        except ProviderFailure as exc:
            status, code, message_id = "failed", exc.code, None
        except Exception:
            status, code, message_id = "failed", "NOTIFICATION_DISPATCH_FAILED", None
            logger.exception("notification dispatch failed id=%s", notification_id)
        with conn.cursor() as cur:
            cur.execute("""UPDATE public.notification_outbox SET delivery_status=%s,
                           sent_at=CASE WHEN %s='sent' THEN NOW() ELSE NULL END,
                           provider_message_id=%s,error_code=%s
                           WHERE notification_id=%s AND delivery_status='sending'""",
                        (status, status, message_id, code, notification_id))
        conn.commit()
        outcomes[notification_id] = status
    return outcomes
