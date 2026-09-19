# Toy Store E-Commerce Database Dataset

## MIT 261 – Parallel and Distributed Systems
### Session 1: Foundations in In-Memory Cluster Compute

This project uses the **Toy Store E-Commerce Database** from Kaggle to demonstrate data profiling, relational joins, partitioning strategy, sequential processing, bounded parallel processing with PySpark, benchmarking, partition-balance analysis, and correctness validation.

## Project Title

**EcomJourney: A Parallel E-Commerce Analytics Framework for Customer Journey, Conversion, and Revenue Intelligence**

## Dataset Source

**Kaggle Dataset:** Toy Store E-Commerce Database  
https://www.kaggle.com/datasets/siddharth0935/toy-store-e-commerce-database

## Dataset Files

The project uses the following related CSV files:

| File | Role | Approx. Rows | Description |
|---|---|---:|---|
| `website_sessions.csv` | Event / Entity | 472,871 | Website session and marketing-source information |
| `website_pageviews.csv` | Event | 1,188,124 | Pageview activity associated with website sessions |
| `orders.csv` | Event | 32,313 | Order-level sales information |
| `order_items.csv` | Event | 40,025 | Individual products purchased per order |
| `order_item_refunds.csv` | Event | 1,731 | Refund transactions for order items |
| `products.csv` | Entity | 4 | Product master information |

## Main Relationships

- `WebsiteSession 1 -> many WebsitePageview`
- `WebsiteSession 1 -> 0..1 Order`
- `Order 1 -> many OrderItem`
- `Product 1 -> many OrderItem`
- `OrderItem 1 -> 0..1 OrderItemRefund`

The dataset provides genuine one-to-many relationships and timestamped event data suitable for parallel and distributed processing activities.

## Session 1 Analytical Design

The main Session 1 workload starts with `website_pageviews.csv` as the event stream, enriches it with session information from `website_sessions.csv`, and left-joins optional order information from `orders.csv`.

### Partition Key

```text
website_session_id
```

This key is owned by the website-session entity and naturally groups all pageview activity belonging to the same session.

### Event Time

```text
website_pageviews.created_at
```

### Main Metrics

For each website session, the program computes:

- Pageview count
- Session duration
- Conversion flag
- Order revenue
- Gross profit

Order-level revenue is aggregated carefully so it is not multiplied by the number of pageviews in the same session.

## Project Structure

```text
session1_parallel_compute/
├── architecture/
├── datasets/
├── docs/
├── results/
├── benchmark.py
├── config.py
├── load_and_join.py
├── parallel_compute.py
├── partition_analysis.py
├── partition_strategy.py
├── profile_files.py
├── render_diagrams.py
├── sequential_baseline.py
├── RUN_ORDER.txt
└── README.md
```

## Requirements

Recommended environment:

- Python 3.11+
- pandas
- PySpark
- pyarrow
- Graphviz

Create and activate a virtual environment:

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
```

Install the required Python packages:

```powershell
pip install pandas pyspark pyarrow
```

Graphviz is required only for diagram rendering.

## Dataset Setup

Place these files inside the `datasets/` directory:

```text
website_sessions.csv
website_pageviews.csv
orders.csv
order_items.csv
order_item_refunds.csv
products.csv
```

## Run Order

Execute the scripts in this order:

```powershell
python profile_files.py
python load_and_join.py
python partition_strategy.py
python sequential_baseline.py
python parallel_compute.py
python benchmark.py
python partition_analysis.py
python render_diagrams.py
```

## Script Purpose

| Script | Purpose |
|---|---|
| `profile_files.py` | Profiles files, row counts, PK/FK integrity, nulls, and multiplicity |
| `load_and_join.py` | Loads and joins pageviews, sessions, and orders with row reconciliation |
| `partition_strategy.py` | Evaluates candidate keys and documents the chosen partition strategy |
| `sequential_baseline.py` | Runs the pandas sequential reference implementation |
| `parallel_compute.py` | Runs the PySpark bounded parallel computation and validates correctness |
| `benchmark.py` | Compares sequential execution with multiple Spark partition settings |
| `partition_analysis.py` | Measures the physical balance of Spark partitions |
| `render_diagrams.py` | Generates the entity-model and architecture diagrams |

## Generated Outputs

The scripts generate files such as:

```text
results/
├── file_profile.json
├── partition_strategy.json
├── baseline_result.csv
├── working_dataset.parquet
├── session_journey_metrics.parquet
├── validation_report.json
├── session1_benchmark.csv
└── partition_sizes.csv
```

Diagram files are generated under:

```text
docs/
architecture/
```

## Correctness Validation

The parallel result is compared against the sequential baseline using:

- Number of output groups
- Pageview count
- Session duration
- Conversion status
- Revenue
- Gross profit

Floating-point metrics are compared using a defined numerical tolerance.

## Parallel Benchmarking

The benchmark evaluates bounded Spark execution using:

```text
2 partitions
4 partitions
8 partitions
```

The purpose is to measure the effect of different partition counts on execution time while preserving identical results.

## Continuity to Later Sessions

This dataset can also support the succeeding MIT 261 activities:

- **Session 2:** Replay pageviews, sessions, and orders using `created_at` as event time.
- **Session 3:** Model session, order, product, and refund components as service boundaries.
- **Session 4:** Apply time-window analytics to traffic, conversion, revenue, and campaign performance.
- **Session 5:** Containerize the analytics pipeline and runtime.
- **Session 6:** Automate setup, validation, and testing through Infrastructure as Code and CI workflows.

## Academic Use

This repository was prepared for academic work in **MIT 261 – Parallel and Distributed Systems**. The original dataset remains the property of its respective Kaggle publisher and contributors.

## AI-Assisted Development Disclosure

AI tools were used as development assistance for code organization, debugging support, documentation, and explanation. Dataset selection, execution, validation, interpretation of results, and final submission remain the responsibility of the student.
