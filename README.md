# RetailMetrics — MIT 261 Parallel and Distributed Systems

## Overview

RetailMetrics is a single academic project built around the Toy Store E-Commerce Database. The repository demonstrates the progression from parallel batch analytics, to durable event streaming, to distributed service communication, and finally to a full operational web application backed by PostgreSQL.

**Course:** MIT 261 — Parallel and Distributed Systems

## Repository Map

```text
MIT261-UTTO/
├── README.md
├── PROJECT_CONTEXT.md
├── RetailMetricsGUI/                 # Session 1 Tkinter console
├── RetailMetricsWeb/                 # Streamlit + FastAPI CRUD/RBAC web app
├── session1_parallel_compute/        # Parallel analytics + PostgreSQL migration
├── session2_event_streaming/         # Durable event streaming / replay
└── session3_distributed_services/    # REST, gRPC, local adapter comparison
```

## Dataset

Main historical tables:

| Table | Approx. rows | Purpose |
|---|---:|---|
| `website_sessions` | 472,871 | Sessions, campaigns, source, device |
| `website_pageviews` | 1,188,124 | Pageview events |
| `orders` | 32,313 | Orders |
| `order_items` | 40,025 | Purchased items |
| `order_item_refunds` | 1,731 | Refunds |
| `products` | 4 | Product master |

Historical values used as the analytical baseline include gross revenue of **$1,938,509.75**, gross profit of **$1,216,139.50**, refunds of **$85,338.69**, and net revenue of **$1,853,171.06**.

The original historical dataset is protected so later web-created records do not silently change the evidence produced by Sessions 1–3.

---

# Session 1 — Parallel Compute

Folder:

```text
session1_parallel_compute/
```

Session 1 establishes the analytical baseline. It performs profiling, relational joins, partition-strategy analysis, a sequential reference computation, bounded parallel execution with PySpark, partition-balance analysis, benchmarking, correctness validation, and CSV-to-PostgreSQL migration.

Main partition key:

```text
website_session_id
```

Main output:

```text
session1_parallel_compute/results/session_journey_metrics.parquet
```

Per-session metrics include:

- pageview count;
- session duration;
- conversion flag;
- order revenue;
- gross profit.

The benchmark compares bounded Spark execution with 2, 4, and 8 partitions while verifying identical analytical results.

## Session 1 GUI — RetailMetricsGUI

Folder:

```text
RetailMetricsGUI/
```

This Tkinter desktop GUI is a visual console for Session 1 and its PostgreSQL migration tools.

It supports:

- profiling;
- joining/loading;
- partition strategy;
- sequential baseline;
- parallel compute;
- benchmarking;
- partition analysis;
- CSV → PostgreSQL migration;
- migration verification;
- console output.

Entry point:

```text
RetailMetricsGUI/RUN_GUI.bat
```

---

# Session 2 — Event Streaming & Messaging Backbone

Folder:

```text
session2_event_streaming/
```

Session 2 replays the Session 1 dataset as a durable event stream and reconciles its final projection against the Session 1 batch result.

Event contract:

```text
Topic: commerce.activity.recorded
Schema version: 1
Partitions: 4
Partition key: website_session_id
Routing: website_session_id % 4
Event time: created_at
```

Main event types:

- `pageview.recorded`
- `refund.recorded`

The PostgreSQL-backed durable log demonstrates:

- stable routing;
- per-partition ordering;
- non-destructive reads;
- consumer-group isolation;
- replay;
- rewind;
- offline catch-up;
- at-least-once recovery;
- idempotent sinks.

Important consumer groups include:

- `session-metrics-projector`
- `conversion-audit-writer`
- `refund-monitor`
- replay-based monetization analytics

The implementation is intentionally a **single PostgreSQL durable-log abstraction** and does not claim Kafka-style replication, leader election, or multi-broker fault tolerance.

## Session 2 GUI

Session 2 contains its own interactive GUI in:

```text
session2_event_streaming/gui.py
```

It provides a visual equivalent of the end-to-end streaming pipeline, including production, consumers, replay, failure/recovery, reconciliation, and console output.

---

# Session 3 — Distributed Services

Folder:

```text
session3_distributed_services/
```

Session 3 compares three call paths over one immutable RetailMetrics service core:

1. in-process adapter;
2. REST with JSON;
3. gRPC with Protocol Buffers.

All Session 3 PostgreSQL access is read-only. The session compares:

- payload size;
- latency;
- round trips;
- completion time;
- streaming;
- time to first usable result.

Local endpoints:

```text
REST: 127.0.0.1:8100
gRPC: 127.0.0.1:50051
```

## Session 3 GUI

The Session 3 Tkinter GUI contains eight tabs:

1. Pipeline
2. Contract
3. Payload Size
4. Latency
5. Round Trips & Streaming
6. Adapter Swap
7. Reconciliation
8. Console

Entry point:

```text
session3_distributed_services/RUN_GUI.bat
```

Benchmark values remain **Not run** until a real experiment is executed.

---

# PostgreSQL Database

Database:

```text
retailmetrics
```

PostgreSQL should remain bound to localhost. Do not expose port `5432` to the LAN or public internet.

## Historical dataset tables

```text
website_sessions
website_pageviews
products
orders
order_items
order_item_refunds
```

## Session 2 infrastructure

Important support tables include:

```text
retailmetrics_event_log
retailmetrics_consumer_offsets
retailmetrics_consumer_partition_offsets
retailmetrics_conversion_audit
retailmetrics_failure_audit
retailmetrics_refund_projection
retailmetrics_session_projection
retailmetrics_stream_runs
```

## RetailMetricsWeb migrations

The web application extends the database through:

```text
001_add_app_users_and_crud_metadata.sql
002_customer_portal_and_order_workflow.sql
003_notification_outbox.sql
004_order_delivery_confirmation.sql
005_audit_trail.sql
```

These migrations add staff identity/RBAC metadata, the customer portal and commerce workflow, notification outbox support, customer-confirmed delivery, and audit logging.

Important application entities include:

```text
app_users
customer_accounts
customer_profiles
customer_addresses
payment_methods
product_catalog_details
shopping_carts
cart_items
order_shipping_addresses
order_payments
refund_requests
notification_outbox
audit_logs
```

Where applicable, `record_origin` separates `imported`, `staff`, and `customer` business context. Canonical historical views protect the original dataset boundary used by Sessions 1–3.

---

# RetailMetrics Web Application

Folder:

```text
RetailMetricsWeb/
```

Architecture:

```text
Browser
  ↓
Streamlit Frontend
  ↓ HTTP
FastAPI Backend
  ↓
Service / Repository Layer
  ↓
PostgreSQL
```

**Streamlit never connects directly to PostgreSQL.** FastAPI remains authoritative for authentication, ownership, RBAC, validation, and optimistic concurrency.

## Security

The web application uses:

- Argon2id password hashing;
- JWT authentication;
- server-side RBAC;
- temporary login lockout;
- email-link password reset and authenticated password change;
- token-version invalidation;
- `row_version` optimistic concurrency.

Password recovery has two separate screens. The request screen accepts an
email address and sends a branded, time-limited **Reset password** link. That
link opens the dedicated reset page; customers and staff do not copy or enter a
reset code in the UI.

## Identity domains

Staff users are stored in:

```text
app_users
```

Staff roles:

- Admin
- Operations Staff
- Analyst

Customers are separate and use:

```text
customer_accounts
customer_profiles
```

A customer is not an `app_users` role, and the historical dataset `user_id` is not an application login identity.

---

# Staff Operational Portal

The staff experience is an operational, data-dense system with a desktop sidebar.

## Admin

Typical pages:

- Dashboard
- User Management
- Customer Accounts
- Customers
- Products
- Storefront Catalog
- Orders
- Refund Requests
- Audit Trail
- Notification Test
- Website Traffic
- Analytics Dashboard
- Business Reports
- My Account

## Operations Staff

Typical pages:

- Dashboard
- Customers
- Orders
- Refund Requests
- Products / Catalog as read-only reference
- My Account

## Analyst

Read-only pages focus on:

- Analytics Dashboard
- Customers with deidentified analytical projections
- Products
- Orders
- Refund Requests and refund records (read-only)
- Website Traffic
- Business Reports
- My Account

RBAC is enforced by FastAPI rather than only by hidden UI controls.

---

# Customer E-Commerce Portal

The public storefront is the application's first screen. Visitors can search
the catalog, view the four illustrated toy products, read store benefits and
shopper reviews, and build a temporary shopping bag without signing in. Login
or account creation is requested when a visitor chooses checkout, while the
**Sign in** action remains available for customers who want to open their
account and explore the authenticated portal.

After customer login, guest bag items are copied into the customer's persistent
cart. The customer portal uses a separate customer-facing shell and does not
reuse the staff dashboard layout.

Intended customer navigation:

```text
RetailMetrics | Shop | Cart | My Orders | Account
```

Customer pages include:

- Public storefront and guest bag
- Unified staff/customer sign-in
- Customer registration
- Forgot Password request
- Dedicated Reset Password page opened from email
- Shop / Home
- Product Details
- Cart
- Checkout
- My Orders
- Order Details
- Refund Request
- My Account
- Profile
- Addresses
- Payment Methods
- Security

The storefront displays only products that have customer-facing catalog
configuration and are available. Known catalog products use bundled WebP toy
artwork from `RetailMetricsWeb/frontend/assets/products/`; unknown products
retain a safe visual fallback.

## Cart CRUD

Cart Items provide the clearest literal CRUD example:

```text
Create  → Add item
Read    → View cart
Update  → Change quantity
Delete  → Remove item
```

## Checkout

Checkout atomically creates the order, order items, shipping snapshot, simulated payment snapshot, and converted cart state after server-side revalidation.

## Order lifecycle

```text
Pending
→ Processing
→ Ready / Shipped
→ Delivered
```

Other terminal states include:

```text
Cancelled
Refunded
```

The owning customer confirms eligible delivery.

---

# Refund Workflow

Customers submit eligible Refund Requests.

Admin or Operations Staff can:

- approve;
- reject;
- process.

Processing an approved request creates the linked Actual Refund. Transaction records are retained for audit integrity rather than exposed as unrestricted CRUD.

The staff **Refund Requests** page is the single refund workspace. Its action
queue appears first and lists every pending or approved request from oldest to
newest. Completed request history and the complete refund-record table are
grouped at the bottom inside the collapsed **All refund history and records**
section. Analysts see the same evidence without mutation controls.

The **Orders** page follows the same pattern: every pending or processing order
appears in an oldest-first queue at the top, with the first unprocessed order
selected by default. Customer order history and imported order records remain
available at the bottom inside the collapsed **All order records** section.

The **Customers** page presents registered customers first. Earlier imported
customer activity is part of the same page and is available in a collapsed
section rather than being presented as a separate customer system.

---

# Notifications

RetailMetrics uses an outbox-based notification workflow.

Current local channel design:

```text
Email → Gmail SMTP
SMS   → Android SMS Gateway
```

Supported customer events include order and refund lifecycle updates.

Philippine mobile numbers are normalized to:

```text
+639XXXXXXXXX
```

Notification provider failures must not roll back a successfully committed business transaction.

Never commit or display SMTP, SMS gateway, database, or JWT secrets.

---

# Audit Trail

The Admin-only Audit Trail records supported authentication, view, and mutation events.

The normal UI provides read/inspect behavior only. Audit descriptions must never include passwords, reset codes, payment credentials, API keys, or notification secrets.

---

# GUI / UI Inventory

| Interface | Technology | Main purpose |
|---|---|---|
| `RetailMetricsGUI` | Tkinter | Session 1 analytics and CSV/PostgreSQL migration |
| Session 2 GUI | Tkinter | Event streaming, replay, recovery, reconciliation |
| Session 3 GUI | Tkinter | REST/gRPC/local benchmark experiments |
| Staff Portal | Streamlit | Admin, Operations, Analyst operational system |
| Customer Portal | Streamlit | Customer-facing e-commerce experience |
| FastAPI `/docs` | OpenAPI/Swagger | Local API inspection |

---

# UI Design Source of Truth

Before changing the web frontend, read:

```text
RetailMetricsWeb/AGENTS.md
RetailMetricsWeb/docs/UI_DESIGN_SYSTEM.md
```

Core rule:

```text
Staff UI    = operational, data-dense, sidebar-based
Customer UI = e-commerce, product-focused, top-navigation-based
```

---

# Running the Web Application

```powershell
cd RetailMetricsWeb
.\.venv\Scripts\Activate.ps1
.\RUN_WEB.bat
```

Open:

```text
http://localhost:8501
```

FastAPI docs:

```text
http://127.0.0.1:8000/docs
```

For LAN testing, use the host machine's private IPv4 address as documented in `RetailMetricsWeb/README.md`. PostgreSQL itself should remain localhost-only.

---

# Running the Desktop GUIs

Session 1:

```powershell
cd RetailMetricsGUI
.\RUN_GUI.bat
```

Session 2:

```powershell
cd session2_event_streaming
python run_pipeline.py
```

Use the Session 2 GUI when an interactive demonstration is preferred.

Session 3:

```powershell
cd session3_distributed_services
RUN_TESTS.bat
RUN_PIPELINE.bat
RUN_GUI.bat
```

---

# Development and Redesign Rules

When using Cursor, Codex, or another coding assistant:

1. inspect the real repository before modifying files;
2. read `RetailMetricsWeb/AGENTS.md`;
3. read `RetailMetricsWeb/docs/UI_DESIGN_SYSTEM.md`;
4. preserve FastAPI contracts and server-side authorization;
5. do not change Session 1–3 evidence while redesigning the web UI;
6. do not modify `.env`;
7. never expose secrets;
8. run focused tests after each major change;
9. run the complete applicable frontend/unit suite before finishing;
10. manually inspect the rendered UI at desktop, tablet, and mobile sizes;
11. test desktop → mobile → desktop resizing;
12. add regression tests for runtime bugs found during redesign.

Automated tests prove functional behavior; they do not replace visual QA.

---

# Current Frontend Experience

The intended web architecture is:

```text
STAFF
Operational
Data-dense
Sidebar navigation

CUSTOMER
E-commerce
Product-focused
Top navigation
```

The current Streamlit experience includes:

- a responsive public landing page with storefront navigation, product search,
  guest bag, benefits, reviews, and a checkout sign-in boundary;
- generated local artwork for all four original toy products;
- a unified sign-in screen for staff usernames and customer email addresses;
- a two-column Create Account form with clearly outlined fields and native
  password visibility controls;
- an email-first Forgot Password screen and a separate tokenized Reset Password
  page;
- customer desktop and mobile navigation for Shop, Cart, My Orders, and Account;
- role-specific staff workspaces with operational queues before historical
  tables;
- consolidated Orders, Refund Requests, and Customers pages with large record
  tables collapsed until requested.

The shared visual system is defined in
`RetailMetricsWeb/frontend/assets/retailmetrics.css`. Any coding assistant
should still verify the rendered application at desktop and narrow widths after
changing Streamlit markup or styles.

---

# Academic Purpose

RetailMetrics is an academic project for **MIT 261 – Parallel and Distributed Systems**.

It demonstrates a continuous progression:

```text
parallel computation
→ durable event streaming
→ distributed services
→ operational web application
```

AI coding tools may be used for implementation assistance, debugging, documentation, and design iteration. Final execution, validation, interpretation, and submission remain the responsibility of the student.
