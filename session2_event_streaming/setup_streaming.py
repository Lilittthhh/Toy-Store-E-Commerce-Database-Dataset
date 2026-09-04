from __future__ import annotations
from db import connect
import config as cfg

DDL = r"""
CREATE TABLE IF NOT EXISTS retailmetrics_event_log (
    log_offset BIGSERIAL PRIMARY KEY,
    topic TEXT NOT NULL,
    partition_id INTEGER NOT NULL CHECK (partition_id >= 0 AND partition_id < 4),
    partition_key BIGINT NOT NULL,
    event_time TIMESTAMP NOT NULL,
    event_type TEXT NOT NULL,
    event_id TEXT NOT NULL UNIQUE,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rm_event_topic_offset
    ON retailmetrics_event_log(topic, log_offset);
CREATE INDEX IF NOT EXISTS idx_rm_event_partition
    ON retailmetrics_event_log(topic, partition_id, log_offset);
CREATE INDEX IF NOT EXISTS idx_rm_event_session
    ON retailmetrics_event_log(partition_key);
CREATE INDEX IF NOT EXISTS idx_rm_event_time
    ON retailmetrics_event_log(event_time);
CREATE INDEX IF NOT EXISTS idx_rm_event_type
    ON retailmetrics_event_log(event_type);

CREATE TABLE IF NOT EXISTS retailmetrics_consumer_offsets (
    consumer_name TEXT NOT NULL,
    topic TEXT NOT NULL,
    last_offset BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (consumer_name, topic)
);

CREATE TABLE IF NOT EXISTS retailmetrics_consumer_partition_offsets (
    consumer_name TEXT NOT NULL,
    topic TEXT NOT NULL,
    partition_id INTEGER NOT NULL,
    last_offset BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (consumer_name, topic, partition_id)
);

-- Idempotent consumer-side sinks. Reprocessing the same event_id cannot create
-- a second logical record.
CREATE TABLE IF NOT EXISTS retailmetrics_conversion_audit (
    event_id TEXT PRIMARY KEY,
    log_offset BIGINT NOT NULL,
    website_session_id BIGINT NOT NULL,
    order_id BIGINT,
    event_time TIMESTAMP NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS retailmetrics_refund_projection (
    event_id TEXT PRIMARY KEY,
    log_offset BIGINT NOT NULL,
    website_session_id BIGINT NOT NULL,
    refund_amount_usd NUMERIC(12,2) NOT NULL,
    event_time TIMESTAMP NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS retailmetrics_session_projection (
    website_session_id BIGINT PRIMARY KEY,
    pageview_count BIGINT NOT NULL,
    session_duration_seconds DOUBLE PRECISION NOT NULL,
    converted INTEGER NOT NULL,
    order_revenue_usd DOUBLE PRECISION NOT NULL,
    gross_profit_usd DOUBLE PRECISION NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS retailmetrics_failure_audit (
    event_id TEXT PRIMARY KEY,
    log_offset BIGINT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS retailmetrics_stream_runs (
    run_id BIGSERIAL PRIMARY KEY,
    stage TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    events_processed BIGINT NOT NULL DEFAULT 0,
    result_json JSONB
);
"""

def main():
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(DDL)
        conn.commit()
        print("RetailMetrics Session 2 streaming tables are ready.")
        print(f"topic         : {cfg.TOPIC}")
        print(f"partitions    : {cfg.NUM_PARTITIONS}")
        print(f"partition key : {cfg.PARTITION_KEY}")
        print(f"event time    : {cfg.EVENT_TIME}")
        print("consumer sinks: idempotent by primary/unique keys")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
