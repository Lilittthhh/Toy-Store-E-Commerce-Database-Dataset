from __future__ import annotations
import argparse
import json
import time

import config as cfg
from db import connect

def monetization_snapshot(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                COUNT(*) FILTER (
                    WHERE event_type='pageview.recorded'
                      AND COALESCE((payload->>'is_last_pageview')::boolean,false)
                ) AS sessions,
                COUNT(*) FILTER (
                    WHERE event_type='pageview.recorded'
                      AND COALESCE((payload->>'converted')::boolean,false)
                ) AS converted,
                COALESCE(SUM(
                    CASE
                        WHEN event_type='pageview.recorded'
                         AND COALESCE((payload->>'converted')::boolean,false)
                        THEN (payload->>'order_revenue_usd')::numeric
                        ELSE 0
                    END
                ),0) AS gross_revenue,
                COALESCE(SUM(
                    CASE
                        WHEN event_type='pageview.recorded'
                         AND COALESCE((payload->>'converted')::boolean,false)
                        THEN (payload->>'order_cogs_usd')::numeric
                        ELSE 0
                    END
                ),0) AS cogs,
                COALESCE(SUM(
                    CASE
                        WHEN event_type='pageview.recorded'
                         AND COALESCE((payload->>'converted')::boolean,false)
                        THEN (payload->>'gross_profit_usd')::numeric
                        ELSE 0
                    END
                ),0) AS gross_profit,
                COALESCE(SUM(
                    CASE
                        WHEN event_type='refund.recorded'
                        THEN (payload->>'refund_amount_usd')::numeric
                        ELSE 0
                    END
                ),0) AS refunds
            FROM retailmetrics_event_log
            WHERE topic=%s
            """,
            (cfg.TOPIC,),
        )
        sessions, converted, revenue, cogs, profit, refunds = cur.fetchone()

        cur.execute(
            """
            SELECT
                COALESCE(payload->>'utm_source','NULL') AS source,
                COUNT(*) FILTER (
                    WHERE event_type='pageview.recorded'
                      AND COALESCE((payload->>'is_last_pageview')::boolean,false)
                ) AS sessions,
                COUNT(*) FILTER (
                    WHERE event_type='pageview.recorded'
                      AND COALESCE((payload->>'converted')::boolean,false)
                ) AS conversions,
                COALESCE(SUM(
                    CASE
                        WHEN event_type='pageview.recorded'
                         AND COALESCE((payload->>'converted')::boolean,false)
                        THEN (payload->>'order_revenue_usd')::numeric
                        ELSE 0
                    END
                ),0) AS revenue
            FROM retailmetrics_event_log
            WHERE topic=%s
              AND event_type='pageview.recorded'
            GROUP BY COALESCE(payload->>'utm_source','NULL')
            ORDER BY revenue DESC
            """,
            (cfg.TOPIC,),
        )

        sources = [
            {
                "source": str(source),
                "sessions": int(sess),
                "conversions": int(conv),
                "revenue_usd": float(revenue or 0),
            }
            for source, sess, conv, revenue in cur.fetchall()
        ]

        cur.execute(
            """
            SELECT
                COALESCE((payload->>'primary_product_id')::integer,0) AS product_id,
                COUNT(*) AS orders,
                COALESCE(SUM((payload->>'order_revenue_usd')::numeric),0) AS revenue,
                COALESCE(SUM((payload->>'gross_profit_usd')::numeric),0) AS profit
            FROM retailmetrics_event_log
            WHERE topic=%s
              AND event_type='pageview.recorded'
              AND COALESCE((payload->>'converted')::boolean,false)
            GROUP BY COALESCE((payload->>'primary_product_id')::integer,0)
            ORDER BY revenue DESC
            """,
            (cfg.TOPIC,),
        )

        products = [
            {
                "product_id": int(pid),
                "orders": int(orders),
                "revenue_usd": float(revenue or 0),
                "gross_profit_usd": float(profit or 0),
            }
            for pid, orders, revenue, profit in cur.fetchall()
        ]

    sessions = int(sessions or 0)
    converted = int(converted or 0)
    gross_revenue = float(revenue or 0)
    cogs = float(cogs or 0)
    gross_profit = float(profit or 0)
    refunds = float(refunds or 0)

    return {
        "sessions": sessions,
        "converted_sessions": converted,
        "conversion_rate_pct": (converted / sessions * 100) if sessions else 0,
        "gross_revenue_usd": gross_revenue,
        "cogs_usd": cogs,
        "gross_profit_usd": gross_profit,
        "refunds_usd": refunds,
        "net_revenue_usd": gross_revenue - refunds,
        "traffic_sources": sources,
        "products": products,
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--from-time",
        default="",
        help="Optional ISO timestamp for the partial replay demonstration.",
    )
    args = parser.parse_args()

    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*), MIN(event_time), MAX(event_time)
                FROM retailmetrics_event_log
                WHERE topic=%s
                """,
                (cfg.TOPIC,),
            )
            total, mn, mx = cur.fetchone()

        total = int(total)
        if total == 0:
            raise RuntimeError("Event log is empty. Run Produce first.")

        t0 = time.perf_counter()
        snap1 = monetization_snapshot(conn)
        late_seconds = time.perf_counter() - t0

        snap2 = monetization_snapshot(conn)
        deterministic = snap1 == snap2

        offline_processed = total
        offline_lag = 0

        partial_from = args.from_time.strip()

        if partial_from:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM retailmetrics_event_log
                    WHERE topic=%s
                      AND event_time >= %s::timestamp
                    """,
                    (cfg.TOPIC, partial_from),
                )
                partial = int(cur.fetchone()[0])
        else:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT percentile_cont(0.8)
                    WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM event_time))
                    FROM retailmetrics_event_log
                    WHERE topic=%s
                    """,
                    (cfg.TOPIC,),
                )
                epoch = cur.fetchone()[0]

                cur.execute(
                    "SELECT to_timestamp(%s)::timestamp",
                    (epoch,),
                )
                partial_from = str(cur.fetchone()[0])

                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM retailmetrics_event_log
                    WHERE topic=%s
                      AND EXTRACT(EPOCH FROM event_time) >= %s
                    """,
                    (cfg.TOPIC, epoch),
                )
                partial = int(cur.fetchone()[0])

        report = {
            "event_time_min": str(mn),
            "event_time_max": str(mx),
            "new_consumer_history": {
                "events_consumed": total,
                "seconds": late_seconds,
            },
            "deterministic_replay": deterministic,
            "offline_catch_up": {
                "events_processed": offline_processed,
                "final_lag": offline_lag,
            },
            "partial_replay": {
                "from_time": partial_from,
                "events": partial,
                "share_pct": partial / total * 100 if total else 0,
            },
            "monetization": snap1,
        }

        (cfg.RESULTS / "replay_suite.json").write_text(
            json.dumps(report, indent=2),
            encoding="utf-8",
        )
        (cfg.RESULTS / "monetization_snapshot.json").write_text(
            json.dumps(snap1, indent=2),
            encoding="utf-8",
        )

        print("RETAILMETRICS REPLAY SUITE")
        print("=" * 72)
        print(f"new consumer read history : {total:,} events")
        print(f"deterministic replay       : {deterministic}")
        print(f"offline catch-up final lag : {offline_lag}")
        print(
            f"partial replay from        : {partial_from} -> "
            f"{partial:,} ({partial/total*100:.1f}%)"
        )
        print("\nMONETIZATION MECHANISM")
        print(
            "website session -> pageviews -> purchase conversion -> revenue -> "
            "COGS -> gross profit -> refund -> net revenue"
        )
        print(f"gross revenue              : ${snap1['gross_revenue_usd']:,.2f}")
        print(f"refunds                    : ${snap1['refunds_usd']:,.2f}")
        print(f"net revenue                : ${snap1['net_revenue_usd']:,.2f}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
