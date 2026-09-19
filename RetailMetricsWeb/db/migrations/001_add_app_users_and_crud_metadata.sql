-- RetailMetrics Web
-- Minimum additive migration for authentication, one-user-one-role RBAC,
-- CRUD attribution, optimistic concurrency, and application-generated IDs.
--
-- This migration:
--   * creates only one table: public.app_users;
--   * adds nullable creator attribution and row versions to four existing
--     Toy Store business tables;
--   * creates four read-only canonical analytical views and enforces the
--     observed one-order-per-session rule;
--   * never copies, truncates, deletes, or updates existing rows;
--   * does not create a webapp schema or modify Session 2 tables; and
--   * creates no user account, password, or credential.

BEGIN;

CREATE TABLE IF NOT EXISTS public.app_users (
    app_user_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username VARCHAR(64) NOT NULL,
    email VARCHAR(254) NOT NULL,
    password_hash TEXT NOT NULL,
    role VARCHAR(32) NOT NULL DEFAULT 'analyst',
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
    CONSTRAINT ck_app_users_username_not_blank
        CHECK (BTRIM(username) <> ''),
    CONSTRAINT ck_app_users_email_not_blank
        CHECK (BTRIM(email) <> ''),
    CONSTRAINT ck_app_users_password_hash_not_blank
        CHECK (BTRIM(password_hash) <> ''),
    CONSTRAINT ck_app_users_role
        CHECK (role IN ('admin', 'operations_staff', 'analyst')),
    CONSTRAINT ck_app_users_failed_login_attempts
        CHECK (failed_login_attempts >= 0),
    CONSTRAINT ck_app_users_token_version
        CHECK (token_version >= 1),
    CONSTRAINT ck_app_users_row_version
        CHECK (row_version >= 1),
    CONSTRAINT ck_app_users_reset_token_hash
        CHECK (
            password_reset_token_hash IS NULL
            OR password_reset_token_hash ~ '^[0-9a-f]{64}$'
        ),
    CONSTRAINT ck_app_users_reset_pair
        CHECK (
            (password_reset_token_hash IS NULL AND password_reset_expires_at IS NULL)
            OR
            (password_reset_token_hash IS NOT NULL AND password_reset_expires_at IS NOT NULL)
        )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_app_users_username_lower
    ON public.app_users (LOWER(username));

CREATE UNIQUE INDEX IF NOT EXISTS uq_app_users_email_lower
    ON public.app_users (LOWER(email));

CREATE INDEX IF NOT EXISTS idx_app_users_role_active
    ON public.app_users (role, is_active);

CREATE INDEX IF NOT EXISTS idx_app_users_locked_until
    ON public.app_users (locked_until)
    WHERE locked_until IS NOT NULL;

ALTER TABLE public.products
    ADD COLUMN IF NOT EXISTS created_by_app_user_id BIGINT,
    ADD COLUMN IF NOT EXISTS row_version BIGINT NOT NULL DEFAULT 1;

ALTER TABLE public.orders
    ADD COLUMN IF NOT EXISTS created_by_app_user_id BIGINT,
    ADD COLUMN IF NOT EXISTS row_version BIGINT NOT NULL DEFAULT 1;

ALTER TABLE public.order_items
    ADD COLUMN IF NOT EXISTS created_by_app_user_id BIGINT,
    ADD COLUMN IF NOT EXISTS row_version BIGINT NOT NULL DEFAULT 1;

ALTER TABLE public.order_item_refunds
    ADD COLUMN IF NOT EXISTS created_by_app_user_id BIGINT,
    ADD COLUMN IF NOT EXISTS row_version BIGINT NOT NULL DEFAULT 1;

DO $constraints$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_products_row_version'
          AND conrelid = 'public.products'::regclass
    ) THEN
        ALTER TABLE public.products
            ADD CONSTRAINT ck_products_row_version CHECK (row_version >= 1);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_orders_row_version'
          AND conrelid = 'public.orders'::regclass
    ) THEN
        ALTER TABLE public.orders
            ADD CONSTRAINT ck_orders_row_version CHECK (row_version >= 1);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_order_items_row_version'
          AND conrelid = 'public.order_items'::regclass
    ) THEN
        ALTER TABLE public.order_items
            ADD CONSTRAINT ck_order_items_row_version CHECK (row_version >= 1);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_order_item_refunds_row_version'
          AND conrelid = 'public.order_item_refunds'::regclass
    ) THEN
        ALTER TABLE public.order_item_refunds
            ADD CONSTRAINT ck_order_item_refunds_row_version CHECK (row_version >= 1);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_products_created_by_app_user'
          AND conrelid = 'public.products'::regclass
    ) THEN
        ALTER TABLE public.products
            ADD CONSTRAINT fk_products_created_by_app_user
            FOREIGN KEY (created_by_app_user_id)
            REFERENCES public.app_users(app_user_id)
            ON DELETE SET NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_orders_created_by_app_user'
          AND conrelid = 'public.orders'::regclass
    ) THEN
        ALTER TABLE public.orders
            ADD CONSTRAINT fk_orders_created_by_app_user
            FOREIGN KEY (created_by_app_user_id)
            REFERENCES public.app_users(app_user_id)
            ON DELETE SET NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_order_items_created_by_app_user'
          AND conrelid = 'public.order_items'::regclass
    ) THEN
        ALTER TABLE public.order_items
            ADD CONSTRAINT fk_order_items_created_by_app_user
            FOREIGN KEY (created_by_app_user_id)
            REFERENCES public.app_users(app_user_id)
            ON DELETE SET NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_order_item_refunds_created_by_app_user'
          AND conrelid = 'public.order_item_refunds'::regclass
    ) THEN
        ALTER TABLE public.order_item_refunds
            ADD CONSTRAINT fk_order_item_refunds_created_by_app_user
            FOREIGN KEY (created_by_app_user_id)
            REFERENCES public.app_users(app_user_id)
            ON DELETE SET NULL;
    END IF;
END
$constraints$;

CREATE INDEX IF NOT EXISTS idx_products_created_by_app_user
    ON public.products (created_by_app_user_id);

CREATE INDEX IF NOT EXISTS idx_orders_created_by_app_user
    ON public.orders (created_by_app_user_id);

-- The imported Toy Store dataset contains at most one order per website
-- session. Enforce that invariant for both imported and application rows.
CREATE UNIQUE INDEX IF NOT EXISTS uq_orders_website_session_id
    ON public.orders (website_session_id);

CREATE INDEX IF NOT EXISTS idx_order_items_created_by_app_user
    ON public.order_items (created_by_app_user_id);

CREATE INDEX IF NOT EXISTS idx_order_item_refunds_created_by_app_user
    ON public.order_item_refunds (created_by_app_user_id);

-- One deliberately unowned sequence supplies new IDs for all four mutable
-- business tables. Because it is not owned by any table, the existing source
-- migration's TRUNCATE ... RESTART IDENTITY cannot reset it.
CREATE SEQUENCE IF NOT EXISTS public.retailmetrics_app_entity_id_seq
    AS BIGINT
    INCREMENT BY 1
    MINVALUE 1
    NO MAXVALUE
    START WITH 1
    CACHE 1;

-- Serialize sequence alignment with business-table writes. ALTER TABLE above
-- already takes strong locks on a first run; this explicit lock also protects
-- a rerun where the columns already exist.
LOCK TABLE
    public.products,
    public.orders,
    public.order_items,
    public.order_item_refunds
IN SHARE ROW EXCLUSIVE MODE;

DO $sequence_alignment$
DECLARE
    required_next_id BIGINT;
    sequence_last_value BIGINT;
    sequence_is_called BOOLEAN;
    sequence_next_id BIGINT;
BEGIN
    SELECT GREATEST(
        COALESCE((SELECT MAX(product_id) FROM public.products), 0),
        COALESCE((SELECT MAX(order_id) FROM public.orders), 0),
        COALESCE((SELECT MAX(order_item_id) FROM public.order_items), 0),
        COALESCE((
            SELECT MAX(order_item_refund_id)
            FROM public.order_item_refunds
        ), 0)
    ) + 1
    INTO required_next_id;

    SELECT last_value, is_called
    INTO sequence_last_value, sequence_is_called
    FROM public.retailmetrics_app_entity_id_seq;

    sequence_next_id := CASE
        WHEN sequence_is_called THEN sequence_last_value + 1
        ELSE sequence_last_value
    END;

    -- Never move the shared sequence backward on a rerun.
    IF sequence_next_id < required_next_id THEN
        EXECUTE format(
            'ALTER SEQUENCE public.retailmetrics_app_entity_id_seq RESTART WITH %s',
            required_next_id
        );
    END IF;
END
$sequence_alignment$;

ALTER TABLE public.products
    ALTER COLUMN product_id
    SET DEFAULT nextval('public.retailmetrics_app_entity_id_seq'::regclass);

ALTER TABLE public.orders
    ALTER COLUMN order_id
    SET DEFAULT nextval('public.retailmetrics_app_entity_id_seq'::regclass);

ALTER TABLE public.order_items
    ALTER COLUMN order_item_id
    SET DEFAULT nextval('public.retailmetrics_app_entity_id_seq'::regclass);

ALTER TABLE public.order_item_refunds
    ALTER COLUMN order_item_refund_id
    SET DEFAULT nextval('public.retailmetrics_app_entity_id_seq'::regclass);

-- Canonical analytical views expose the original CSV shape only. OFFSET 0 is
-- deliberately present: it preserves the result set while making each view
-- non-automatically-updatable in PostgreSQL. Analytics read these views;
-- RetailMetricsWeb CRUD writes the base tables.
CREATE OR REPLACE VIEW public.canonical_products AS
SELECT
    product_id,
    created_at,
    product_name
FROM public.products
WHERE created_by_app_user_id IS NULL
OFFSET 0;

CREATE OR REPLACE VIEW public.canonical_orders AS
SELECT
    order_id,
    created_at,
    website_session_id,
    user_id,
    primary_product_id,
    items_purchased,
    price_usd,
    cogs_usd
FROM public.orders
WHERE created_by_app_user_id IS NULL
OFFSET 0;

CREATE OR REPLACE VIEW public.canonical_order_items AS
SELECT
    order_item_id,
    created_at,
    order_id,
    product_id,
    is_primary_item,
    price_usd,
    cogs_usd
FROM public.order_items
WHERE created_by_app_user_id IS NULL
OFFSET 0;

CREATE OR REPLACE VIEW public.canonical_order_item_refunds AS
SELECT
    order_item_refund_id,
    created_at,
    order_item_id,
    order_id,
    refund_amount_usd
FROM public.order_item_refunds
WHERE created_by_app_user_id IS NULL
OFFSET 0;

COMMENT ON TABLE public.app_users IS
    'RetailMetricsWeb login accounts with one fixed role per user.';

COMMENT ON COLUMN public.products.created_by_app_user_id IS
    'Application account that created this row; NULL identifies imported source data.';
COMMENT ON COLUMN public.orders.created_by_app_user_id IS
    'Application account that created this row; NULL identifies imported source data.';
COMMENT ON COLUMN public.order_items.created_by_app_user_id IS
    'Application account that created this row; NULL identifies imported source data.';
COMMENT ON COLUMN public.order_item_refunds.created_by_app_user_id IS
    'Application account that created this row; NULL identifies imported source data.';

COMMENT ON VIEW public.canonical_products IS
    'Read-only imported products used as the default analytical baseline.';
COMMENT ON VIEW public.canonical_orders IS
    'Read-only imported orders used as the default analytical baseline.';
COMMENT ON VIEW public.canonical_order_items IS
    'Read-only imported order items used as the default analytical baseline.';
COMMENT ON VIEW public.canonical_order_item_refunds IS
    'Read-only imported refunds used as the default analytical baseline.';

COMMIT;
