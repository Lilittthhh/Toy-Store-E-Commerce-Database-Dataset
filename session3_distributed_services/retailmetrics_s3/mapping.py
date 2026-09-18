from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from google.protobuf.timestamp_pb2 import Timestamp

from .proto import retailmetrics_pb2 as pb


def _timestamp(value: str) -> Timestamp:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    result = Timestamp()
    result.FromDatetime(parsed)
    return result


def _iso(value: Timestamp) -> str:
    return value.ToDatetime(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def product_to_pb(v: dict[str, Any]) -> pb.Product:
    out = pb.Product(product_id=v["product_id"], product_name=v["product_name"])
    out.created_at.CopyFrom(_timestamp(v["created_at"]))
    return out


def product_from_pb(v: pb.Product) -> dict[str, Any]:
    return {"product_id": v.product_id, "created_at": _iso(v.created_at), "product_name": v.product_name}


def order_to_pb(v: dict[str, Any]) -> pb.Order:
    out = pb.Order(
        order_id=v["order_id"], website_session_id=v["website_session_id"],
        user_id=v["user_id"], items_purchased=v["items_purchased"],
        price_cents=v["price_cents"], cogs_cents=v["cogs_cents"],
    )
    out.created_at.CopyFrom(_timestamp(v["created_at"]))
    if v.get("primary_product_id") is not None:
        out.primary_product_id = v["primary_product_id"]
    return out


def order_from_pb(v: pb.Order) -> dict[str, Any]:
    return {
        "order_id": v.order_id, "created_at": _iso(v.created_at),
        "website_session_id": v.website_session_id, "user_id": v.user_id,
        "primary_product_id": v.primary_product_id if v.HasField("primary_product_id") else None,
        "items_purchased": v.items_purchased, "price_cents": v.price_cents,
        "cogs_cents": v.cogs_cents,
    }


def item_to_pb(v: dict[str, Any]) -> pb.OrderItem:
    out = pb.OrderItem(
        order_item_id=v["order_item_id"], order_id=v["order_id"],
        product_id=v["product_id"], price_cents=v["price_cents"],
        cogs_cents=v["cogs_cents"],
    )
    out.created_at.CopyFrom(_timestamp(v["created_at"]))
    if v.get("is_primary_item") is not None:
        out.is_primary_item = v["is_primary_item"]
    return out


def item_from_pb(v: pb.OrderItem) -> dict[str, Any]:
    return {
        "order_item_id": v.order_item_id, "created_at": _iso(v.created_at),
        "order_id": v.order_id, "product_id": v.product_id,
        "is_primary_item": v.is_primary_item if v.HasField("is_primary_item") else None,
        "price_cents": v.price_cents, "cogs_cents": v.cogs_cents,
    }


def refund_to_pb(v: dict[str, Any]) -> pb.Refund:
    out = pb.Refund(
        refund_id=v["refund_id"], order_item_id=v["order_item_id"],
        order_id=v["order_id"], refund_amount_cents=v["refund_amount_cents"],
    )
    out.created_at.CopyFrom(_timestamp(v["created_at"]))
    return out


def refund_from_pb(v: pb.Refund) -> dict[str, Any]:
    return {
        "refund_id": v.refund_id, "created_at": _iso(v.created_at),
        "order_item_id": v.order_item_id, "order_id": v.order_id,
        "refund_amount_cents": v.refund_amount_cents,
    }


def session_to_pb(v: dict[str, Any]) -> pb.WebsiteSession:
    out = pb.WebsiteSession(website_session_id=v["website_session_id"], user_id=v["user_id"])
    out.created_at.CopyFrom(_timestamp(v["created_at"]))
    for field in ("is_repeat_session", "utm_source", "utm_campaign", "utm_content", "device_type", "http_referer"):
        if v.get(field) is not None:
            setattr(out, field, v[field])
    return out


def session_from_pb(v: pb.WebsiteSession) -> dict[str, Any]:
    result = {"website_session_id": v.website_session_id, "created_at": _iso(v.created_at), "user_id": v.user_id}
    for field in ("is_repeat_session", "utm_source", "utm_campaign", "utm_content", "device_type", "http_referer"):
        result[field] = getattr(v, field) if v.HasField(field) else None
    return result


def metric_to_pb(v: dict[str, Any]) -> pb.SessionMetric:
    return pb.SessionMetric(**v)


def metric_from_pb(v: pb.SessionMetric) -> dict[str, Any]:
    return {
        "website_session_id": v.website_session_id, "pageview_count": v.pageview_count,
        "session_duration_seconds": v.session_duration_seconds, "converted": v.converted,
        "order_revenue_cents": v.order_revenue_cents,
        "gross_profit_cents": v.gross_profit_cents,
    }


def summary_to_pb(v: dict[str, Any]) -> pb.SalesSummary:
    return pb.SalesSummary(**v)


def summary_from_pb(v: pb.SalesSummary) -> dict[str, Any]:
    return {
        "session_count": v.session_count, "order_count": v.order_count,
        "conversion_count": v.conversion_count, "revenue_cents": v.revenue_cents,
        "gross_profit_cents": v.gross_profit_cents, "refund_cents": v.refund_cents,
        "conversion_rate": v.conversion_rate,
    }


def performance_to_pb(v: dict[str, Any]) -> pb.ProductPerformance:
    return pb.ProductPerformance(**v)


def performance_from_pb(v: pb.ProductPerformance) -> dict[str, Any]:
    return {field.name: getattr(v, field.name) for field in v.DESCRIPTOR.fields}

