# Submission Evidence Guide

Capture evidence from a controlled demonstration; do not alter imported rows or
include credentials, raw access tokens, password hashes, reset-token hashes, or
the local `.env` file in screenshots.

## Recommended screenshots

1. **Architecture and access** — Streamlit open in a browser, plus the FastAPI
   `/docs` or `/health` page showing the separate HTTP service.
2. **Authentication** — registration, login, My Account/password change, the
   generic password-recovery response, temporary lockout, and Admin unlock.
3. **Role navigation** — one screenshot each for Admin, Operations Staff, and
   Analyst, showing the appropriate navigation and controls.
4. **Literal CRUD** — show a Customer adding, viewing, changing the quantity of,
   and removing a Cart Item. Capture the **Remove** action as the literal Delete
   operation. Also show Address or simulated Payment Method deactivation as a
   safe delete-equivalent for retained customer data.
5. **Source boundary** — a table containing both `Historical data` and
   `Application-created` labels, followed by the refusal to mutate an imported
   record.
6. **Unauthorized HTTP request** — an Analyst-authenticated mutation in FastAPI
   Swagger returning HTTP 403. Mask the bearer token before capture.
7. **Concurrency** — two-device or two-browser evidence showing a stale
   `row_version` request returning HTTP 409 and the refreshed current record.
8. **Transaction integrity** — Customer checkout creates the Order and Order
   Items atomically; Operations uses lifecycle actions; processing an approved
   Refund Request creates one linked Actual Refund. Explain why these retained
   transactions are cancelled/processed rather than generically deleted.
9. **Read-only entities** — unified Website Traffic with Sessions and Pageviews
   tabs, displayed without Create, Update, or Delete controls.
10. **LAN operation** — the same application reached from a second device using
    `http://HOST_IP:8501`; avoid showing unrelated network details.

## Sample-data evidence by table

Include a small, readable sample rather than a full export:

| Table | Suggested evidence |
|---|---|
| `app_users` | Admin User Management view with username, role, status, and lock state only |
| `website_sessions` | Read-only page with several rows and useful filters |
| `website_pageviews` | Read-only page with several rows and session relationship visible |
| `products` | Protected imported products and their separate storefront configuration |
| `orders` | Customer checkout order with lifecycle status and immutable snapshots |
| `order_items` | Checkout-created line item linked to its parent order and product |
| `order_item_refunds` | Workflow-created actual refund linked to its request, item, and order |

For each entity, make the primary key and relevant foreign keys visible. Where
space permits, include the Source label and the user-facing date/time. Do not
publish the `password_hash`, reset-token fields, JWT secret, database password,
or full Authorization header.

## Database and design artifacts

- Include `ERD_FINAL.svg` or its PNG equivalent.
- Include `ERD_SPEC.md`, `CRUD_ROLE_MATRIX.md`, and the migration/schema DDL.
- Include canonical baseline counts from the successful verification output.
- Include the dataset source and justification and the concurrency reflection.
- Keep a short caption under every screenshot stating the role, operation, and
  expected result.
