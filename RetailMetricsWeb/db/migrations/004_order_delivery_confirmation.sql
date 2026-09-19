-- Additive customer-order fulfillment lifecycle.
-- Apply after Migration 003.
--
-- No imported/canonical row is updated.
-- Transaction rolls back in full on error.

BEGIN;

ALTER TABLE public.orders
    ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS delivered_confirmed_by_customer BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE public.orders
    DROP CONSTRAINT IF EXISTS ck_orders_status;

-- Historical imported rows keep NULL order_status.
-- Only application-origin orders using the old "completed" status are backfilled.

UPDATE public.orders
SET
    order_status = 'ready_shipped',
    row_version = COALESCE(row_version, 0) + 1,
    updated_at = NOW()
WHERE record_origin IN ('staff', 'customer')
  AND order_status = 'completed';

ALTER TABLE public.orders
    ADD CONSTRAINT ck_orders_status CHECK (
        order_status IS NULL
        OR order_status IN (
            'pending',
            'processing',
            'ready_shipped',
            'delivered',
            'cancelled',
            'refunded'
        )
    );

ALTER TABLE public.orders
    ADD CONSTRAINT ck_orders_delivery_confirmation CHECK (
        (
            NOT delivered_confirmed_by_customer
            AND delivered_at IS NULL
            AND order_status IS DISTINCT FROM 'delivered'
        )
        OR
        (
            delivered_confirmed_by_customer
            AND delivered_at IS NOT NULL
            AND record_origin = 'customer'
            AND order_status IN ('delivered', 'refunded')
        )
    );

-- Migration 002's origin trigger gives legacy staff inserts their default status.
-- Replace only that default; preserve its existing origin inference rules.

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

            SELECT o.record_origin
            INTO parent_origin
            FROM public.orders o
            WHERE o.order_id = NEW.order_id;

            NEW.record_origin := COALESCE(
                parent_origin,
                CASE
                    WHEN NEW.created_by_app_user_id IS NULL THEN 'imported'
                    ELSE 'staff'
                END
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

        ELSIF NEW.record_origin = 'staff'
              AND NEW.order_status IS NULL THEN
            NEW.order_status := 'ready_shipped';

        END IF;

    END IF;

    RETURN NEW;
END;
$function$;

ALTER TABLE public.notification_outbox
    DROP CONSTRAINT IF EXISTS ck_notification_outbox_target;

ALTER TABLE public.notification_outbox
    ADD CONSTRAINT ck_notification_outbox_target CHECK (
        (
            event_type IN (
                'order_confirmation',
                'order_processing',
                'order_completed',
                'order_ready_shipped',
                'order_delivered',
                'order_cancelled'
            )
            AND order_id IS NOT NULL
            AND refund_request_id IS NULL
        )
        OR
        (
            event_type IN (
                'refund_request_submitted',
                'refund_rejected',
                'refund_processed'
            )
            AND refund_request_id IS NOT NULL
            AND order_id IS NULL
        )
    );

ALTER TABLE public.notification_outbox
    DROP CONSTRAINT IF EXISTS ck_notification_outbox_event_channel;

ALTER TABLE public.notification_outbox
    ADD CONSTRAINT ck_notification_outbox_event_channel CHECK (
        channel = 'sms'
        OR event_type IN (
            'order_confirmation',
            'order_processing',
            'order_completed',
            'order_ready_shipped',
            'order_delivered',
            'order_cancelled',
            'refund_rejected',
            'refund_processed'
        )
    );

COMMIT;