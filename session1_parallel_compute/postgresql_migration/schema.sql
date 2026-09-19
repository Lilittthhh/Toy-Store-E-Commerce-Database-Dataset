CREATE TABLE IF NOT EXISTS website_sessions (
    website_session_id BIGINT PRIMARY KEY,
    created_at TIMESTAMP NOT NULL,
    user_id BIGINT NOT NULL,
    is_repeat_session INTEGER,
    utm_source TEXT,
    utm_campaign TEXT,
    utm_content TEXT,
    device_type TEXT,
    http_referer TEXT
);

CREATE TABLE IF NOT EXISTS products (
    product_id BIGINT PRIMARY KEY,
    created_at TIMESTAMP NOT NULL,
    product_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS website_pageviews (
    website_pageview_id BIGINT PRIMARY KEY,
    created_at TIMESTAMP NOT NULL,
    website_session_id BIGINT NOT NULL REFERENCES website_sessions(website_session_id),
    pageview_url TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    order_id BIGINT PRIMARY KEY,
    created_at TIMESTAMP NOT NULL,
    website_session_id BIGINT NOT NULL REFERENCES website_sessions(website_session_id),
    user_id BIGINT NOT NULL,
    primary_product_id BIGINT REFERENCES products(product_id),
    items_purchased INTEGER NOT NULL,
    price_usd NUMERIC(12,2) NOT NULL,
    cogs_usd NUMERIC(12,2) NOT NULL
);

CREATE TABLE IF NOT EXISTS order_items (
    order_item_id BIGINT PRIMARY KEY,
    created_at TIMESTAMP NOT NULL,
    order_id BIGINT NOT NULL REFERENCES orders(order_id),
    product_id BIGINT NOT NULL REFERENCES products(product_id),
    is_primary_item INTEGER,
    price_usd NUMERIC(12,2) NOT NULL,
    cogs_usd NUMERIC(12,2) NOT NULL
);

CREATE TABLE IF NOT EXISTS order_item_refunds (
    order_item_refund_id BIGINT PRIMARY KEY,
    created_at TIMESTAMP NOT NULL,
    order_item_id BIGINT NOT NULL REFERENCES order_items(order_item_id),
    order_id BIGINT NOT NULL REFERENCES orders(order_id),
    refund_amount_usd NUMERIC(12,2) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pageviews_session_id ON website_pageviews(website_session_id);
CREATE INDEX IF NOT EXISTS idx_pageviews_created_at ON website_pageviews(created_at);
CREATE INDEX IF NOT EXISTS idx_sessions_created_at ON website_sessions(created_at);
CREATE INDEX IF NOT EXISTS idx_orders_session_id ON orders(website_session_id);
CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at);
CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_order_items_product_id ON order_items(product_id);
CREATE INDEX IF NOT EXISTS idx_refunds_order_id ON order_item_refunds(order_id);
