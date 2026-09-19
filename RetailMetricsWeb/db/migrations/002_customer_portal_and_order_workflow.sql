-- RetailMetrics Web
-- Customer identity, storefront metadata, carts, order workflow, and origin boundary.
-- Phase 2 schema preparation only: no customer accounts or business rows are seeded.

BEGIN;

-- Block concurrent business writes for the complete classification/DDL window.
LOCK TABLE public.app_users, public.products, public.orders,
    public.order_items, public.order_item_refunds
IN ACCESS EXCLUSIVE MODE;

-- Refuse partial/repeated deployment and unsafe reclassification before any DDL.
DO $preflight$
BEGIN
    IF to_regclass('public.app_users') IS NULL
       OR to_regclass('public.products') IS NULL
       OR to_regclass('public.orders') IS NULL
       OR to_regclass('public.order_items') IS NULL
       OR to_regclass('public.order_item_refunds') IS NULL THEN
        RAISE EXCEPTION 'Migration 001 and all mutable Toy Store tables are required';
    END IF;

    IF to_regclass('public.customer_accounts') IS NOT NULL
       OR EXISTS (
           SELECT 1 FROM information_schema.columns
           WHERE table_schema = 'public' AND table_name = 'orders'
             AND column_name = 'record_origin'
       ) THEN
        RAISE EXCEPTION 'Migration 002 appears to be already or partially applied';
    END IF;

    -- Existing application-created orders have no trustworthy lifecycle status.
    -- They must be reviewed outside this migration rather than guessed.
    IF EXISTS (SELECT 1 FROM public.orders WHERE created_by_app_user_id IS NOT NULL) THEN
        RAISE EXCEPTION
            'Existing application-created orders require an explicit status before migration 002';
    END IF;

    -- An item must inherit its parent order origin. With no pre-existing staff
    -- orders, a pre-existing staff-created item cannot be classified safely.
    IF EXISTS (
        SELECT 1
        FROM public.order_items oi
        JOIN public.orders o ON o.order_id = oi.order_id
        WHERE (oi.created_by_app_user_id IS NULL)
              IS DISTINCT FROM (o.created_by_app_user_id IS NULL)
    ) THEN
        RAISE EXCEPTION
            'Existing order-item creator state does not match its parent order';
    END IF;
END
$preflight$;

CREATE TABLE public.customer_accounts (
    customer_account_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dataset_user_id BIGINT,
    email VARCHAR(254) NOT NULL,
    password_hash TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    failed_login_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TIMESTAMPTZ,
    last_login_at TIMESTAMPTZ,
    password_changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    password_reset_token_hash CHAR(64),
    password_reset_expires_at TIMESTAMPTZ,
    token_version INTEGER NOT NULL DEFAULT 1,
    row_version BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_customer_accounts_dataset_user_id CHECK (dataset_user_id IS NULL OR dataset_user_id > 0),
    CONSTRAINT ck_customer_accounts_email_not_blank CHECK (BTRIM(email) <> ''),
    CONSTRAINT ck_customer_accounts_password_hash_not_blank CHECK (BTRIM(password_hash) <> ''),
    CONSTRAINT ck_customer_accounts_failed_login_attempts CHECK (failed_login_attempts >= 0),
    CONSTRAINT ck_customer_accounts_token_version CHECK (token_version >= 1),
    CONSTRAINT ck_customer_accounts_row_version CHECK (row_version >= 1),
    CONSTRAINT ck_customer_accounts_reset_hash CHECK (
        password_reset_token_hash IS NULL
        OR password_reset_token_hash ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT ck_customer_accounts_reset_pair CHECK (
        (password_reset_token_hash IS NULL AND password_reset_expires_at IS NULL)
        OR (password_reset_token_hash IS NOT NULL AND password_reset_expires_at IS NOT NULL)
    )
);

CREATE UNIQUE INDEX uq_customer_accounts_email_lower
    ON public.customer_accounts (LOWER(email));
CREATE UNIQUE INDEX uq_customer_accounts_dataset_user_id
    ON public.customer_accounts (dataset_user_id)
    WHERE dataset_user_id IS NOT NULL;
CREATE INDEX idx_customer_accounts_active ON public.customer_accounts (is_active);
CREATE INDEX idx_customer_accounts_locked_until ON public.customer_accounts (locked_until)
    WHERE locked_until IS NOT NULL;

CREATE TABLE public.customer_profiles (
    customer_account_id BIGINT PRIMARY KEY,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    phone VARCHAR(32),
    row_version BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_customer_profiles_account FOREIGN KEY (customer_account_id)
        REFERENCES public.customer_accounts(customer_account_id) ON DELETE RESTRICT,
    CONSTRAINT ck_customer_profiles_first_name CHECK (BTRIM(first_name) <> ''),
    CONSTRAINT ck_customer_profiles_last_name CHECK (BTRIM(last_name) <> ''),
    CONSTRAINT ck_customer_profiles_phone CHECK (phone IS NULL OR BTRIM(phone) <> ''),
    CONSTRAINT ck_customer_profiles_row_version CHECK (row_version >= 1)
);

CREATE TABLE public.customer_addresses (
    customer_address_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_account_id BIGINT NOT NULL,
    label VARCHAR(50) NOT NULL,
    recipient_first_name VARCHAR(100) NOT NULL,
    recipient_last_name VARCHAR(100) NOT NULL,
    phone VARCHAR(32),
    address_line_1 VARCHAR(200) NOT NULL,
    address_line_2 VARCHAR(200),
    city VARCHAR(100) NOT NULL,
    province_region VARCHAR(100) NOT NULL,
    postal_code VARCHAR(20) NOT NULL,
    country_code CHAR(2) NOT NULL DEFAULT 'PH',
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    row_version BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_customer_addresses_account FOREIGN KEY (customer_account_id)
        REFERENCES public.customer_accounts(customer_account_id) ON DELETE RESTRICT,
    CONSTRAINT uq_customer_addresses_id_account UNIQUE (customer_address_id, customer_account_id),
    CONSTRAINT ck_customer_addresses_label CHECK (BTRIM(label) <> ''),
    CONSTRAINT ck_customer_addresses_recipient_first CHECK (BTRIM(recipient_first_name) <> ''),
    CONSTRAINT ck_customer_addresses_recipient_last CHECK (BTRIM(recipient_last_name) <> ''),
    CONSTRAINT ck_customer_addresses_phone CHECK (phone IS NULL OR BTRIM(phone) <> ''),
    CONSTRAINT ck_customer_addresses_line_1 CHECK (BTRIM(address_line_1) <> ''),
    CONSTRAINT ck_customer_addresses_line_2 CHECK (address_line_2 IS NULL OR BTRIM(address_line_2) <> ''),
    CONSTRAINT ck_customer_addresses_city CHECK (BTRIM(city) <> ''),
    CONSTRAINT ck_customer_addresses_province CHECK (BTRIM(province_region) <> ''),
    CONSTRAINT ck_customer_addresses_postal CHECK (BTRIM(postal_code) <> ''),
    CONSTRAINT ck_customer_addresses_country CHECK (country_code ~ '^[A-Z]{2}$'),
    CONSTRAINT ck_customer_addresses_row_version CHECK (row_version >= 1)
);

CREATE INDEX idx_customer_addresses_account ON public.customer_addresses (customer_account_id);
CREATE UNIQUE INDEX uq_customer_addresses_active_default
    ON public.customer_addresses (customer_account_id)
    WHERE is_default AND is_active;

CREATE TABLE public.payment_methods (
    payment_method_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_account_id BIGINT NOT NULL,
    method_type VARCHAR(24) NOT NULL,
    display_label VARCHAR(100) NOT NULL,
    card_brand VARCHAR(32),
    card_last_four CHAR(4),
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    row_version BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_payment_methods_account FOREIGN KEY (customer_account_id)
        REFERENCES public.customer_accounts(customer_account_id) ON DELETE RESTRICT,
    CONSTRAINT uq_payment_methods_id_account UNIQUE (payment_method_id, customer_account_id),
    CONSTRAINT ck_payment_methods_type CHECK (
        method_type IN ('card', 'gcash', 'paypal', 'cash_on_delivery')
    ),
    CONSTRAINT ck_payment_methods_label CHECK (BTRIM(display_label) <> ''),
    CONSTRAINT ck_payment_methods_safe_card_metadata CHECK (
        (method_type = 'card'
         AND card_brand IS NOT NULL AND BTRIM(card_brand) <> ''
         AND card_last_four ~ '^[0-9]{4}$')
        OR
        (method_type <> 'card' AND card_brand IS NULL AND card_last_four IS NULL)
    ),
    CONSTRAINT ck_payment_methods_row_version CHECK (row_version >= 1)
);

CREATE INDEX idx_payment_methods_account ON public.payment_methods (customer_account_id);
CREATE UNIQUE INDEX uq_payment_methods_active_default
    ON public.payment_methods (customer_account_id)
    WHERE is_default AND is_active;

CREATE TABLE public.product_catalog_details (
    product_id BIGINT PRIMARY KEY,
    description TEXT NOT NULL DEFAULT '',
    current_price_usd NUMERIC(12,2) NOT NULL,
    current_cogs_usd NUMERIC(12,2) NOT NULL,
    image_url TEXT,
    is_available BOOLEAN NOT NULL DEFAULT FALSE,
    updated_by_app_user_id BIGINT NOT NULL,
    row_version BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_product_catalog_details_product FOREIGN KEY (product_id)
        REFERENCES public.products(product_id) ON DELETE RESTRICT,
    CONSTRAINT fk_product_catalog_details_updated_by FOREIGN KEY (updated_by_app_user_id)
        REFERENCES public.app_users(app_user_id) ON DELETE RESTRICT,
    CONSTRAINT ck_product_catalog_details_price CHECK (current_price_usd > 0),
    CONSTRAINT ck_product_catalog_details_cogs CHECK (
        current_cogs_usd >= 0 AND current_cogs_usd <= current_price_usd
    ),
    CONSTRAINT ck_product_catalog_details_image CHECK (image_url IS NULL OR BTRIM(image_url) <> ''),
    CONSTRAINT ck_product_catalog_details_row_version CHECK (row_version >= 1)
);

-- Add origin/workflow columns without defaults. BEFORE INSERT compatibility
-- triggers below classify legacy import/API inserts while future APIs set origin explicitly.
ALTER TABLE public.products ADD COLUMN record_origin VARCHAR(16);
ALTER TABLE public.orders
    ADD COLUMN record_origin VARCHAR(16),
    ADD COLUMN customer_account_id BIGINT,
    ADD COLUMN order_status VARCHAR(16),
    ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ALTER COLUMN website_session_id DROP NOT NULL,
    ALTER COLUMN user_id DROP NOT NULL;
ALTER TABLE public.order_items ADD COLUMN record_origin VARCHAR(16);
ALTER TABLE public.order_item_refunds
    ADD COLUMN record_origin VARCHAR(16),
    ADD COLUMN refund_request_id BIGINT;

UPDATE public.products
SET record_origin = CASE WHEN created_by_app_user_id IS NULL THEN 'imported' ELSE 'staff' END;
UPDATE public.orders
SET record_origin = CASE WHEN created_by_app_user_id IS NULL THEN 'imported' ELSE 'staff' END;
UPDATE public.order_items
SET record_origin = CASE WHEN created_by_app_user_id IS NULL THEN 'imported' ELSE 'staff' END;
UPDATE public.order_item_refunds
SET record_origin = CASE WHEN created_by_app_user_id IS NULL THEN 'imported' ELSE 'staff' END;

ALTER TABLE public.products ALTER COLUMN record_origin SET NOT NULL;
ALTER TABLE public.orders ALTER COLUMN record_origin SET NOT NULL;
ALTER TABLE public.order_items ALTER COLUMN record_origin SET NOT NULL;
ALTER TABLE public.order_item_refunds ALTER COLUMN record_origin SET NOT NULL;

ALTER TABLE public.products
    ADD CONSTRAINT ck_products_record_origin CHECK (record_origin IN ('imported', 'staff')),
    ADD CONSTRAINT ck_products_origin_context CHECK (
        (record_origin = 'imported' AND created_by_app_user_id IS NULL)
        OR (record_origin = 'staff' AND created_by_app_user_id IS NOT NULL)
    );

ALTER TABLE public.orders
    ADD CONSTRAINT fk_orders_customer_account FOREIGN KEY (customer_account_id)
        REFERENCES public.customer_accounts(customer_account_id) ON DELETE RESTRICT,
    ADD CONSTRAINT ck_orders_record_origin CHECK (
        record_origin IN ('imported', 'staff', 'customer')
    ),
    ADD CONSTRAINT ck_orders_status CHECK (
        order_status IS NULL
        OR order_status IN ('pending', 'processing', 'completed', 'cancelled', 'refunded')
    ),
    ADD CONSTRAINT ck_orders_origin_context CHECK (
        (record_origin = 'imported'
         AND created_by_app_user_id IS NULL
         AND customer_account_id IS NULL
         AND website_session_id IS NOT NULL
         AND user_id IS NOT NULL
         AND order_status IS NULL)
        OR
        (record_origin = 'staff'
         AND created_by_app_user_id IS NOT NULL
         AND customer_account_id IS NULL
         AND website_session_id IS NOT NULL
         AND user_id IS NOT NULL
         AND order_status IS NOT NULL)
        OR
        (record_origin = 'customer'
         AND customer_account_id IS NOT NULL
         AND website_session_id IS NULL
         AND user_id IS NULL
         AND order_status IS NOT NULL)
    ),
    ADD CONSTRAINT uq_orders_id_origin UNIQUE (order_id, record_origin),
    ADD CONSTRAINT uq_orders_id_customer UNIQUE (order_id, customer_account_id);

ALTER TABLE public.order_items
    ADD CONSTRAINT ck_order_items_record_origin CHECK (
        record_origin IN ('imported', 'staff', 'customer')
    ),
    ADD CONSTRAINT ck_order_items_origin_context CHECK (
        (record_origin = 'imported' AND created_by_app_user_id IS NULL)
        OR (record_origin = 'staff' AND created_by_app_user_id IS NOT NULL)
        OR (record_origin = 'customer')
    ),
    ADD CONSTRAINT uq_order_items_id_order UNIQUE (order_item_id, order_id),
    ADD CONSTRAINT fk_order_items_order_origin FOREIGN KEY (order_id, record_origin)
        REFERENCES public.orders(order_id, record_origin) ON DELETE RESTRICT;

CREATE TABLE public.order_shipping_addresses (
    order_id BIGINT PRIMARY KEY,
    customer_account_id BIGINT NOT NULL,
    source_customer_address_id BIGINT,
    recipient_first_name VARCHAR(100) NOT NULL,
    recipient_last_name VARCHAR(100) NOT NULL,
    phone VARCHAR(32),
    address_line_1 VARCHAR(200) NOT NULL,
    address_line_2 VARCHAR(200),
    city VARCHAR(100) NOT NULL,
    province_region VARCHAR(100) NOT NULL,
    postal_code VARCHAR(20) NOT NULL,
    country_code CHAR(2) NOT NULL,
    row_version BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_order_shipping_order_customer
        FOREIGN KEY (order_id, customer_account_id)
        REFERENCES public.orders(order_id, customer_account_id) ON DELETE RESTRICT,
    CONSTRAINT fk_order_shipping_source_address
        FOREIGN KEY (source_customer_address_id, customer_account_id)
        REFERENCES public.customer_addresses(customer_address_id, customer_account_id)
        ON DELETE RESTRICT,
    CONSTRAINT ck_order_shipping_recipient_first CHECK (BTRIM(recipient_first_name) <> ''),
    CONSTRAINT ck_order_shipping_recipient_last CHECK (BTRIM(recipient_last_name) <> ''),
    CONSTRAINT ck_order_shipping_phone CHECK (phone IS NULL OR BTRIM(phone) <> ''),
    CONSTRAINT ck_order_shipping_line_1 CHECK (BTRIM(address_line_1) <> ''),
    CONSTRAINT ck_order_shipping_line_2 CHECK (address_line_2 IS NULL OR BTRIM(address_line_2) <> ''),
    CONSTRAINT ck_order_shipping_city CHECK (BTRIM(city) <> ''),
    CONSTRAINT ck_order_shipping_province CHECK (BTRIM(province_region) <> ''),
    CONSTRAINT ck_order_shipping_postal CHECK (BTRIM(postal_code) <> ''),
    CONSTRAINT ck_order_shipping_country CHECK (country_code ~ '^[A-Z]{2}$'),
    CONSTRAINT ck_order_shipping_row_version CHECK (row_version >= 1)
);

CREATE TABLE public.order_payments (
    order_payment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL UNIQUE,
    customer_account_id BIGINT NOT NULL,
    payment_method_id BIGINT,
    method_type VARCHAR(24) NOT NULL,
    payment_display_snapshot VARCHAR(100) NOT NULL,
    payment_status VARCHAR(24) NOT NULL DEFAULT 'pending',
    amount_usd NUMERIC(12,2) NOT NULL,
    simulated_reference VARCHAR(100),
    processed_at TIMESTAMPTZ,
    row_version BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_order_payments_order_customer
        FOREIGN KEY (order_id, customer_account_id)
        REFERENCES public.orders(order_id, customer_account_id) ON DELETE RESTRICT,
    CONSTRAINT fk_order_payments_method_customer
        FOREIGN KEY (payment_method_id, customer_account_id)
        REFERENCES public.payment_methods(payment_method_id, customer_account_id)
        ON DELETE RESTRICT,
    CONSTRAINT ck_order_payments_method_type CHECK (
        method_type IN ('card', 'gcash', 'paypal', 'cash_on_delivery')
    ),
    CONSTRAINT ck_order_payments_display CHECK (BTRIM(payment_display_snapshot) <> ''),
    CONSTRAINT ck_order_payments_status CHECK (
        payment_status IN ('pending', 'paid', 'failed', 'partially_refunded', 'refunded')
    ),
    CONSTRAINT ck_order_payments_amount CHECK (amount_usd > 0),
    CONSTRAINT ck_order_payments_reference CHECK (
        simulated_reference IS NULL OR BTRIM(simulated_reference) <> ''
    ),
    CONSTRAINT ck_order_payments_row_version CHECK (row_version >= 1)
);

CREATE TABLE public.refund_requests (
    refund_request_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_account_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    order_item_id BIGINT NOT NULL,
    reason TEXT NOT NULL,
    requested_amount_usd NUMERIC(12,2) NOT NULL,
    request_status VARCHAR(16) NOT NULL DEFAULT 'pending',
    resolution_note TEXT,
    reviewed_by_app_user_id BIGINT,
    reviewed_at TIMESTAMPTZ,
    row_version BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_refund_requests_order_customer
        FOREIGN KEY (order_id, customer_account_id)
        REFERENCES public.orders(order_id, customer_account_id) ON DELETE RESTRICT,
    CONSTRAINT fk_refund_requests_order_item
        FOREIGN KEY (order_item_id, order_id)
        REFERENCES public.order_items(order_item_id, order_id) ON DELETE RESTRICT,
    CONSTRAINT fk_refund_requests_reviewer FOREIGN KEY (reviewed_by_app_user_id)
        REFERENCES public.app_users(app_user_id) ON DELETE RESTRICT,
    CONSTRAINT uq_refund_requests_id_order_item
        UNIQUE (refund_request_id, order_id, order_item_id),
    CONSTRAINT ck_refund_requests_reason CHECK (BTRIM(reason) <> ''),
    CONSTRAINT ck_refund_requests_amount CHECK (requested_amount_usd > 0),
    CONSTRAINT ck_refund_requests_status CHECK (
        request_status IN ('pending', 'approved', 'rejected', 'processed')
    ),
    CONSTRAINT ck_refund_requests_resolution CHECK (
        resolution_note IS NULL OR BTRIM(resolution_note) <> ''
    ),
    CONSTRAINT ck_refund_requests_review_state CHECK (
        (request_status = 'pending'
         AND reviewed_by_app_user_id IS NULL AND reviewed_at IS NULL)
        OR
        (request_status <> 'pending'
         AND reviewed_by_app_user_id IS NOT NULL AND reviewed_at IS NOT NULL)
    ),
    CONSTRAINT ck_refund_requests_row_version CHECK (row_version >= 1)
);

CREATE INDEX idx_refund_requests_customer ON public.refund_requests (customer_account_id);
CREATE INDEX idx_refund_requests_order ON public.refund_requests (order_id);
CREATE INDEX idx_refund_requests_item ON public.refund_requests (order_item_id);
CREATE INDEX idx_refund_requests_status ON public.refund_requests (request_status);
CREATE UNIQUE INDEX uq_refund_requests_pending_customer_item
    ON public.refund_requests (customer_account_id, order_item_id)
    WHERE request_status = 'pending';

ALTER TABLE public.order_item_refunds
    ADD CONSTRAINT fk_order_item_refunds_request_context
        FOREIGN KEY (refund_request_id, order_id, order_item_id)
        REFERENCES public.refund_requests(refund_request_id, order_id, order_item_id)
        ON DELETE RESTRICT,
    ADD CONSTRAINT ck_order_item_refunds_record_origin CHECK (
        record_origin IN ('imported', 'staff', 'customer')
    ),
    ADD CONSTRAINT ck_order_item_refunds_origin_context CHECK (
        (record_origin = 'imported'
         AND created_by_app_user_id IS NULL AND refund_request_id IS NULL)
        OR
        (record_origin = 'staff'
         AND created_by_app_user_id IS NOT NULL AND refund_request_id IS NULL)
        OR
        (record_origin = 'customer'
         AND created_by_app_user_id IS NOT NULL AND refund_request_id IS NOT NULL)
    );

CREATE TABLE public.shopping_carts (
    shopping_cart_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_account_id BIGINT NOT NULL,
    cart_status VARCHAR(16) NOT NULL DEFAULT 'active',
    converted_order_id BIGINT UNIQUE,
    row_version BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_shopping_carts_account FOREIGN KEY (customer_account_id)
        REFERENCES public.customer_accounts(customer_account_id) ON DELETE RESTRICT,
    CONSTRAINT fk_shopping_carts_converted_order
        FOREIGN KEY (converted_order_id, customer_account_id)
        REFERENCES public.orders(order_id, customer_account_id) ON DELETE RESTRICT,
    CONSTRAINT ck_shopping_carts_status CHECK (
        cart_status IN ('active', 'converted', 'abandoned')
    ),
    CONSTRAINT ck_shopping_carts_conversion CHECK (
        (cart_status = 'converted' AND converted_order_id IS NOT NULL)
        OR (cart_status <> 'converted' AND converted_order_id IS NULL)
    ),
    CONSTRAINT ck_shopping_carts_row_version CHECK (row_version >= 1)
);

CREATE INDEX idx_shopping_carts_account ON public.shopping_carts (customer_account_id);
CREATE UNIQUE INDEX uq_shopping_carts_active_customer
    ON public.shopping_carts (customer_account_id)
    WHERE cart_status = 'active';

CREATE TABLE public.cart_items (
    cart_item_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    shopping_cart_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price_usd NUMERIC(12,2) NOT NULL,
    row_version BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_cart_items_cart FOREIGN KEY (shopping_cart_id)
        REFERENCES public.shopping_carts(shopping_cart_id) ON DELETE CASCADE,
    CONSTRAINT fk_cart_items_product FOREIGN KEY (product_id)
        REFERENCES public.products(product_id) ON DELETE RESTRICT,
    CONSTRAINT uq_cart_items_cart_product UNIQUE (shopping_cart_id, product_id),
    CONSTRAINT ck_cart_items_quantity CHECK (quantity BETWEEN 1 AND 99),
    CONSTRAINT ck_cart_items_unit_price CHECK (unit_price_usd > 0),
    CONSTRAINT ck_cart_items_row_version CHECK (row_version >= 1)
);

CREATE INDEX idx_cart_items_product ON public.cart_items (product_id);

-- Preserve permanent staff attribution. Staff accounts are deactivated, not deleted.
ALTER TABLE public.products DROP CONSTRAINT fk_products_created_by_app_user;
ALTER TABLE public.products ADD CONSTRAINT fk_products_created_by_app_user
    FOREIGN KEY (created_by_app_user_id) REFERENCES public.app_users(app_user_id)
    ON DELETE RESTRICT;
ALTER TABLE public.orders DROP CONSTRAINT fk_orders_created_by_app_user;
ALTER TABLE public.orders ADD CONSTRAINT fk_orders_created_by_app_user
    FOREIGN KEY (created_by_app_user_id) REFERENCES public.app_users(app_user_id)
    ON DELETE RESTRICT;
ALTER TABLE public.order_items DROP CONSTRAINT fk_order_items_created_by_app_user;
ALTER TABLE public.order_items ADD CONSTRAINT fk_order_items_created_by_app_user
    FOREIGN KEY (created_by_app_user_id) REFERENCES public.app_users(app_user_id)
    ON DELETE RESTRICT;
ALTER TABLE public.order_item_refunds DROP CONSTRAINT fk_order_item_refunds_created_by_app_user;
ALTER TABLE public.order_item_refunds ADD CONSTRAINT fk_order_item_refunds_created_by_app_user
    FOREIGN KEY (created_by_app_user_id) REFERENCES public.app_users(app_user_id)
    ON DELETE RESTRICT;

CREATE OR REPLACE FUNCTION public.set_retailmetrics_record_origin()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $function$
DECLARE
    parent_origin VARCHAR(16);
BEGIN
    IF NEW.record_origin IS NULL THEN
        IF TG_TABLE_NAME = 'orders' THEN
            IF NEW.customer_account_id IS NOT NULL THEN
                NEW.record_origin := 'customer';
            ELSE
                NEW.record_origin := CASE
                    WHEN NEW.created_by_app_user_id IS NULL THEN 'imported'
                    ELSE 'staff'
                END;
            END IF;
        ELSIF TG_TABLE_NAME = 'order_items' THEN
            SELECT o.record_origin INTO parent_origin
            FROM public.orders o
            WHERE o.order_id = NEW.order_id;
            NEW.record_origin := COALESCE(
                parent_origin,
                CASE WHEN NEW.created_by_app_user_id IS NULL THEN 'imported' ELSE 'staff' END
            );
        ELSIF TG_TABLE_NAME = 'order_item_refunds' THEN
            IF NEW.refund_request_id IS NOT NULL THEN
                NEW.record_origin := 'customer';
            ELSE
                NEW.record_origin := CASE
                    WHEN NEW.created_by_app_user_id IS NULL THEN 'imported'
                    ELSE 'staff'
                END;
            END IF;
        ELSE
            NEW.record_origin := CASE
                WHEN NEW.created_by_app_user_id IS NULL THEN 'imported'
                ELSE 'staff'
            END;
        END IF;
    END IF;

    IF TG_TABLE_NAME = 'orders' THEN
        IF NEW.record_origin = 'imported' THEN
            NEW.order_status := NULL;
        ELSIF NEW.record_origin = 'staff' AND NEW.order_status IS NULL THEN
            NEW.order_status := 'completed';
        END IF;
    END IF;
    RETURN NEW;
END
$function$;

CREATE TRIGGER trg_products_record_origin
    BEFORE INSERT ON public.products FOR EACH ROW
    EXECUTE FUNCTION public.set_retailmetrics_record_origin();
CREATE TRIGGER trg_orders_record_origin
    BEFORE INSERT ON public.orders FOR EACH ROW
    EXECUTE FUNCTION public.set_retailmetrics_record_origin();
CREATE TRIGGER trg_order_items_record_origin
    BEFORE INSERT ON public.order_items FOR EACH ROW
    EXECUTE FUNCTION public.set_retailmetrics_record_origin();
CREATE TRIGGER trg_order_item_refunds_record_origin
    BEFORE INSERT ON public.order_item_refunds FOR EACH ROW
    EXECUTE FUNCTION public.set_retailmetrics_record_origin();

CREATE INDEX idx_products_record_origin ON public.products (record_origin);
CREATE INDEX idx_orders_record_origin ON public.orders (record_origin);
CREATE INDEX idx_orders_customer_status ON public.orders (customer_account_id, order_status)
    WHERE customer_account_id IS NOT NULL;
CREATE INDEX idx_order_items_record_origin ON public.order_items (record_origin);
CREATE INDEX idx_order_item_refunds_record_origin ON public.order_item_refunds (record_origin);
CREATE INDEX idx_order_item_refunds_request ON public.order_item_refunds (refund_request_id)
    WHERE refund_request_id IS NOT NULL;
CREATE INDEX idx_website_sessions_user_latest
    ON public.website_sessions (user_id, created_at DESC);
CREATE INDEX idx_orders_user_id ON public.orders (user_id) WHERE user_id IS NOT NULL;

-- Exact legacy names and CSV column shapes are preserved for Sessions 1-3.
CREATE OR REPLACE VIEW public.canonical_products AS
SELECT product_id, created_at, product_name
FROM public.products
WHERE record_origin = 'imported'
OFFSET 0;

CREATE OR REPLACE VIEW public.canonical_orders AS
SELECT order_id, created_at, website_session_id, user_id, primary_product_id,
       items_purchased, price_usd, cogs_usd
FROM public.orders
WHERE record_origin = 'imported'
OFFSET 0;

CREATE OR REPLACE VIEW public.canonical_order_items AS
SELECT order_item_id, created_at, order_id, product_id, is_primary_item,
       price_usd, cogs_usd
FROM public.order_items
WHERE record_origin = 'imported'
OFFSET 0;

CREATE OR REPLACE VIEW public.canonical_order_item_refunds AS
SELECT order_item_refund_id, created_at, order_item_id, order_id, refund_amount_usd
FROM public.order_item_refunds
WHERE record_origin = 'imported'
OFFSET 0;

CREATE VIEW public.historical_customer_summary AS
WITH session_totals AS (
    SELECT user_id AS dataset_user_id,
           COUNT(*)::BIGINT AS session_count,
           BOOL_OR(COALESCE(is_repeat_session, 0) <> 0) AS repeat_visitor,
           MAX(created_at) AS last_visit
    FROM public.website_sessions
    GROUP BY user_id
),
latest_session AS (
    SELECT DISTINCT ON (user_id)
           user_id AS dataset_user_id, utm_source AS latest_utm_source,
           device_type AS latest_device_type
    FROM public.website_sessions
    ORDER BY user_id, created_at DESC, website_session_id DESC
),
order_totals AS (
    SELECT user_id AS dataset_user_id, COUNT(*)::BIGINT AS order_count,
           COALESCE(SUM(price_usd), 0)::NUMERIC(14,2) AS total_spent
    FROM public.canonical_orders
    GROUP BY user_id
),
refund_totals AS (
    SELECT o.user_id AS dataset_user_id,
           COALESCE(SUM(r.refund_amount_usd), 0)::NUMERIC(14,2) AS refund_total
    FROM public.canonical_orders o
    JOIN public.canonical_order_item_refunds r ON r.order_id = o.order_id
    GROUP BY o.user_id
)
SELECT s.dataset_user_id, s.session_count, s.repeat_visitor,
       COALESCE(o.order_count, 0)::BIGINT AS order_count,
       COALESCE(o.total_spent, 0)::NUMERIC(14,2) AS total_spent,
       COALESCE(r.refund_total, 0)::NUMERIC(14,2) AS refund_total,
       s.last_visit, l.latest_utm_source, l.latest_device_type
FROM session_totals s
JOIN latest_session l USING (dataset_user_id)
LEFT JOIN order_totals o USING (dataset_user_id)
LEFT JOIN refund_totals r USING (dataset_user_id)
OFFSET 0;

COMMENT ON COLUMN public.customer_accounts.dataset_user_id IS
    'Optional logical association to an imported shopper ID; not an authentication claim and not a foreign key.';
COMMENT ON COLUMN public.products.record_origin IS
    'Business source/context: imported or staff. Actor attribution is separate.';
COMMENT ON COLUMN public.orders.record_origin IS
    'Business source/context: imported, staff, or customer. Actor attribution is separate.';
COMMENT ON COLUMN public.order_items.record_origin IS
    'Business source/context inherited from the parent order.';
COMMENT ON COLUMN public.order_item_refunds.record_origin IS
    'Business source/context; customer means an approved customer request processed by staff.';
COMMENT ON VIEW public.historical_customer_summary IS
    'Deidentified read-only aggregate derived exclusively from canonical imported data.';

COMMIT;
