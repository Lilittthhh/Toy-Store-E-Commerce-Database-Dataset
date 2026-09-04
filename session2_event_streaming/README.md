# RetailMetrics — Session 2 Event Streaming & Messaging Backbone

**Project title:** RetailMetrics: An E-Commerce Analytics System for Sales, Website Performance, and Revenue Intelligence

## What Session 2 does
Session 2 replays the Toy Store E-Commerce dataset established in Session 1 as a durable event stream and proves that the streamed session metrics reconcile with the Session 1 batch output.

## Session 1 handover
Run:

```powershell
python handover_verify.py
```

Evidence is written to `results/handover_verification.json`. It verifies:
- `session1_parallel_compute/datasets/` resolves and contains all six source CSV files;
- `session1_parallel_compute/results/session_journey_metrics.parquet` exists and loads;
- Session 1 group count and aggregate revenue/profit totals;
- inherited partition key `website_session_id`;
- event-time field `created_at`.

## Event contract
**Topic:** `commerce.activity.recorded`  
**Schema version:** `1`  
**Partitions:** `4`  
**Partition key:** `website_session_id`  
**Routing rule:** `website_session_id % 4`  
**Event time:** `created_at`

### `pageview.recorded`
Carries `schema_version`, `website_pageview_id`, `website_session_id`, `user_id`, `pageview_url`, device/session/UTM/referrer fields, `is_last_pageview`, `converted`, and—only on the final pageview of a converted session—`order_id`, `primary_product_id`, `items_purchased`, `order_revenue_usd`, `order_cogs_usd`, and `gross_profit_usd`.

### `refund.recorded`
Carries `schema_version`, refund/order/item IDs, `website_session_id`, and `refund_amount_usd`.

## Producer enrichment and row-count guard
`produce_events.py` enriches pageviews with `website_sessions` and `orders`, and refunds with `orders`. Before publishing, it asserts that both joins preserve the raw event-source row counts. The measured evidence is written to `results/enrichment_report.json`.

The producer sorts the combined event stream by `event_time, event_id` before insertion so event-time order is established at the stream boundary.

## Durable-log guarantees
`self_test.py` verifies:
1. stable routing using the same `website_session_id % 4` rule as the producer;
2. ordering within a partition;
3. non-destructive reads;
4. consumer-group isolation;
5. replay after offset reset;
6. local durability across application/process reconnection.

### Backbone limitation
This capstone uses a **single PostgreSQL instance as a file/broker-like durable log abstraction**. It persists events across application restarts but does **not** claim Kafka/Redpanda-style replication, leader election, broker failover, or multi-node fault tolerance.

## Consumer groups and fan-out
- `session-metrics-projector` — rebuilds Session 1 metrics and writes `results/stream_session_metrics.csv`; its database projection is keyed by `website_session_id` and is deterministically upserted.
- `conversion-audit-writer` — writes an audit sink keyed by `event_id`; redelivery is rejected with `ON CONFLICT DO NOTHING`.
- `refund-monitor` — writes an event-id keyed refund projection.
- `monetization-analytics` — late-joining replay-based view used by `replay_suite.py`.

The producer requires **zero code changes** to add another consumer group.

## Delivery semantic and idempotency
The failure demonstration implements **at-least-once** behavior: processing can occur after the last committed offset, so a crash can cause those events to be redelivered. `failure_recovery.py` actually resumes from the committed log offset, processes the backlog, and measures delivery attempts, newly inserted records, and duplicate/redelivered event IDs.

The failure audit sink uses `event_id PRIMARY KEY` + `ON CONFLICT DO NOTHING`, so redelivery does not change the logical final record count.

## Replay demonstrations
`replay_suite.py` records:
- a new consumer reading all retained history;
- rewind and deterministic reprocessing;
- offline consumer catch-up;
- partial replay from a timestamp.

The late-joining consumer computes transaction-driven monetization from the dataset mechanism:

`website session → pageviews → purchase conversion → order revenue → COGS → gross profit → refund → net revenue`

## Reconciliation
`reconcile.py` compares `results/stream_session_metrics.csv` with Session 1 `session_journey_metrics.parquet`.

CI pass condition:
- identical `website_session_id` set;
- identical group count;
- exact `pageview_count` and `converted` differences of `0`;
- `session_duration_seconds`, `order_revenue_usd`, and `gross_profit_usd` maximum absolute difference `<= 1e-6`;
- every core consumer finishes at lag `0`.

## Architecture diagram
Generate it with:

```powershell
python render_architecture.py
```

Output: `architecture_diagram.png`.

## End-to-end execution
Command line:

```powershell
python run_pipeline.py
```

Order:
1. Session 1 handover verification
2. streaming-table initialization
3. producer `--reset`
4. durable-log self-test
5. consumer groups
6. reconciliation
7. failure/recovery
8. replay

The GUI `Run everything` provides the interactive equivalent.

## Repository evidence
| Requirement | Repository path |
|---|---|
| Configuration | `session2_event_streaming/config.py` |
| Durable log schema | `session2_event_streaming/setup_streaming.py` |
| Shared routing rule | `session2_event_streaming/routing.py` |
| Session 1 handover verifier | `session2_event_streaming/handover_verify.py` |
| Producer | `session2_event_streaming/produce_events.py` |
| Consumers | `session2_event_streaming/consumers.py` |
| Failure/recovery | `session2_event_streaming/failure_recovery.py` |
| Replay | `session2_event_streaming/replay_suite.py` |
| Reconciliation | `session2_event_streaming/reconcile.py` |
| End-to-end runner | `session2_event_streaming/run_pipeline.py` |
| GUI | `session2_event_streaming/gui.py` |
| Stream projection | `session2_event_streaming/results/stream_session_metrics.csv` |
| Consumer lag | `session2_event_streaming/results/consumer_lag.csv` |
| Reconciliation report | `session2_event_streaming/results/reconciliation_report.json` |
| Enrichment evidence | `session2_event_streaming/results/enrichment_report.json` |
| Handover evidence | `session2_event_streaming/results/handover_verification.json` |
| Architecture diagram | `session2_event_streaming/architecture_diagram.png` |

## Session 3 handoff
Session 3 can consume the retained `retailmetrics_event_log`, the idempotent projection tables, and the Session 2 result artifacts. Candidate services are Session/Traffic Analytics, Order/Conversion Analytics, Product/Revenue Analytics, and Refund Analytics.

## Session 4 constraint
The dataset is historical/simulated rather than a live feed. Session 4 should replay `created_at` as event time for fixed/tumbling/sliding windows and state that limitation explicitly.


## Log-first execution
The Session 2 pipeline now starts with `self_test.py --pre`, matching the documentation/reference order. This pre-produce test only verifies guarantees that are meaningful before events exist. After `produce_events.py --reset`, `self_test.py --post` validates the event-dependent guarantees against the actual retained Toy Store event history. This avoids claiming ordering/replay/durability evidence from an empty log.

## Render Session 2 diagrams

Session 2 includes a Graphviz-based `render_diagrams.py`, adapted from the Session 1 renderer. It produces:

- `docs/event-topic-model-session2.png` — event types, topic, event time and partition key
- `architecture/architecture-session2.png` — Session 2 durable-log / producer / consumer / replay / recovery architecture
- `docs/pipeline-flow-session2.png` — actual Run Everything sequence, including the pre-produce self-test and automatic post-produce guarantees

Run either:

```powershell
python .\session2_event_streaming\render_diagrams.py
```

or double-click `RUN_DIAGRAMS.bat`.

Graphviz must be installed and `dot` must be available on PATH. If it is not, the script still writes the `.dot` source files so the diagrams can be rendered later.
