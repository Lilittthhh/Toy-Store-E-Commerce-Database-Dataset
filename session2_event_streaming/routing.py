from __future__ import annotations

import config as cfg


def partition_for(partition_key: int) -> int:
    """Stable broker-neutral routing rule used by producer and self-test.

    website_session_id is already a stable integer identifier, so modulo routing
    is deterministic across processes and machines and preserves session affinity.
    """
    return int(partition_key) % int(cfg.NUM_PARTITIONS)
