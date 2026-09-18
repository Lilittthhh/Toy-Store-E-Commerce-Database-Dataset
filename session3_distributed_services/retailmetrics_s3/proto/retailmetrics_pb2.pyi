import datetime

from google.protobuf import empty_pb2 as _empty_pb2
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class PageRequest(_message.Message):
    __slots__ = ("limit", "offset")
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    limit: int
    offset: int
    def __init__(self, limit: _Optional[int] = ..., offset: _Optional[int] = ...) -> None: ...

class ProductIdRequest(_message.Message):
    __slots__ = ("product_id",)
    PRODUCT_ID_FIELD_NUMBER: _ClassVar[int]
    product_id: int
    def __init__(self, product_id: _Optional[int] = ...) -> None: ...

class Product(_message.Message):
    __slots__ = ("product_id", "created_at", "product_name")
    PRODUCT_ID_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    PRODUCT_NAME_FIELD_NUMBER: _ClassVar[int]
    product_id: int
    created_at: _timestamp_pb2.Timestamp
    product_name: str
    def __init__(self, product_id: _Optional[int] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., product_name: _Optional[str] = ...) -> None: ...

class ProductList(_message.Message):
    __slots__ = ("products", "total")
    PRODUCTS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_FIELD_NUMBER: _ClassVar[int]
    products: _containers.RepeatedCompositeFieldContainer[Product]
    total: int
    def __init__(self, products: _Optional[_Iterable[_Union[Product, _Mapping]]] = ..., total: _Optional[int] = ...) -> None: ...

class OrderIdRequest(_message.Message):
    __slots__ = ("order_id",)
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    order_id: int
    def __init__(self, order_id: _Optional[int] = ...) -> None: ...

class OrderBatchRequest(_message.Message):
    __slots__ = ("order_ids",)
    ORDER_IDS_FIELD_NUMBER: _ClassVar[int]
    order_ids: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, order_ids: _Optional[_Iterable[int]] = ...) -> None: ...

class Order(_message.Message):
    __slots__ = ("order_id", "created_at", "website_session_id", "user_id", "primary_product_id", "items_purchased", "price_cents", "cogs_cents")
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    WEBSITE_SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    PRIMARY_PRODUCT_ID_FIELD_NUMBER: _ClassVar[int]
    ITEMS_PURCHASED_FIELD_NUMBER: _ClassVar[int]
    PRICE_CENTS_FIELD_NUMBER: _ClassVar[int]
    COGS_CENTS_FIELD_NUMBER: _ClassVar[int]
    order_id: int
    created_at: _timestamp_pb2.Timestamp
    website_session_id: int
    user_id: int
    primary_product_id: int
    items_purchased: int
    price_cents: int
    cogs_cents: int
    def __init__(self, order_id: _Optional[int] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., website_session_id: _Optional[int] = ..., user_id: _Optional[int] = ..., primary_product_id: _Optional[int] = ..., items_purchased: _Optional[int] = ..., price_cents: _Optional[int] = ..., cogs_cents: _Optional[int] = ...) -> None: ...

class OrderBatch(_message.Message):
    __slots__ = ("orders", "total")
    ORDERS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_FIELD_NUMBER: _ClassVar[int]
    orders: _containers.RepeatedCompositeFieldContainer[Order]
    total: int
    def __init__(self, orders: _Optional[_Iterable[_Union[Order, _Mapping]]] = ..., total: _Optional[int] = ...) -> None: ...

class OrderItemIdRequest(_message.Message):
    __slots__ = ("order_item_id",)
    ORDER_ITEM_ID_FIELD_NUMBER: _ClassVar[int]
    order_item_id: int
    def __init__(self, order_item_id: _Optional[int] = ...) -> None: ...

class OrderItemsRequest(_message.Message):
    __slots__ = ("order_id", "limit", "offset")
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    order_id: int
    limit: int
    offset: int
    def __init__(self, order_id: _Optional[int] = ..., limit: _Optional[int] = ..., offset: _Optional[int] = ...) -> None: ...

class OrderItem(_message.Message):
    __slots__ = ("order_item_id", "created_at", "order_id", "product_id", "is_primary_item", "price_cents", "cogs_cents")
    ORDER_ITEM_ID_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    PRODUCT_ID_FIELD_NUMBER: _ClassVar[int]
    IS_PRIMARY_ITEM_FIELD_NUMBER: _ClassVar[int]
    PRICE_CENTS_FIELD_NUMBER: _ClassVar[int]
    COGS_CENTS_FIELD_NUMBER: _ClassVar[int]
    order_item_id: int
    created_at: _timestamp_pb2.Timestamp
    order_id: int
    product_id: int
    is_primary_item: int
    price_cents: int
    cogs_cents: int
    def __init__(self, order_item_id: _Optional[int] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., order_id: _Optional[int] = ..., product_id: _Optional[int] = ..., is_primary_item: _Optional[int] = ..., price_cents: _Optional[int] = ..., cogs_cents: _Optional[int] = ...) -> None: ...

class OrderItemList(_message.Message):
    __slots__ = ("items", "total")
    ITEMS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_FIELD_NUMBER: _ClassVar[int]
    items: _containers.RepeatedCompositeFieldContainer[OrderItem]
    total: int
    def __init__(self, items: _Optional[_Iterable[_Union[OrderItem, _Mapping]]] = ..., total: _Optional[int] = ...) -> None: ...

class RefundIdRequest(_message.Message):
    __slots__ = ("refund_id",)
    REFUND_ID_FIELD_NUMBER: _ClassVar[int]
    refund_id: int
    def __init__(self, refund_id: _Optional[int] = ...) -> None: ...

class RefundsRequest(_message.Message):
    __slots__ = ("order_id", "limit", "offset")
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    order_id: int
    limit: int
    offset: int
    def __init__(self, order_id: _Optional[int] = ..., limit: _Optional[int] = ..., offset: _Optional[int] = ...) -> None: ...

class Refund(_message.Message):
    __slots__ = ("refund_id", "created_at", "order_item_id", "order_id", "refund_amount_cents")
    REFUND_ID_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    ORDER_ITEM_ID_FIELD_NUMBER: _ClassVar[int]
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    REFUND_AMOUNT_CENTS_FIELD_NUMBER: _ClassVar[int]
    refund_id: int
    created_at: _timestamp_pb2.Timestamp
    order_item_id: int
    order_id: int
    refund_amount_cents: int
    def __init__(self, refund_id: _Optional[int] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., order_item_id: _Optional[int] = ..., order_id: _Optional[int] = ..., refund_amount_cents: _Optional[int] = ...) -> None: ...

class RefundList(_message.Message):
    __slots__ = ("refunds", "total")
    REFUNDS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_FIELD_NUMBER: _ClassVar[int]
    refunds: _containers.RepeatedCompositeFieldContainer[Refund]
    total: int
    def __init__(self, refunds: _Optional[_Iterable[_Union[Refund, _Mapping]]] = ..., total: _Optional[int] = ...) -> None: ...

class SessionIdRequest(_message.Message):
    __slots__ = ("website_session_id",)
    WEBSITE_SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    website_session_id: int
    def __init__(self, website_session_id: _Optional[int] = ...) -> None: ...

class SessionBatchRequest(_message.Message):
    __slots__ = ("website_session_ids",)
    WEBSITE_SESSION_IDS_FIELD_NUMBER: _ClassVar[int]
    website_session_ids: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, website_session_ids: _Optional[_Iterable[int]] = ...) -> None: ...

class WebsiteSession(_message.Message):
    __slots__ = ("website_session_id", "created_at", "user_id", "is_repeat_session", "utm_source", "utm_campaign", "utm_content", "device_type", "http_referer")
    WEBSITE_SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    IS_REPEAT_SESSION_FIELD_NUMBER: _ClassVar[int]
    UTM_SOURCE_FIELD_NUMBER: _ClassVar[int]
    UTM_CAMPAIGN_FIELD_NUMBER: _ClassVar[int]
    UTM_CONTENT_FIELD_NUMBER: _ClassVar[int]
    DEVICE_TYPE_FIELD_NUMBER: _ClassVar[int]
    HTTP_REFERER_FIELD_NUMBER: _ClassVar[int]
    website_session_id: int
    created_at: _timestamp_pb2.Timestamp
    user_id: int
    is_repeat_session: int
    utm_source: str
    utm_campaign: str
    utm_content: str
    device_type: str
    http_referer: str
    def __init__(self, website_session_id: _Optional[int] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., user_id: _Optional[int] = ..., is_repeat_session: _Optional[int] = ..., utm_source: _Optional[str] = ..., utm_campaign: _Optional[str] = ..., utm_content: _Optional[str] = ..., device_type: _Optional[str] = ..., http_referer: _Optional[str] = ...) -> None: ...

class SessionBatch(_message.Message):
    __slots__ = ("sessions", "total")
    SESSIONS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_FIELD_NUMBER: _ClassVar[int]
    sessions: _containers.RepeatedCompositeFieldContainer[WebsiteSession]
    total: int
    def __init__(self, sessions: _Optional[_Iterable[_Union[WebsiteSession, _Mapping]]] = ..., total: _Optional[int] = ...) -> None: ...

class SessionMetricsRequest(_message.Message):
    __slots__ = ("limit", "after_session_id")
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    AFTER_SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    limit: int
    after_session_id: int
    def __init__(self, limit: _Optional[int] = ..., after_session_id: _Optional[int] = ...) -> None: ...

class SessionMetric(_message.Message):
    __slots__ = ("website_session_id", "pageview_count", "session_duration_seconds", "converted", "order_revenue_cents", "gross_profit_cents")
    WEBSITE_SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    PAGEVIEW_COUNT_FIELD_NUMBER: _ClassVar[int]
    SESSION_DURATION_SECONDS_FIELD_NUMBER: _ClassVar[int]
    CONVERTED_FIELD_NUMBER: _ClassVar[int]
    ORDER_REVENUE_CENTS_FIELD_NUMBER: _ClassVar[int]
    GROSS_PROFIT_CENTS_FIELD_NUMBER: _ClassVar[int]
    website_session_id: int
    pageview_count: int
    session_duration_seconds: float
    converted: bool
    order_revenue_cents: int
    gross_profit_cents: int
    def __init__(self, website_session_id: _Optional[int] = ..., pageview_count: _Optional[int] = ..., session_duration_seconds: _Optional[float] = ..., converted: _Optional[bool] = ..., order_revenue_cents: _Optional[int] = ..., gross_profit_cents: _Optional[int] = ...) -> None: ...

class SessionMetricList(_message.Message):
    __slots__ = ("metrics", "total")
    METRICS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_FIELD_NUMBER: _ClassVar[int]
    metrics: _containers.RepeatedCompositeFieldContainer[SessionMetric]
    total: int
    def __init__(self, metrics: _Optional[_Iterable[_Union[SessionMetric, _Mapping]]] = ..., total: _Optional[int] = ...) -> None: ...

class SalesSummary(_message.Message):
    __slots__ = ("session_count", "order_count", "conversion_count", "revenue_cents", "gross_profit_cents", "refund_cents", "conversion_rate")
    SESSION_COUNT_FIELD_NUMBER: _ClassVar[int]
    ORDER_COUNT_FIELD_NUMBER: _ClassVar[int]
    CONVERSION_COUNT_FIELD_NUMBER: _ClassVar[int]
    REVENUE_CENTS_FIELD_NUMBER: _ClassVar[int]
    GROSS_PROFIT_CENTS_FIELD_NUMBER: _ClassVar[int]
    REFUND_CENTS_FIELD_NUMBER: _ClassVar[int]
    CONVERSION_RATE_FIELD_NUMBER: _ClassVar[int]
    session_count: int
    order_count: int
    conversion_count: int
    revenue_cents: int
    gross_profit_cents: int
    refund_cents: int
    conversion_rate: float
    def __init__(self, session_count: _Optional[int] = ..., order_count: _Optional[int] = ..., conversion_count: _Optional[int] = ..., revenue_cents: _Optional[int] = ..., gross_profit_cents: _Optional[int] = ..., refund_cents: _Optional[int] = ..., conversion_rate: _Optional[float] = ...) -> None: ...

class ProductPerformanceRequest(_message.Message):
    __slots__ = ("limit",)
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    limit: int
    def __init__(self, limit: _Optional[int] = ...) -> None: ...

class ProductPerformance(_message.Message):
    __slots__ = ("product_id", "product_name", "order_count", "units", "revenue_cents", "cogs_cents", "refund_cents", "net_revenue_cents")
    PRODUCT_ID_FIELD_NUMBER: _ClassVar[int]
    PRODUCT_NAME_FIELD_NUMBER: _ClassVar[int]
    ORDER_COUNT_FIELD_NUMBER: _ClassVar[int]
    UNITS_FIELD_NUMBER: _ClassVar[int]
    REVENUE_CENTS_FIELD_NUMBER: _ClassVar[int]
    COGS_CENTS_FIELD_NUMBER: _ClassVar[int]
    REFUND_CENTS_FIELD_NUMBER: _ClassVar[int]
    NET_REVENUE_CENTS_FIELD_NUMBER: _ClassVar[int]
    product_id: int
    product_name: str
    order_count: int
    units: int
    revenue_cents: int
    cogs_cents: int
    refund_cents: int
    net_revenue_cents: int
    def __init__(self, product_id: _Optional[int] = ..., product_name: _Optional[str] = ..., order_count: _Optional[int] = ..., units: _Optional[int] = ..., revenue_cents: _Optional[int] = ..., cogs_cents: _Optional[int] = ..., refund_cents: _Optional[int] = ..., net_revenue_cents: _Optional[int] = ...) -> None: ...

class ProductPerformanceList(_message.Message):
    __slots__ = ("products",)
    PRODUCTS_FIELD_NUMBER: _ClassVar[int]
    products: _containers.RepeatedCompositeFieldContainer[ProductPerformance]
    def __init__(self, products: _Optional[_Iterable[_Union[ProductPerformance, _Mapping]]] = ...) -> None: ...

class DelayRequest(_message.Message):
    __slots__ = ("delay_ms",)
    DELAY_MS_FIELD_NUMBER: _ClassVar[int]
    delay_ms: int
    def __init__(self, delay_ms: _Optional[int] = ...) -> None: ...

class DelayResult(_message.Message):
    __slots__ = ("requested_delay_ms", "completed", "summary")
    REQUESTED_DELAY_MS_FIELD_NUMBER: _ClassVar[int]
    COMPLETED_FIELD_NUMBER: _ClassVar[int]
    SUMMARY_FIELD_NUMBER: _ClassVar[int]
    requested_delay_ms: int
    completed: bool
    summary: SalesSummary
    def __init__(self, requested_delay_ms: _Optional[int] = ..., completed: _Optional[bool] = ..., summary: _Optional[_Union[SalesSummary, _Mapping]] = ...) -> None: ...
