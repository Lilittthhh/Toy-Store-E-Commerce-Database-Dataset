from __future__ import annotations
import argparse
import json
import time
from db import connect
import config as cfg

# Event schema version is explicit so a later service can evolve the contract.
SCHEMA_VERSION = 1

# One durable topic, two event types:
# 1) pageview.recorded — website activity. The last pageview of a converted
#    session carries order facts needed to rebuild Session 1 exactly.
# 2) refund.recorded — refund adjustment for the monetization projection.
#
# IMPORTANT: the stored partition rule is the same deterministic rule verified
# by self_test.py: partition_id = website_session_id % NUM_PARTITIONS.
INSERT_SQL = r"""
WITH ranked_pageviews AS (
    SELECT
        p.website_pageview_id,
        p.created_at,
        p.website_session_id,
        p.pageview_url,
        s.user_id,
        s.is_repeat_session,
        s.utm_source,
        s.utm_campaign,
        s.utm_content,
        s.device_type,
        s.http_referer,
        ROW_NUMBER() OVER (
            PARTITION BY p.website_session_id
            ORDER BY p.created_at DESC, p.website_pageview_id DESC
        ) AS reverse_rn
    FROM website_pageviews p
    JOIN website_sessions s
      ON s.website_session_id = p.website_session_id
),
pageview_events AS (
    SELECT
        p.website_session_id AS partition_key,
        p.created_at AS event_time,
        'pageview.recorded'::text AS event_type,
        ('pageview:' || p.website_pageview_id)::text AS event_id,
        jsonb_build_object(
            'schema_version', %s,
            'website_pageview_id', p.website_pageview_id,
            'website_session_id', p.website_session_id,
            'user_id', p.user_id,
            'pageview_url', p.pageview_url,
            'device_type', p.device_type,
            'is_repeat_session', p.is_repeat_session,
            'utm_source', p.utm_source,
            'utm_campaign', p.utm_campaign,
            'utm_content', p.utm_content,
            'http_referer', p.http_referer,
            'is_last_pageview', (p.reverse_rn = 1),
            'converted', (p.reverse_rn = 1 AND o.order_id IS NOT NULL),
            'order_id', CASE WHEN p.reverse_rn = 1 THEN o.order_id ELSE NULL END,
            'primary_product_id', CASE WHEN p.reverse_rn = 1 THEN o.primary_product_id ELSE NULL END,
            'items_purchased', CASE WHEN p.reverse_rn = 1 THEN o.items_purchased ELSE NULL END,
            'order_revenue_usd', CASE WHEN p.reverse_rn = 1 THEN o.price_usd ELSE NULL END,
            'order_cogs_usd', CASE WHEN p.reverse_rn = 1 THEN o.cogs_usd ELSE NULL END,
            'gross_profit_usd', CASE WHEN p.reverse_rn = 1 THEN (o.price_usd - o.cogs_usd) ELSE NULL END
        ) AS payload
    FROM ranked_pageviews p
    LEFT JOIN orders o
      ON o.website_session_id = p.website_session_id
),
refund_events AS (
    SELECT
        o.website_session_id AS partition_key,
        r.created_at AS event_time,
        'refund.recorded'::text AS event_type,
        ('refund:' || r.order_item_refund_id)::text AS event_id,
        jsonb_build_object(
            'schema_version', %s,
            'order_item_refund_id', r.order_item_refund_id,
            'order_item_id', r.order_item_id,
            'order_id', r.order_id,
            'website_session_id', o.website_session_id,
            'refund_amount_usd', r.refund_amount_usd
        ) AS payload
    FROM order_item_refunds r
    JOIN orders o ON o.order_id = r.order_id
),
all_events AS (
    SELECT * FROM pageview_events
    UNION ALL
    SELECT * FROM refund_events
)
INSERT INTO retailmetrics_event_log
    (topic, partition_id, partition_key, event_time, event_type, event_id, payload)
SELECT
    %s,
    MOD(partition_key, %s)::integer,
    partition_key,
    event_time,
    event_type,
    event_id,
    payload
FROM all_events
ORDER BY event_time, event_id
ON CONFLICT (event_id) DO NOTHING
"""


def verify_enrichment(cur):
    """Prove enrichment does not change event-source cardinality."""
    cur.execute("SELECT COUNT(*) FROM website_pageviews")
    pageviews_before = int(cur.fetchone()[0])

    cur.execute(
        """
        SELECT COUNT(*)
        FROM website_pageviews p
        JOIN website_sessions s
          ON s.website_session_id = p.website_session_id
        LEFT JOIN orders o
          ON o.website_session_id = p.website_session_id
        """
    )
    pageviews_after = int(cur.fetchone()[0])

    cur.execute("SELECT COUNT(*) FROM order_item_refunds")
    refunds_before = int(cur.fetchone()[0])

    cur.execute(
        """
        SELECT COUNT(*)
        FROM order_item_refunds r
        JOIN orders o ON o.order_id = r.order_id
        """
    )
    refunds_after = int(cur.fetchone()[0])

    # Required row-count guards for the enrichment joins.
    assert pageviews_after == pageviews_before, (
        f"Pageview enrichment changed row count: {pageviews_before:,} -> {pageviews_after:,}"
    )
    assert refunds_after == refunds_before, (
        f"Refund enrichment changed row count: {refunds_before:,} -> {refunds_after:,}"
    )

    return {
        "pageviews_before": pageviews_before,
        "pageviews_after": pageviews_after,
        "refunds_before": refunds_before,
        "refunds_after": refunds_after,
        "assertions": [
            "pageviews_after == pageviews_before",
            "refunds_after == refunds_before",
        ],
        "passed": True,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Clear retained Session 2 topic and offsets before producing."
    )
    args = parser.parse_args()

    conn = connect()
    started = time.perf_counter()
    try:
        with conn.cursor() as cur:
            enrichment = verify_enrichment(cur)

            if args.reset:
                cur.execute(
                    "DELETE FROM retailmetrics_consumer_offsets WHERE topic=%s",
                    (cfg.TOPIC,),
                )
                cur.execute(
                    "DELETE FROM retailmetrics_consumer_partition_offsets WHERE topic=%s",
                    (cfg.TOPIC,),
                )
                cur.execute(
                    "DELETE FROM retailmetrics_event_log WHERE topic=%s",
                    (cfg.TOPIC,),
                )
                conn.commit()

            expected_events = (
                enrichment["pageviews_before"] + enrichment["refunds_before"]
            )

            cur.execute(
                "SELECT COUNT(*) FROM retailmetrics_event_log WHERE topic=%s",
                (cfg.TOPIC,),
            )
            before = int(cur.fetchone()[0])

            cur.execute(
                INSERT_SQL,
                (
                    SCHEMA_VERSION,
                    SCHEMA_VERSION,
                    cfg.TOPIC,
                    cfg.NUM_PARTITIONS,
                ),
            )
            inserted = max(0, int(cur.rowcount))
        conn.commit()

        elapsed = time.perf_counter() - started

        with conn.cursor() as cur:
            cur.execute(
                """SELECT COUNT(*), MIN(log_offset), MAX(log_offset),
                          MIN(event_time), MAX(event_time),
                          COUNT(DISTINCT partition_key)
                   FROM retailmetrics_event_log WHERE topic=%s""",
                (cfg.TOPIC,),
            )
            count, mn_off, mx_off, mn_time, mx_time, distinct_keys = cur.fetchone()

            cur.execute(
                """SELECT partition_id, COUNT(*)
                   FROM retailmetrics_event_log
                   WHERE topic=%s
                   GROUP BY partition_id ORDER BY partition_id""",
                (cfg.TOPIC,),
            )
            parts = [(int(pid), int(n)) for pid, n in cur.fetchall()]

            cur.execute("SELECT pg_total_relation_size('retailmetrics_event_log')")
            log_bytes = int(cur.fetchone()[0] or 0)

        count = int(count)
        if args.reset:
            assert count == expected_events, (
                f"Produced event count mismatch: expected {expected_events:,}, got {count:,}"
            )

        counts = [n for _, n in parts]
        even_share = (sum(counts) / len(counts)) if counts else 0
        skew_ratio = (max(counts) / min(counts)) if counts and min(counts) else 0

        enrichment["expected_events"] = expected_events
        (cfg.RESULTS / "enrichment_report.json").write_text(
            json.dumps(enrichment, indent=2), encoding="utf-8"
        )

        report = {
            "topic": cfg.TOPIC,
            "event_types": ["pageview.recorded", "refund.recorded"],
            "schema_version": SCHEMA_VERSION,
            "partition_key": cfg.PARTITION_KEY,
            "routing_rule": "website_session_id % 4",
            "event_time": cfg.EVENT_TIME,
            "pageview_events_expected": enrichment["pageviews_before"],
            "refund_events_expected": enrichment["refunds_before"],
            "total_events_expected": expected_events,
            "events_before": before,
            "events_inserted": inserted,
            "events_after": count,
            "distinct_partition_keys": int(distinct_keys or 0),
            "offset_min": int(mn_off or 0),
            "offset_max": int(mx_off or 0),
            "event_time_min": str(mn_time),
            "event_time_max": str(mx_time),
            "sort_applied": "ORDER BY event_time, event_id before insertion",
            "partitions": parts,
            "even_share": even_share,
            "skew_ratio": skew_ratio,
            "log_size_bytes": log_bytes,
            "log_size_mb": log_bytes / (1024 * 1024),
            "elapsed_s": elapsed,
            "events_per_sec": (inserted / elapsed) if elapsed else 0,
            "reset": bool(args.reset),
            "enrichment_assertions_passed": True,
        }
        (cfg.RESULTS / "producer_summary.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )

        print("RETAILMETRICS SESSION 2 - PRODUCE DURABLE EVENTS")
        print("=" * 72)
        print(f"topic                 : {cfg.TOPIC}")
        print("event types           : pageview.recorded, refund.recorded")
        print(f"schema version        : {SCHEMA_VERSION}")
        print(f"routing               : website_session_id % {cfg.NUM_PARTITIONS}")
        print("enrichment guard      : PASS (row counts unchanged)")
        print(f"pageview events       : {enrichment['pageviews_before']:,}")
        print(f"refund events         : {enrichment['refunds_before']:,}")
        print(f"expected total        : {expected_events:,}")
        print(f"events before         : {before:,}")
        print(f"events inserted       : {inserted:,}")
        print(f"events after          : {count:,}")
        print(f"distinct session keys : {int(distinct_keys or 0):,}")
        print(f"event-time range      : {mn_time} -> {mx_time}")
        print("sort before publishing: event_time, event_id")
        print(f"elapsed               : {elapsed:.3f} s")
        print(f"throughput            : {(inserted/elapsed if elapsed else 0):,.0f} events/s")
        print(f"log size              : {log_bytes/(1024*1024):.2f} MB")
        print(f"partition skew        : {skew_ratio:.2f} : 1")
        for pid, n in parts:
            print(f"partition {pid}           : {n:,}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
