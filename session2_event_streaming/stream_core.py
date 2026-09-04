from __future__ import annotations
from db import connect
import config as cfg


def ensure_consumer(cur, consumer_name: str):
    cur.execute(
        """INSERT INTO retailmetrics_consumer_offsets(consumer_name, topic, last_offset)
           VALUES (%s,%s,0)
           ON CONFLICT (consumer_name, topic) DO NOTHING""",
        (consumer_name, cfg.TOPIC),
    )
    for partition_id in range(cfg.NUM_PARTITIONS):
        cur.execute(
            """INSERT INTO retailmetrics_consumer_partition_offsets
               (consumer_name, topic, partition_id, last_offset)
               VALUES (%s,%s,%s,0)
               ON CONFLICT (consumer_name, topic, partition_id) DO NOTHING""",
            (consumer_name, cfg.TOPIC, partition_id),
        )


def get_offset(cur, consumer_name: str) -> int:
    ensure_consumer(cur, consumer_name)
    cur.execute(
        """SELECT last_offset FROM retailmetrics_consumer_offsets
           WHERE consumer_name=%s AND topic=%s""",
        (consumer_name, cfg.TOPIC),
    )
    return int(cur.fetchone()[0])


def set_offset(cur, consumer_name: str, offset: int):
    cur.execute(
        """UPDATE retailmetrics_consumer_offsets
           SET last_offset=%s, updated_at=NOW()
           WHERE consumer_name=%s AND topic=%s""",
        (int(offset), consumer_name, cfg.TOPIC),
    )


def set_partition_offsets_to_end(cur, consumer_name: str):
    ensure_consumer(cur, consumer_name)
    cur.execute(
        """WITH ends AS (
               SELECT partition_id, COALESCE(MAX(log_offset),0) AS end_offset
               FROM retailmetrics_event_log
               WHERE topic=%s
               GROUP BY partition_id
           )
           UPDATE retailmetrics_consumer_partition_offsets c
           SET last_offset=ends.end_offset, updated_at=NOW()
           FROM ends
           WHERE c.consumer_name=%s
             AND c.topic=%s
             AND c.partition_id=ends.partition_id""",
        (cfg.TOPIC, consumer_name, cfg.TOPIC),
    )


def reset_consumer(consumer_name: str):
    conn = connect()
    try:
        with conn.cursor() as cur:
            ensure_consumer(cur, consumer_name)
            set_offset(cur, consumer_name, 0)
            cur.execute(
                """UPDATE retailmetrics_consumer_partition_offsets
                   SET last_offset=0, updated_at=NOW()
                   WHERE consumer_name=%s AND topic=%s""",
                (consumer_name, cfg.TOPIC),
            )
        conn.commit()
    finally:
        conn.close()


def end_offset(conn=None) -> int:
    own = conn is None
    conn = conn or connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(MAX(log_offset),0) FROM retailmetrics_event_log WHERE topic=%s",
                (cfg.TOPIC,),
            )
            return int(cur.fetchone()[0])
    finally:
        if own:
            conn.close()


def lag(consumer_name: str) -> tuple[int, int, int]:
    """Return (committed_log_offset, end_log_offset, unread_retained_event_count).

    log_offset is a durable sequence identifier, not an event count. PostgreSQL
    sequences do not reset when rows are deleted/reproduced, so lag must be
    counted from retained rows after the consumer's committed offset rather
    than calculated as end_offset - current_offset.
    """
    conn = connect()
    try:
        with conn.cursor() as cur:
            ensure_consumer(cur, consumer_name)
            current = get_offset(cur, consumer_name)
            end = end_offset(conn)
            cur.execute(
                """SELECT COUNT(*)
                   FROM retailmetrics_event_log
                   WHERE topic=%s AND log_offset > %s""",
                (cfg.TOPIC, current),
            )
            unread = int(cur.fetchone()[0])
        conn.commit()
        return current, end, unread
    finally:
        conn.close()
