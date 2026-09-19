# RetailMetrics Final Evidence Checklist

## Verified presentation starting state

- [ ] Catalog product IDs `1`, `2`, `3`, and `4` are configured, available, and use the neutral placeholder.
- [ ] Presentation customer ID `105` is active and unlocked with the intended profile only.
- [ ] Address ID `35` is the single active/default presentation address.
- [ ] Payment method ID `56` is the single active/default simulated card (`Demo Card`, safe last four `0000`).
- [ ] The cart contains zero items; orders and refund requests both equal zero.
- [ ] Admin, Operations Staff, and Analyst accounts are active and unlocked.

Capture screenshots at a normal laptop viewport, preferably 1366×768. Do not include passwords, JWTs, reset tokens, `.env`, PostgreSQL credentials, browser cookies, or real personal/payment information.

## Architecture and data boundary

- [ ] Browser → Streamlit → HTTP → FastAPI → PostgreSQL architecture.
- [ ] Final ERD with staff/customer identities and lifecycle relationships.
- [ ] Canonical counts for all six imported tables/views.
- [ ] Historical data versus Application-created source labels.
- [ ] PostgreSQL listening only on loopback port 5432.

## Customer Portal

- [ ] Storefront with four configured products and neutral image placeholders.
- [ ] Product Details page with price and description but no COGS.
- [ ] Cart containing the selected demonstration product.
- [ ] Cart Item Create, Read, quantity Update, and literal Remove/Delete.
- [ ] Checkout address/payment review and simulated-payment disclaimer.
- [ ] Successful pending-order confirmation.
- [ ] My Orders Pending, Processing, Ready / Shipped, and Delivered states where practical.
- [ ] Customer refund-request form and submitted request.
- [ ] My Account tabs: Profile, Addresses, Payment Methods, Security.
- [ ] Customer Address or simulated Payment Method showing Create, Read, Update,
  and Deactivate as a retained-resource delete-equivalent.

## Admin

- [ ] Admin Dashboard KPI cards and global summary.
- [ ] User Management showing the three staff roles without credential data.
- [ ] Customer Accounts showing the presentation customer.
- [ ] Customers page showing historical and registered categories.
- [ ] Storefront Catalog configuration and source-product relationship.
- [ ] Order/refund oversight pages.
- [ ] Orders page showing lifecycle actions without generic Create/Update/Delete
  transaction tabs.
- [ ] Refunds page showing processed refund evidence as read-only.

## Operations Staff

- [ ] Operations Dashboard and quick-access queues.
- [ ] Pending order in Orders Needing Action.
- [ ] Start Processing action.
- [ ] Mark Ready / Shipped staff action and customer Mark as Received confirmation.
- [ ] Pending refund request.
- [ ] Approval and processing controls.
- [ ] Absence of User Management and catalog-editing controls.
- [ ] Absence of generic Create Order, Create Order Item, and Create Refund controls.

## Analyst

- [ ] Analytics Dashboard imported-scope KPIs.
- [ ] Revenue/orders trends and product performance.
- [ ] Traffic-source and device summaries.
- [ ] Deidentified historical/registered Customers views.
- [ ] Read-only Products, Orders, Refunds, and unified Website Traffic tabs.
- [ ] Business Reports without technical Project Evidence.
- [ ] Absence of operational mutation controls.

## Security and concurrency

- [ ] Analyst direct mutation request returning HTTP 403.
- [ ] Imported-row update/delete refusal.
- [ ] Stale `row_version` mutation returning HTTP 409.
- [ ] Explanation that cancellation/deactivation replaces unsafe physical
  deletion for retained lifecycle resources.
- [ ] Temporary login lockout and Admin unlock, if included in the allotted time.

## Verification evidence

- [ ] Full test-suite final line showing PASS.
- [ ] Migration 002 verifier showing all schema/data checks passing; if the
  already-known Session 1/2 evidence-hash mismatch remains, disclose it
  separately rather than presenting it as a new migration regression.
- [ ] Canonical-count verification after presentation setup.
- [ ] Historical-data metrics: 32,313 orders; $1,938,509.75 gross revenue; $722,370.25 COGS; $1,216,139.50 gross profit; $85,338.69 refunds; and $1,853,171.06 net revenue.
- [ ] Session 3 reconciliation PASS.
- [ ] LAN health from the current host IPv4 address.

## Screenshot hygiene

- [ ] Use only clearly marked presentation data.
- [ ] Crop unrelated desktop content and notifications.
- [ ] Keep page title, role badge, and relevant result visible.
- [ ] Never capture passwords, tokens, secrets, or `.env` contents.
- [ ] Record the demonstrated order ID separately so the targeted rehearsal reset can be dry-run first.
- [ ] After any rehearsal reset, capture the final zero cart-item/order/refund-request check before the assessed demonstration.
