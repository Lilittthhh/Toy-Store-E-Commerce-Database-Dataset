from __future__ import annotations

import os

import pytest

from retailmetrics_s3.config import SESSION1_RESULTS, SESSION2_RESULTS, settings
from retailmetrics_s3.db import CanonicalRepository, _assert_select, read_only_connection
from retailmetrics_s3.experiments.reconciliation import reconciliation_report
from retailmetrics_s3.service_core import RetailMetricsServiceCore, load_snapshot


def _database_configured():
    return bool(os.getenv("RETAILMETRICS_PG_PASSWORD"))


@pytest.mark.integration
@pytest.mark.skipif(not _database_configured(), reason="read-only PostgreSQL credentials not configured")
def test_session1_and_session2_reconciliation():
    repo = CanonicalRepository(settings())
    report = reconciliation_report(RetailMetricsServiceCore(load_snapshot(repo)), SESSION1_RESULTS, SESSION2_RESULTS)
    assert report["passed"] is True
    assert all(item["passed"] for item in report["comparisons"])
    assert report["refund_comparison"]["passed"] is True


@pytest.mark.integration
@pytest.mark.skipif(not _database_configured(), reason="read-only PostgreSQL credentials not configured")
def test_database_connection_and_fingerprint_are_read_only():
    cfg = settings(); repo = CanonicalRepository(cfg); before = repo.safety_fingerprint()
    with read_only_connection(cfg) as conn, conn.cursor() as cur:
        cur.execute("SHOW transaction_read_only")
        assert cur.fetchone()[0] == "on"
    assert repo.safety_fingerprint() == before


def test_sql_guard_rejects_mutation_before_execution():
    for sql in ("INSERT INTO products VALUES (1)", "UPDATE orders SET user_id=1", "DELETE FROM app_users", "CREATE TABLE unsafe(x int)"):
        with pytest.raises(ValueError): _assert_select(sql)

