# RetailMetrics Final Presentation Script

Target duration: approximately 12–15 minutes. Use only the controlled presentation customer and application-created records.

## Before presenting

- Confirm PostgreSQL listens only on `127.0.0.1:5432` and `[::1]:5432`.
- Run `RUN_WEB.bat` and confirm FastAPI and Streamlit health.
- Confirm the approved starting state: customer account `105`, address `35`, and simulated payment method `56`.
- Confirm customer `105` has an empty cart, no orders, and no refund requests. A physical active-cart row is created only when the first item is added; before that, the API correctly presents an empty cart.
- Confirm catalog product IDs `1`, `2`, `3`, and `4` are available and use the neutral image placeholder.
- Confirm the Admin, Operations Staff, and Analyst accounts are active and not temporarily locked.
- Keep the Admin, Operations Staff, Analyst, and Customer credentials private.
- Open Swagger only for the two short refusal/conflict demonstrations.

## 1. Introduction

Introduce RetailMetrics as an e-commerce analytics and operations system built over the Toy Store dataset. Explain that imported history is preserved while controlled application commerce is clearly separated.

## 2. Architecture

Show the architecture: Browser → Streamlit → HTTP → FastAPI → PostgreSQL. State that Streamlit never connects directly to PostgreSQL and authorization is enforced in FastAPI.

## 3. Dataset

Show the six imported entities and canonical counts. Point out that imported records remain protected and analytics use canonical views by default.

## 4. Staff roles

Briefly identify the distinct goals:

- Admin: system management and business oversight.
- Operations Staff: daily order and refund operations.
- Analyst: read-only business intelligence.
- Customer: shopping and personal account/order management.

## 5. Customer portal, CRUD, and storefront

Log in as the presentation customer. Show the four configured products and one product-detail page. Explain that the names come from the canonical product rows, while descriptions and current catalog values are application presentation configuration rather than historical dataset facts. Never show COGS in the Customer Portal.

Show the saved Address and simulated Payment Method. Explain that these retained
resources use update/default actions and deactivation rather than physical
deletion. Add a product to the Cart, view it, change its quantity, and remove it
once. State explicitly that Cart Item removal is the literal Delete example.
Add the product again before continuing.

## 6. Cart and checkout

Add one product to the empty cart. Show quantity and server-held price. Proceed through checkout using the presentation address and the simulated card ending in `0000`. Explicitly state that no real card number, CVV, or payment credentials are collected. Place the order and record its order ID.

Expected state: `Pending` order with a simulated `Paid` payment.

## 7. Operations order processing

Log in as Operations Staff. Show the Operations Dashboard and Orders Needing Action. Open the new order, select **Start Processing**, then **Mark Ready / Shipped**. Point out `row_version` concurrency protection and staff actor attribution. Return to the owning Customer Portal, choose **Mark as Received**, and confirm receipt.

Expected state: order moves `Pending → Processing → Ready / Shipped → Delivered`.

## 8. Refund workflow

Return to the Customer Portal, open the delivered order, and submit a partial refund request with an obvious demonstration reason. Log in as Operations Staff or Admin, open Refund Requests, approve it, then process it.

Expected state: one linked actual refund; request becomes `Processed`; simulated payment becomes `Partially Refunded`; the whole order does not become refunded unless cumulative refunds cover its full value.

## 9. Analyst analytics

Log in as Analyst. Show the imported-scope KPI cards, trends, product performance, traffic sources, devices, Customers, and Reports. State that Analyst customer data is deidentified and that application/combined scopes are separate.

## 10. Unauthorized HTTP request

In Swagger, authenticate as Analyst and attempt an Admin-only mutation such as
`POST /products`. Show HTTP `403 Forbidden`. Explain that hiding a control in
Streamlit is not the security boundary: FastAPI independently refuses the
direct request. Do not create a record.

## 11. Optimistic-concurrency conflict

Use the presentation customer's mutable address or another appropriate
application resource. Read its current `row_version`, update it once, then
submit the old version again. Show HTTP `409 Conflict`. Do not target an imported
row or use generic transaction deletion.

## 12. Sessions 1–3 relationship

Explain:

- Session 1 produced the parallel-compute baseline.
- Session 2 replayed events and reconciled with Session 1.
- Session 3 compared in-process, REST/JSON, and gRPC/protobuf using shared read-only business logic.
- RetailMetricsWeb surfaces stable canonical SQL and vetted result artifacts without importing or executing the analytical session modules.

Open **Project Evidence as Admin**. Emphasize that communication benchmarks are
local observations, not universal protocol claims. Analyst Business Reports do
not expose this technical evidence.

## 13. Conclusion

Summarize protected historical data, server-side RBAC, atomic checkout, explicit order/refund lifecycles, optimistic concurrency, multi-user LAN access, and reconciled analytics.

## Rehearsal reset

Record the exact order ID created during the rehearsal. Stop if the ID is uncertain. First run a dry-run from the application directory:

```powershell
cd RetailMetricsWeb
.\.venv\Scripts\python.exe scripts\reset_presentation_data.py --order-id ORDER_ID
```

Review every listed target. To execute, add `--execute` and type the exact confirmation phrase when prompted. The utility retains catalog configuration, the presentation customer, address, and simulated payment method. It refuses orders that do not belong to `presentation.customer@example.com` or are not customer-origin records.

After reviewing the dry-run, execute the same explicit ID only:

```powershell
.\.venv\Scripts\python.exe scripts\reset_presentation_data.py --order-id ORDER_ID --execute
```

The reset removes dependencies in safe order: converted-cart items/cart, actual refunds, refund requests, payment snapshot, shipping snapshot, order items, then the customer-origin order. It never uses `TRUNCATE`, broad predicates, imported rows, or another customer's records.

After reset, rerun the setup utility only if the retained customer resources or catalog configuration need validation. Confirm the clean starting state again before presenting:

- customer `105` is active and unlocked;
- address `35` and payment method `56` are active defaults;
- the cart is empty;
- order and refund-request counts are zero;
- canonical counts are unchanged.
