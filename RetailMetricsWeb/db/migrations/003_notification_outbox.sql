-- RetailMetrics transactional notification outbox. No historical rows are changed.
BEGIN;

CREATE TABLE public.notification_outbox (
    notification_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_account_id BIGINT NOT NULL,
    order_id BIGINT,
    refund_request_id BIGINT,
    event_type VARCHAR(32) NOT NULL,
    channel VARCHAR(5) NOT NULL,
    delivery_status VARCHAR(16) NOT NULL DEFAULT 'pending',
    recipient_address VARCHAR(254) NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_attempt_at TIMESTAMPTZ,
    sent_at TIMESTAMPTZ,
    provider_message_id VARCHAR(128),
    error_code VARCHAR(64),
    CONSTRAINT fk_notification_outbox_customer FOREIGN KEY (customer_account_id)
        REFERENCES public.customer_accounts(customer_account_id) ON DELETE RESTRICT,
    CONSTRAINT fk_notification_outbox_order_owner FOREIGN KEY (order_id, customer_account_id)
        REFERENCES public.orders(order_id, customer_account_id) ON DELETE RESTRICT,
    CONSTRAINT fk_notification_outbox_refund_request FOREIGN KEY (refund_request_id)
        REFERENCES public.refund_requests(refund_request_id) ON DELETE RESTRICT,
    CONSTRAINT ck_notification_outbox_target CHECK (
        (event_type IN ('order_confirmation','order_processing','order_completed','order_cancelled')
            AND order_id IS NOT NULL AND refund_request_id IS NULL)
        OR
        (event_type IN ('refund_request_submitted','refund_rejected','refund_processed')
            AND refund_request_id IS NOT NULL AND order_id IS NULL)
    ),
    CONSTRAINT ck_notification_outbox_channel CHECK (channel IN ('email','sms')),
    CONSTRAINT ck_notification_outbox_event_channel CHECK (
        channel='sms' OR event_type IN
            ('order_confirmation','order_completed','order_cancelled','refund_rejected','refund_processed')
    ),
    CONSTRAINT ck_notification_outbox_status CHECK (delivery_status IN ('pending','sending','sent','failed')),
    CONSTRAINT ck_notification_outbox_recipient CHECK (
        BTRIM(recipient_address) <> '' AND
        (channel='email' OR recipient_address ~ '^\+[1-9][0-9]{7,14}$')
    ),
    CONSTRAINT ck_notification_outbox_attempts CHECK (attempt_count >= 0),
    CONSTRAINT ck_notification_outbox_delivery_state CHECK (
        (delivery_status='pending' AND attempt_count=0 AND last_attempt_at IS NULL AND sent_at IS NULL)
        OR (delivery_status='sending' AND attempt_count>0 AND last_attempt_at IS NOT NULL AND sent_at IS NULL)
        OR (delivery_status='failed' AND attempt_count>0 AND last_attempt_at IS NOT NULL AND sent_at IS NULL)
        OR (delivery_status='sent' AND attempt_count>0 AND last_attempt_at IS NOT NULL AND sent_at IS NOT NULL)
    )
);

CREATE UNIQUE INDEX uq_notification_outbox_order_event_channel
    ON public.notification_outbox(order_id,event_type,channel) WHERE order_id IS NOT NULL;
CREATE UNIQUE INDEX uq_notification_outbox_refund_event_channel
    ON public.notification_outbox(refund_request_id,event_type,channel) WHERE refund_request_id IS NOT NULL;
CREATE INDEX idx_notification_outbox_pending
    ON public.notification_outbox(created_at,notification_id) WHERE delivery_status='pending';

COMMIT;
