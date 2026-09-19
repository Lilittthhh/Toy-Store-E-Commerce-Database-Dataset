from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "datasets"
RESULTS_DIR = BASE_DIR / "results"
DOCS_DIR = BASE_DIR / "docs"
ARCH_DIR = BASE_DIR / "architecture"

for p in (DATA_DIR, RESULTS_DIR, DOCS_DIR, ARCH_DIR):
    p.mkdir(parents=True, exist_ok=True)

DATASET_TITLE = "Toy Store E-Commerce Database"
KAGGLE_URL = "https://www.kaggle.com/datasets/siddharth0935/toy-store-e-commerce-database"

FILES = {
    "website_sessions": DATA_DIR / "website_sessions.csv",
    "website_pageviews": DATA_DIR / "website_pageviews.csv",
    "orders": DATA_DIR / "orders.csv",
    "order_items": DATA_DIR / "order_items.csv",
    "order_item_refunds": DATA_DIR / "order_item_refunds.csv",
    "products": DATA_DIR / "products.csv",
}

# Core Session 1 workload
PARTITION_KEY = "website_session_id"
EVENT_TIME_FIELD = "pageview_created_at"
METRIC_FIELD = "order_revenue_usd"

PARTITION_SETTINGS = (2, 4, 8)
BENCHMARK_REPEATS = 3
BASELINE_REPEATS = 5
CHOSEN_PARTITIONS = 4
TOLERANCE = 1e-6

SPARK_APP_NAME = "MIT261-ToyStore-Session1"
SPARK_MASTER = "local[*]"
SPARK_DRIVER_MEMORY = "4g"
SPARK_SHUFFLE_PARTITIONS = "8"

OUT_PROFILE = RESULTS_DIR / "file_profile.json"
OUT_JOINED = RESULTS_DIR / "working_dataset.parquet"
OUT_BASELINE = RESULTS_DIR / "baseline_result.csv"
OUT_FINAL = RESULTS_DIR / "session_journey_metrics.parquet"
OUT_VALIDATION = RESULTS_DIR / "validation_report.json"
OUT_BENCHMARK = RESULTS_DIR / "session1_benchmark.csv"
OUT_PARTITIONS = RESULTS_DIR / "partition_sizes.csv"
OUT_PARTITION_STRATEGY = RESULTS_DIR / "partition_strategy.json"

def require_files():
    missing = [str(p) for p in FILES.values() if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing dataset file(s):\n- " + "\n- ".join(missing) +
            "\n\nCopy the Kaggle CSV files into the datasets/ folder."
        )

def build_spark():
    from pyspark.sql import SparkSession
    spark = (
        SparkSession.builder
        .appName(SPARK_APP_NAME)
        .master(SPARK_MASTER)
        .config("spark.driver.memory", SPARK_DRIVER_MEMORY)
        .config("spark.sql.shuffle.partitions", SPARK_SHUFFLE_PARTITIONS)
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")
    return spark

def banner(title):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)
