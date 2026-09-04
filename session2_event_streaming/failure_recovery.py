from __future__ import annotations
import argparse
import json
import time
from db import connect
import config as cfg

DEFAULT_FAIL_AFTER = 250_000
COMMIT_EVERY = 50_000


def nth_log_offset(cur, n: int) -> int:
    """Return the global log_offset for the nth retained topic event (1-based)."""
    if n <= 0:
        return 0
    cur.execute(
        """SELECT log_offset
           FROM retailmetrics_event_log
           WHERE topic=%s
           ORDER BY log_offset
           OFFSET %s LIMIT 1""",
        (cfg.TOPIC, n-1),
    )
    row = cur.fetchone()
    return int(row[0]) if row else 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fail-after", type=int, default=DEFAULT_FAIL_AFTER,
        help="Number of events handled before the audit consumer crashes."
    )
    args = parser.parse_args()

    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM retailmetrics_event_log WHERE topic=%s",
                (cfg.TOPIC,),
            )
            total_events = int(cur.fetchone()[0])
        if total_events == 0:
            raise RuntimeError("Event log is empty. Run Produce first.")

        handled = max(1, min(int(args.fail_after), total_events))
        committed_count = (handled // COMMIT_EVERY) * COMMIT_EVERY
        if committed_count == handled and committed_count > 0:
            committed_count -= COMMIT_EVERY

        with conn.cursor() as cur:
            handled_offset = nth_log_offset(cur, handled)
            committed_offset = nth_log_offset(cur, committed_count)

            # Clean failure-demo sink, then ACTUALLY process the pre-crash events.
            cur.execute("TRUNCATE retailmetrics_failure_audit")
            cur.execute(
                """INSERT INTO retailmetrics_failure_audit(event_id,log_offset)
                   SELECT event_id,log_offset
                   FROM retailmetrics_event_log
                   WHERE topic=%s AND log_offset <= %s
                   ORDER BY log_offset
                   ON CONFLICT (event_id) DO NOTHING""",
                (cfg.TOPIC, handled_offset),
            )
            precrash_written = max(0, int(cur.rowcount))
        conn.commit()

        backlog = total_events - committed_count
        expected_redelivered = handled - committed_count

        # Simulate process loss by closing the connection. The rows written after
        # committed_offset remain side effects, but the restarted consumer only
        # knows the committed offset and therefore receives them again.
        conn.close()

        recovery_started = time.perf_counter()
        conn = connect()
        with conn.cursor() as cur:
            # ACTUAL catch-up from committed offset. ON CONFLICT makes the audit
            # sink idempotent: redelivered event_ids are rejected as duplicates.
            cur.execute(
                """WITH candidates AS (
                       SELECT event_id,log_offset
                       FROM retailmetrics_event_log
                       WHERE topic=%s AND log_offset > %s
                       ORDER BY log_offset
                   ), inserted AS (
                       INSERT INTO retailmetrics_failure_audit(event_id,log_offset)
                       SELECT event_id,log_offset FROM candidates
                       ON CONFLICT (event_id) DO NOTHING
                       RETURNING event_id
                   )
                   SELECT
                     (SELECT COUNT(*) FROM candidates) AS delivery_attempts,
                     (SELECT COUNT(*) FROM inserted) AS newly_written""",
                (cfg.TOPIC, committed_offset),
            )
            delivery_attempts, newly_written = [int(x) for x in cur.fetchone()]
            duplicates_skipped = delivery_attempts - newly_written

            cur.execute("SELECT COUNT(*) FROM retailmetrics_failure_audit")
            final_records = int(cur.fetchone()[0])

            cur.execute(
                """INSERT INTO retailmetrics_consumer_offsets(consumer_name,topic,last_offset)
                   VALUES (%s,%s,%s)
                   ON CONFLICT (consumer_name,topic)
                   DO UPDATE SET last_offset=EXCLUDED.last_offset, updated_at=NOW()""",
                ("flaky-conversion-audit", cfg.TOPIC, nth_log_offset(cur, total_events)),
            )
        conn.commit()
        recovery_seconds = time.perf_counter() - recovery_started

        assert duplicates_skipped == expected_redelivered, (
            f"Expected {expected_redelivered:,} redeliveries, observed {duplicates_skipped:,}"
        )
        assert final_records == total_events, (
            f"Idempotent recovery should end with {total_events:,} unique audit records, got {final_records:,}"
        )

        report = {
            "consumer": "flaky-conversion-audit",
            "delivery_semantic": "at-least-once",
            "commit_location": "offset is advanced only after a committed processing batch",
            "commit_frequency_events": COMMIT_EVERY,
            "events_in_log": total_events,
            "failure_after_handled": handled,
            "handled_log_offset": handled_offset,
            "committed_event_count": committed_count,
            "committed_before_crash": committed_offset,
            "precrash_records_written": precrash_written,
            "backlog_left_in_log": backlog,
            "events_processed_during_recovery": delivery_attempts,
            "new_records_during_recovery": newly_written,
            "events_redelivered": duplicates_skipped,
            "duplicates_skipped_by_event_id": duplicates_skipped,
            "total_records_written_unique": final_records,
            "final_lag": 0,
            "recovery_seconds": recovery_seconds,
            "events_lost": 0,
            "idempotency_mechanism": "retailmetrics_failure_audit.event_id PRIMARY KEY + ON CONFLICT DO NOTHING",
            "blast_radius": [
                {"component": "Producer", "status": "UNAFFECTED", "evidence": f"{total_events:,} events already retained"},
                {"component": cfg.PROJECTOR_GROUP, "status": "UNAFFECTED", "evidence": "independent consumer group and offsets"},
                {"component": cfg.REFUND_GROUP, "status": "UNAFFECTED", "evidence": "independent consumer group and offsets"},
                {"component": "flaky-conversion-audit", "status": "DOWN THEN RECOVERED", "evidence": f"resumed from committed log_offset {committed_offset:,}"},
            ],
        }
        (cfg.RESULTS / "failure_recovery.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )

        print("RETAILMETRICS FAILURE & RECOVERY")
        print("=" * 72)
        print(f"events in log            : {total_events:,}")
        print(f"handled before crash     : {handled:,}")
        print(f"committed event count    : {committed_count:,}")
        print(f"committed log_offset     : {committed_offset:,}")
        print(f"backlog after crash      : {backlog:,}")
        print(f"catch-up delivery attempts: {delivery_attempts:,}")
        print(f"redelivered/skipped      : {duplicates_skipped:,}")
        print(f"unique records afterward : {final_records:,}")
        print(f"catch-up time            : {recovery_seconds:.3f} s")
        print("events lost              : 0")
        print("final lag                : 0")
        print("semantic                 : at-least-once")
    finally:
        try:
            conn.close()
        except Exception:
            pass

if __name__ == "__main__":
    main()
