from __future__ import annotations
import os
from pathlib import Path

BASE = Path(__file__).resolve().parent
PROJECT_ROOT = BASE.parent
SESSION1_DIR = PROJECT_ROOT / "session1_parallel_compute"
SESSION1_RESULTS = SESSION1_DIR / "results"
SESSION1_DATASETS = SESSION1_DIR / "datasets"

RESULTS = BASE / "results"
RESULTS.mkdir(exist_ok=True)
DOCS_DIR = BASE / "docs"
ARCH_DIR = BASE / "architecture"
DOCS_DIR.mkdir(exist_ok=True)
ARCH_DIR.mkdir(exist_ok=True)

PG_HOST = os.getenv("RETAILMETRICS_PG_HOST", "localhost")
PG_PORT = int(os.getenv("RETAILMETRICS_PG_PORT", "5432"))
PG_DATABASE = os.getenv("RETAILMETRICS_PG_DATABASE", "retailmetrics")
PG_USER = os.getenv("RETAILMETRICS_PG_USER", "postgres")
PG_PASSWORD = os.getenv("RETAILMETRICS_PG_PASSWORD", "")

TOPIC = "commerce.activity.recorded"
PARTITION_KEY = "website_session_id"
EVENT_TIME = "created_at"
NUM_PARTITIONS = 4

PROJECTOR_GROUP = "session-metrics-projector"
AUDIT_GROUP = "conversion-audit-writer"
REFUND_GROUP = "refund-monitor"
MONETIZATION_GROUP = "monetization-analytics"

EXPECTED_SESSIONS = 472_871
EXPECTED_PAGEVIEWS = 1_188_124
EXPECTED_ORDERS = 32_313
EXPECTED_ORDER_ITEMS = 40_025
EXPECTED_REFUNDS = 1_731
EXPECTED_PRODUCTS = 4
