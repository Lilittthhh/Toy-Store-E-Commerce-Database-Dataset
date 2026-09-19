-- Additive Admin-only application audit trail. Apply after Migration 004.
-- No imported/canonical row is changed.
BEGIN;

CREATE TABLE IF NOT EXISTS public.audit_logs (
    audit_log_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor_type VARCHAR(16) NOT NULL,
    actor_id BIGINT,
    actor_role VARCHAR(24),
    actor_display VARCHAR(100),
    action VARCHAR(80) NOT NULL,
    entity_type VARCHAR(64),
    entity_id VARCHAR(100),
    description TEXT,
    old_values JSONB,
    new_values JSONB,
    ip_address VARCHAR(45),
    user_agent TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_audit_actor_type CHECK (actor_type IN ('staff','customer','system','anonymous')),
    CONSTRAINT ck_audit_actor_id CHECK (
        (actor_type IN ('staff','customer') AND actor_id IS NOT NULL AND actor_id > 0) OR
        (actor_type IN ('system','anonymous') AND actor_id IS NULL)
    ),
    CONSTRAINT ck_audit_actor_role CHECK (
        (actor_type='staff' AND actor_role IS NOT NULL AND actor_role IN ('admin','operations_staff','analyst')) OR
        (actor_type='customer' AND actor_role IS NOT NULL AND actor_role='customer') OR
        (actor_type IN ('system','anonymous') AND actor_role IS NULL)
    ),
    CONSTRAINT ck_audit_action CHECK (action ~ '^[A-Z][A-Z0-9_]{1,79}$'),
    CONSTRAINT ck_audit_old_values CHECK (old_values IS NULL OR jsonb_typeof(old_values)='object'),
    CONSTRAINT ck_audit_new_values CHECK (new_values IS NULL OR jsonb_typeof(new_values)='object')
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON public.audit_logs (created_at DESC, audit_log_id DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_actor ON public.audit_logs (actor_type, actor_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_actor_role ON public.audit_logs (actor_role);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action
ON public.audit_logs (action);
CREATE INDEX IF NOT EXISTS idx_audit_logs_entity ON public.audit_logs (entity_type, entity_id);

COMMIT;
