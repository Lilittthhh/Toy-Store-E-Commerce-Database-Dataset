# PROJECT CONTEXT — RetailMetrics / MIT 261
**Canonical Project Context — use whether continuing on this account or transferring**
**Last updated:** 2026-09-13

## 1. Purpose
This file is a handoff context for continuing the RetailMetrics project on another ChatGPT/Codex account without losing the current project state.

Project title:
**RetailMetrics: An E-Commerce Analytics System for Sales, Website Performance, and Revenue Intelligence**

Course:
**MIT 261 — Parallel and Distributed Systems**

Dataset:
**Toy Store E-Commerce Database** from Kaggle.

Primary repository/workspace:
`C:\Users\ureha\OneDrive\Desktop\MIT\MIT261-UTTO`

---

## 2. Important Working Style / Safety Rules
- Read this file before proposing changes.
- Do not redesign working components without a concrete reason.
- Preserve Sessions 1–3 and the completed CRUD/RBAC application.
- Prefer incremental changes.
- Do not invent dataset fields, counts, benchmark numbers, or professor requirements.
- Never expose PostgreSQL credentials, JWT secrets, or passwords.
- Never commit `.env`.
- PostgreSQL must stay localhost-only.
- Do not force-push.
- Before Git work, always inspect:
  - `git status`
  - `git branch`
  - `git remote -v`
- Do not use `git add .` while the repository still contains unrelated Session 1/2 changes.
- Do not modify imported/canonical business rows through the CRUD web application.
- New session work should be isolated first, then integrated only after it is verified.

---

# 3. Repository Structure

```text
MIT261-UTTO/
├── RetailMetricsGUI/
├── RetailMetricsWeb/
├── session1_parallel_compute/
├── session2_event_streaming/
├── session3_distributed_services/
├── .gitignore
├── PROJECT_CONTEXT.md
└── README.md
```

Session 4 has NOT been posted by the professor yet. Do not invent Session 4 requirements.

---

# 4. Dataset

Original Toy Store E-Commerce tables and baseline row counts:

| Table | Rows |
|---|---:|
| website_sessions | 472,871 |
| website_pageviews | 1,188,124 |
| products | 4 |
| orders | 32,313 |
| order_items | 40,025 |
| order_item_refunds | 1,731 |

Relationships:
- WebsiteSession → WebsitePageviews
- WebsiteSession → Orders
- Product → Orders
- Product → OrderItems
- Order → OrderItems
- Order → Refunds
- OrderItem → Refunds

Verified RetailMetrics values:
- Gross revenue: **$1,938,509.75**
- Gross profit: **$1,216,139.50**
- Refunds: **$85,338.69**
- Net revenue: **$1,853,171.06**
- COGS: **$722,370.25**
- Sessions: **472,871**
- Purchase conversions/orders: **32,313**
- Conversion rate: **6.83%**

Traffic sources include:
- gsearch
- bsearch
- socialbook
- NULL/unattributed

Do not invent unsupported traffic categories.

---

# 5. PostgreSQL

Database:
`retailmetrics`

Typical local config:
- host: localhost
- port: 5432
- user: postgres

Security status:
- PostgreSQL was changed from `listen_addresses='*'` to:
  `listen_addresses='localhost'`
- PostgreSQL service was restarted successfully.
- Verified with:
  `SHOW listen_addresses;`
  result: `localhost`
- Verified with:
  `netstat -ano | findstr :5432`
- Listening only on:
  - `127.0.0.1:5432`
  - `[::1]:5432`
- No `0.0.0.0:5432`.

Do not reopen PostgreSQL to LAN.

---

# 6. Session 1 — Parallel Compute

Folder:
`session1_parallel_compute/`

Main analytics still uses original CSV inputs.

Important result:
`session1_parallel_compute/results/session_journey_metrics.parquet`

Verified output:
- 472,871 session groups
- revenue $1,938,509.75
- gross profit $1,216,139.50

Authoritative PostgreSQL migration folder:
`session1_parallel_compute/postgresql_migration/`

Do not treat malformed/old root migration copies as authoritative.

---

# 7. Session 2 — Event Streaming

Folder:
`session2_event_streaming/`

Session 2 baseline:
- events: 1,189,855
- partitions: 4
- reconciliation: PASS

Support tables:
- retailmetrics_event_log
- retailmetrics_consumer_offsets
- retailmetrics_consumer_partition_offsets
- retailmetrics_conversion_audit
- retailmetrics_failure_audit
- retailmetrics_refund_projection
- retailmetrics_session_projection
- retailmetrics_stream_runs

These are Session 2 infrastructure tables, not CRUD/RBAC user tables.

Important Session 2 result artifacts:
- `results/stream_session_metrics.csv`
- `results/reconciliation_report.json`
- `results/consumer_summary.json`

Session 2 producer/reconciliation uses canonical views for mutable entities so application-created CRUD rows do not corrupt baseline evidence.

---

# 8. CRUD/RBAC Web Application

Folder:
`RetailMetricsWeb/`

Architecture:
**Browser → Streamlit → HTTP → FastAPI → PostgreSQL**

Frontend:
- Streamlit

Backend:
- FastAPI

Database:
- PostgreSQL

Security:
- Argon2id password hashing
- JWT authentication
- server-side RBAC
- temporary login lockout
- password change
- password reset
- token invalidation through `token_version`

Roles and identity boundaries:
1. Admin
2. Operations Staff
3. Analyst
4. Customer (separate `customer_accounts` authentication domain)

Dataset `user_id` is a shopper ID and is NOT an application login user.

## RBAC

Admin:
- manages staff users and customer account access
- manages application-created Products and Storefront Catalog configuration
- oversees validated customer Order and Refund Request workflows
- reads business analytics and Admin-only Project Evidence
- has no normal generic Create/Update/Delete UI for Orders, Order Items, or
  Actual Refunds

Operations Staff:
- reads operationally necessary customer information
- processes Customer Orders through validated lifecycle transitions
- approves, rejects, and processes Refund Requests
- reads Actual Refund outcomes
- uses Products and Storefront Catalog as read-only reference
- cannot manage staff users or manually create Orders, Order Items, or Refunds

Analyst:
- deidentified, read-only business intelligence and reporting
- no mutation, operational workflow, account-management, or Project Evidence UI

Customer:
- manages own profile, addresses, simulated Payment Methods, and Cart
- creates Orders only through atomic Checkout and reads only own Orders
- may cancel an eligible pending Order and submit eligible Refund Requests
- cannot access staff workspaces or another customer's resources

Website Sessions and Website Pageviews are read-only for every role.

RBAC is enforced by FastAPI, not just the UI.

---

# 9. CRUD/Customer Portal Database Migrations

Migration 001:
`RetailMetricsWeb/db/migrations/001_add_app_users_and_crud_metadata.sql`

Added:
- `public.app_users`
- creator metadata and `row_version` to:
  - products
  - orders
  - order_items
  - order_item_refunds
- nullable `created_by_app_user_id` FK → `app_users`
- shared sequence:
  `public.retailmetrics_app_entity_id_seq`
- unique index:
  `uq_orders_website_session_id`
- canonical read-only views:
  - canonical_products
  - canonical_orders
  - canonical_order_items
  - canonical_order_item_refunds

Origin rule:
- historical/canonical rows: `record_origin='imported'`
- application business context: `record_origin='staff'` or
  `record_origin='customer'`
- `created_by_app_user_id` is separate actor attribution and does not define the
  business source/context

Do NOT infer record origin from ID ranges.

Migration 002:
`RetailMetricsWeb/db/migrations/002_customer_portal_and_order_workflow.sql`

Migration 002 additively provides the separate customer identity/profile,
address, simulated Payment Method, storefront catalog, Cart, immutable checkout
snapshot, payment, and Refund Request structures. It extends the four business
tables with precise `record_origin` and customer-workflow metadata without
copying or rewriting the six historical dataset tables. No Migration 003 was
required for the completed refund workflow.

Migration 001 and its post-migration verification completed successfully.
Migration 002 is deployed; its latest cumulative verifier reports every
schema, relationship, origin, canonical-boundary, and Session 2 database
fingerprint check passing. The separately reported Session 1/2 evidence-file
hash mismatch is a known working-tree artifact mismatch, not a schema/data
failure introduced by Migration 002 or the web application.

Canonical counts remained:
- products: 4
- orders: 32,313
- order_items: 40,025
- refunds: 1,731

---

# 10. CRUD/RBAC Functional Verification

Verified manually and/or through tests:

- Customer Cart Item literal CRUD works: Add, View, Change Quantity, Remove
- Customer Address and simulated Payment Method create/read/update/deactivate
  workflows work
- Admin staff-account and application-created Product management works
- Customer Checkout creates Orders and Order Items atomically
- Admin/Operations Order and Refund Request lifecycle workflows work
- Analyst is read-only
- direct unauthorized HTTP mutation → **403 Forbidden**
- stale optimistic-concurrency mutation → **409 Conflict**
- error example:
  `Stale row_version: expected 6, current value is 7.`
- imported rows cannot be updated/deleted
- permitted application master/profile resources can be updated or deactivated
- dependent-record deletion is protected
- duplicate order for same Website Session → 409
- refund validations work
- account lockout works
- admin unlock works
- password change works
- forgot/reset password works
- role/status changes invalidate existing tokens
- logout/password reset increments token version
- F5 session persistence works
- Refresh Data works
- multi-device LAN access was manually verified
- frontend uses HTTP only and does not connect directly to PostgreSQL

A clean literal CRUD lifecycle is demonstrated on Customer Cart Items:
Add → View → Change Quantity → Remove. Retained resources such as users,
addresses, and simulated Payment Methods use deactivation. Financial Orders,
Order Items, and Actual Refunds are retained lifecycle/audit records rather than
generic deletion targets.

After cleanup the database returned to canonical baseline counts:
- Refunds: 1,731
- Order Items: 40,025
- Orders: 32,313
- Products: 4

---

# 11. CRUD Web UI

The Streamlit frontend has been presentation-polished.

Final role-specific pages:
- Customer: Home/Shop, Product Details, Cart, Checkout, My Orders, Order Details,
  My Account/Profile, Addresses, simulated Payment Methods, Security, Logout
- Operations Staff: Dashboard, Customers, Orders, Refund Requests, Refunds,
  Products, Storefront Catalog, My Account, Logout
- Admin: Dashboard, User Management, Customer Accounts, Customers, Products,
  Storefront Catalog, Orders, Refund Requests, Refunds, Website Traffic,
  Analytics Dashboard, Business Reports, Project Evidence, My Account, Logout
- Analyst: Analytics Dashboard, Customers, Products, Orders, Refunds, Website
  Traffic, Business Reports, My Account, Logout

Visual improvements include:
- RetailMetrics branding
- dark/sidebar treatment
- consistent professional palette
- clearer tables/forms
- source badges:
  - Historical data
  - Application-created
  - Customer-created only where legitimate
- compact, responsibility-appropriate controls
- consistent Refresh Data
- improved dashboard cards/charts
- role-aware controls
- no internal Streamlit page/module names

Latest complete verified suite after the final cross-role alignment pass:
**236 passed** (208 unit/frontend and 28 PostgreSQL integration tests).
The focused frontend/navigation subset also passes **69 tests**, and static
Python compilation passes.

A separate audit concluded the application was functionally complete.

---

# 12. CRUD Documentation

Completed artifacts under `RetailMetricsWeb/docs/` include:
- `ERD_SPEC.md`
- `CRUD_ROLE_MATRIX.md`
- `DATASET_JUSTIFICATION.md`
- `CONCURRENCY_REFLECTION.md`
- `DEMONSTRATION_SCRIPT.md`
- `SUBMISSION_EVIDENCE_GUIDE.md`
- `erd/retailmetrics_erd.dot`
- `erd/ERD_FINAL.svg`
- `erd/ERD_FINAL.png`

ERD correction:
WebsiteSession → Order multiplicity is:
**1 → 0..1**
because of `uq_orders_website_session_id`.

User self-service email editing is NOT implemented and should not be claimed.

A Word CRUD scenarios document was also created based on the professor's reference format:
`RetailMetrics_CRUD_Scenarios.docx`

---

# 13. LAN / Presentation Networking

Previously verified local Wi-Fi IPv4:
`192.168.254.103`

Past URLs:
- Streamlit: `http://192.168.254.103:8501`
- Swagger: `http://192.168.254.103:8000/docs`

This IP is NOT permanent and changes with networks.

The user plans to defer Windows Firewall configuration until all sessions are integrated.

For presentation:
- likely use a trusted network or phone hotspot
- laptop and demo device must be on the same LAN
- firewall may later allow Private-profile TCP 8000 and 8501 only
- never expose 5432

Internet/mobile data is not required for local LAN communication itself.

---

# 14. Session 3 — High-Performance Inter-Service Communication

Folder:
`session3_distributed_services/`

Professor material:
**Session 3 — the gRPC-family concept**

Concepts:
- REST/JSON vs gRPC/protobuf
- typed `.proto` contracts
- binary serialization
- adapter pattern
- payload-size comparison
- latency comparison
- batching/round trips
- server streaming
- deadline behavior
- reconciliation
- when gRPC is appropriate vs inappropriate

Professor's CMA/payment examples were treated only as conceptual/layout references. RetailMetrics uses Toy Store entities and analytics.

## Session 3 Environment
Dedicated Python:
**3.11.9**

Dedicated venv:
`session3_distributed_services/.venv`

Dependencies include:
- FastAPI 0.141.1
- grpcio 1.83.1
- grpcio-tools 1.83.1
- protobuf 7.36.1
- httpx 0.28.1
- psycopg2-binary 2.9.12
- pandas 3.0.5
- pyarrow 25.0.1
- python-dotenv 1.2.3
- pytest 9.1.1
- uvicorn 0.52.4

`pip check`: PASS

## Architecture

```text
RetailMetrics Session 3 GUI
         |
 Experiment Coordinator
   /       |        \
in-process REST     gRPC
   \       |        /
 Shared RetailMetricsServiceCore
         |
 Read-only canonical repository
         |
 PostgreSQL localhost only
```

REST:
`127.0.0.1:8100`

gRPC:
`127.0.0.1:50051`

Both use the same immutable/shared service logic.

Database reads are read-only and use canonical data.

---

# 15. Session 3 Protobuf Contract

Contract:
`retailmetrics_s3/proto/retailmetrics.proto`

Generated modules:
- retailmetrics_pb2.py
- retailmetrics_pb2.pyi
- retailmetrics_pb2_grpc.py

Contract contains:
- **29 messages**
- **5 services**
- **16 RPC methods**

Services:

## CatalogService
- GetProduct
- ListProducts

## OrderDataService
- GetOrder
- ListOrders
- BatchGetOrders
- GetOrderItem
- ListOrderItems
- GetRefund
- ListRefunds

## JourneyService
- GetSession
- BatchGetSessions

## AnalyticsService
- GetSalesSummary
- GetSessionMetrics
- StreamSessionMetrics
- GetProductPerformance

## DiagnosticsService
- DelaySummary

At least one server-streaming RPC is implemented:
`StreamSessionMetrics`

Money is converted using exact Decimal-based conversion to integer cents.

---

# 16. Session 3 GUI

Separate Tkinter GUI:
**RetailMetrics — Session 3 Inter-Service Communication**

Eight tabs:
1. Pipeline
2. Contract
3. Payload size
4. Latency
5. Round trips & streaming
6. Adapter swap
7. Reconciliation
8. Console

The professor's screenshots were used only for structural inspiration.

The GUI does NOT use CMA/payment-specific content.

Additional presentation improvements:
- Reconciliation includes:
  **Session 3 Product Performance**
  with note that it is Session 3-only and not compared with Sessions 1/2.
- Adapter Swap includes summary cards for:
  - results identical
  - response bytes saved
  - caller-site changes
  - deadline result

GUI launch:
```powershell
cd C:\Users\ureha\OneDrive\Desktop\MIT\MIT261-UTTO\session3_distributed_services
.\RUN_GUI.bat
```

Manual venv activation is not required when the batch launcher directly uses the Session 3 venv.

Session 3 requires its own `.env` with local PostgreSQL credentials.
Never commit or share the real `.env`.

---

# 17. Session 3 Verified Benchmarks

These are LOCAL, machine/run-specific observations. Do not present them as universal protocol claims.

## Payload serialization
Measured JSON vs protobuf payloads:

- Product: 92 B JSON / 34 B protobuf / 63.0% reduction
- Order: 167 B / 24 B / 85.6%
- OrderItem: 140 B / 22 B / 84.3%
- Refund: 111 B / 17 B / 84.7%
- WebsiteSession: 230 B / 74 B / 67.8%
- SessionMetric: 139 B / 4 B / 97.1%
- SalesSummary: 186 B / 36 B / 80.6%
- ProductPerformance: 191 B / 54 B / 71.7%

Best measured reduction:
**97.1%**

## Unary latency
One verified pipeline run:
- in-process median: 0.0007 ms
- REST/JSON median: 1.9845 ms
- gRPC/protobuf median: 0.6030 ms

A later GUI run recorded roughly:
- REST ~1.53 ms
- gRPC ~0.52 ms

Do not force one exact latency value if presenting a rerun. Show the current measured run.

## Batch vs individual requests
Verified run:
- REST batch: 5.2739 ms
- REST 50 individual: 92.9746 ms
- ratio: 17.63×
- trips saved: 49

- gRPC batch: 1.6788 ms
- gRPC 50 individual: 34.4894 ms
- ratio: 20.54×
- trips saved: 49

Later GUI observations reported approximately:
- REST ~26.37×
- gRPC ~24.16×

Again, these vary per run.

## Streaming
5,000 session metric records:
- unary total: 190.9072 ms
- streaming total: 761.0795 ms
- first streamed result: 4.6817 ms
- first usable streamed result arrived ~40.78× earlier than unary completion

Important interpretation:
Streaming was NOT faster in total completion time in this run.
Its demonstrated benefit was much earlier time-to-first-usable-result.

A later GUI run showed first streamed message around 4.29 ms.

## Adapter swap
- REST and gRPC normalized results: identical
- caller sites changed: zero
- REST median: 4.3393 ms/call
- gRPC median: 1.2537 ms/call
- REST response: 985 bytes/call
- protobuf response: 248 bytes/call

## Deadline
- requested delay: 250 ms
- 50 ms deadline: `DEADLINE_EXCEEDED`
- 2000 ms deadline: `SUCCESS`

---

# 18. Session 3 Reconciliation

Overall:
**PASS**

Compared with Sessions 1 and 2 across:
**472,871 sessions**

Verified:
- Session IDs: exact equality
- Pageview differences: 0
- Conversion differences: 0
- Maximum duration difference: 0
- Revenue difference: 0 cents
- Gross-profit difference: 0 cents

Session 2 refund reconciliation:
- Session 3 refunds: 1,731
- Session 2 refunds: 1,731
- total refunded difference: 0 cents

Product-performance ranking is a Session 3-only output and must not be falsely presented as a cross-session comparison.

---

# 19. Session 3 Safety / Tests

Final Session 3 full suite:
**15 passed**

Dedicated GUI smoke:
**1 passed**

Static compilation:
**PASS**

Database counts remained unchanged:
- website_sessions: 472,871
- website_pageviews: 1,188,124
- canonical products: 4
- canonical orders: 32,313
- canonical order items: 40,025
- canonical refunds: 1,731
- app_users: 3

Session 2 support-table counts also remained unchanged.

Safeguards:
- read-only PostgreSQL transactions
- REPEATABLE READ
- SQL mutation guard
- canonical views
- rollback on close
- before/after database fingerprint
- Session 1/2 evidence-file hashes remained unchanged

Generated Session 3 evidence:
`session3_distributed_services/results/`

---

# 20. Session 3 Status

**SESSION 3 IS COMPLETE AND VERIFIED.**

Do not re-architect or redo it without a specific requirement from the professor.

No remaining Session 3 implementation work is known to be incomplete.

---

# 21. Git Situation

Important: repository cleanup has NOT been finalized.

Previously reported:
- `RetailMetricsWeb/` contained many untracked files.
- Session 1 had numerous pre-existing modified/deleted/generated files.
- Session 2 had some pre-existing modifications/deletions.

Do not bulk-stage.

Correct Toy Store repository used for Session 2 resubmission:
`https://github.com/Lilittthhh/Toy-Store-E-Commerce-Database-Dataset`

Session 2 submitted commit:
`b5cfc59c3c54398da094002ab79d6360ea4ea5e4`

This may not be current HEAD.

Before any final commit:
```powershell
git status --short
git branch
git remote -v
git log --oneline -5
```

Keep excluded:
- `.env`
- `.venv/`
- `__pycache__/`
- `*.pyc`
- `.pytest_cache/`
- credentials/secrets
- temporary benchmark/cache files unless intentionally required as evidence

ERD PNG/SVG are intentional submission artifacts.

---

# 22. Professor Reference Materials

CRUD reference:
**Scenarios for CRUD Operations**
- professor uses a CMA example only
- RetailMetrics must adapt scenarios to its own entities
- professor emphasizes a complete end-to-end CRUD lifecycle

Session 3 reference:
**Session 3 of 6 — High-Performance Inter-Service Communication**
- REST/JSON vs gRPC
- typed `.proto`
- adapter seam
- serialized payload comparison
- streaming
- when gRPC is the wrong choice for browsers/human-readable debugging

The professor's screenshots are visual/layout references, NOT values/content to copy.

---

# 23. Current Immediate State

Completed:
- Session 1
- Session 2
- CRUD/RBAC web application
- CRUD documentation and ERD
- Customer authentication, profiles, addresses, simulated Payment Methods,
  storefront, Cart, atomic Checkout, Order lifecycle, and Refund Request workflow
- Final role-specific Customer, Operations Staff, Admin, and Analyst interfaces
- Phase 9 presentation catalog/customer setup with the live checkout/refund
  workflow intentionally left available for demonstration
- Final professor-facing CRUD/RBAC alignment: Customer Cart Items demonstrate
  literal Create/Read/Update/Delete; retained identities and financial records
  use deactivation or validated lifecycle transitions
- PostgreSQL localhost binding
- Session 3 implementation
- Session 3 GUI
- Session 3 pipeline/reconciliation/tests
- Session 3 project-context update
- Session 3 visual follow-up: Product Performance section in Reconciliation and summary cards in Adapter Swap
- Full Session 3 suite still passes: 15 passed
- Dedicated GUI smoke test still passes: 1 passed
- Static compilation still passes
- RetailMetricsWeb final suite passes: 208 unit/frontend and 28 PostgreSQL
  integration tests
- Migration 002 schema/data/canonical checks pass; the known Session 1/2
  evidence-file hash mismatch remains disclosed separately

Deferred:
- Windows Firewall configuration for 8000/8501
- final Git staging/commit cleanup
- final all-session integration
- presentation-day networking setup
- Session 4 design/implementation

Reason Session 4 is not started:
**Professor has not posted Session 4 materials yet.**

Do not guess Session 4.

---

# 24. What to Do Next

When continuing on another ChatGPT/Codex account:

1. Give that assistant this file first.
2. Tell it to read `PROJECT_CONTEXT.md` before any work.
3. Do not start Session 4 until professor materials are provided.
4. When Session 4 arrives:
   - review professor PDF/screenshots/links first
   - extract exact requirements
   - design only
   - review plan
   - implement in an isolated Session 4 folder
   - verify
   - then integrate
5. Keep CRUD and Sessions 1–3 stable.
6. Postpone firewall/network finalization until all sessions are integrated.
7. Do Git cleanup only after reviewing the dirty worktree carefully.

---

# 25. Suggested First Message on the New Account

Paste this with the project context file:

> I am continuing an existing MIT 261 Parallel and Distributed Systems project called RetailMetrics. Read the attached `PROJECT_CONTEXT.md` completely before proposing or changing anything. Sessions 1–3 and the CRUD/RBAC web application are already implemented and verified. Preserve all working behavior. Session 4 has not been posted by my professor yet, so do not invent its requirements. I will send the professor's next materials before we continue. When I provide new materials, base the next design on those materials and the existing RetailMetrics architecture.

---

# 26. Final Preservation Rule

The project is currently in a strong verified state.

**Do not change working code just to make it different.**

For each future session:
**Professor materials → requirement review → design → approval → isolated implementation → tests/reconciliation → integration → documentation → final presentation.**

---

# 27. Current Handoff Note

This file is not only for account transfer. It is the current project context backup and may be used on the same account as well.

If the local repository's `PROJECT_CONTEXT.md` is older than this file, replace or merge it with this version before future Codex work.

As of 2026-09-13:
- Session 4 has still not been posted by the professor.
- Do not invent Session 4 requirements.
- The user has not yet transferred to another ChatGPT account.
- Continue using this file as the canonical project handoff/context until a newer version is created.
