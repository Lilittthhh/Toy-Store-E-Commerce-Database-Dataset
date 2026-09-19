# RetailMetrics Customer Portal — Final ERD Specification

## Scope and identity boundary

Migration 002 extends the existing `public` Toy Store schema; it does not copy
the six dataset tables. `app_users` remains exclusively for staff identities
(`admin`, `operations_staff`, `analyst`). Customer login identity is held in
`customer_accounts`. The imported dataset's `website_sessions.user_id` is a
shopper identifier, not an application or customer login foreign key.

`customer_accounts.dataset_user_id` is therefore a nullable, unique logical
association only. It has no FK and creates no public historical-account claiming
flow. Analysts use the deidentified `historical_customer_summary` view.

In the field summaries below, `NN` means NOT NULL and `?` means nullable. All
mutable portal entities include `row_version BIGINT NN DEFAULT 1` and
`created_at/updated_at TIMESTAMPTZ NN` unless explicitly noted.

## Staff and customer identity

### `app_users` (existing, staff only)

`app_user_id BIGINT PK`; case-insensitive unique `username VARCHAR(64) NN` and
`email VARCHAR(254) NN`; `password_hash TEXT NN`; `role VARCHAR(32) NN`;
activation, lockout, reset-token, `token_version`, `row_version`, and timestamps.
Staff accounts are deactivated rather than deleted.

### `customer_accounts`

`customer_account_id BIGINT IDENTITY PK`; `dataset_user_id BIGINT ?` (partial
unique when non-null); case-insensitive unique `email VARCHAR(254) NN`;
`password_hash TEXT NN`; `is_active BOOLEAN NN`; `failed_login_attempts INTEGER
NN`; `locked_until/last_login_at TIMESTAMPTZ ?`; password-change and paired
hashed password-reset fields; `token_version INTEGER NN`; row version and
timestamps. No name, address, staff role, or payment credential is stored here.

### `customer_profiles`

`customer_account_id BIGINT PK/FK -> customer_accounts ON DELETE RESTRICT`;
`first_name VARCHAR(100) NN`; `last_name VARCHAR(100) NN`; `phone VARCHAR(32) ?`;
row version and timestamps. This is a strict 1:0..1 profile relationship.

### `customer_addresses`

`customer_address_id BIGINT IDENTITY PK`; `customer_account_id BIGINT NN FK ->
customer_accounts RESTRICT`; label, recipient first/last name, optional phone,
address lines, city, province/region, postal code, and two-letter country code;
`is_default/is_active BOOLEAN NN`; row version and timestamps. A partial unique
index permits at most one active default address per customer.

### `payment_methods` (simulation metadata only)

`payment_method_id BIGINT IDENTITY PK`; `customer_account_id BIGINT NN FK ->
customer_accounts RESTRICT`; `method_type` in `card`, `gcash`, `paypal`, or
`cash_on_delivery`; safe `display_label`; optional `card_brand` and exactly four
digits in `card_last_four` only for simulated cards; default/active flags, row
version, and timestamps. Full card numbers, CVV, actual GCash numbers, PayPal
emails, OTPs, credentials, and gateway tokens are deliberately absent.

## Catalog and cart

### `products` (existing, extended)

Original columns plus `created_by_app_user_id BIGINT ? FK -> app_users RESTRICT`,
`row_version BIGINT NN`, and `record_origin VARCHAR(16) NN`. Allowed origins:
`imported`, `staff`.

### `product_catalog_details`

`product_id BIGINT PK/FK -> products RESTRICT`; `description TEXT NN`;
`current_price_usd/current_cogs_usd NUMERIC(12,2) NN`; `image_url TEXT ?`;
`is_available BOOLEAN NN`; `updated_by_app_user_id BIGINT NN FK -> app_users
RESTRICT`; row version and timestamps. Migration 002 creates no rows or invented
prices; staff must populate these later through an authorized workflow.

### `shopping_carts`

`shopping_cart_id BIGINT IDENTITY PK`; `customer_account_id BIGINT NN FK ->
customer_accounts RESTRICT`; `cart_status` in `active`, `converted`, `abandoned`;
`converted_order_id BIGINT ?`, unique and ownership-checked against the same
customer order; row version and timestamps. A partial unique index permits one
active cart per customer. A converted cart must have an order; other statuses
must not.

### `cart_items`

`cart_item_id BIGINT IDENTITY PK`; `shopping_cart_id BIGINT NN FK ->
shopping_carts ON DELETE CASCADE`; `product_id BIGINT NN FK -> products
RESTRICT`; `quantity INTEGER NN` from 1 to 99; positive `unit_price_usd
NUMERIC(12,2)`; row version and timestamps; unique `(shopping_cart_id,
product_id)`. The stored price is informational for the cart; checkout must
revalidate availability and price server-side.

## Dataset and order workflow

### `website_sessions` and `website_pageviews` (existing, read-only)

`website_sessions.website_session_id BIGINT PK` has the original timestamp,
dataset `user_id`, repeat, campaign, device, and referrer columns.
`website_pageviews.website_pageview_id BIGINT PK` has `website_session_id BIGINT
NN FK -> website_sessions`, timestamp, and URL. RetailMetricsWeb never writes
either table.

### `orders` (existing, extended)

Original PK, monetary, item-count, and optional primary-product relationship;
`website_session_id` and dataset `user_id` become nullable only to support
customer-origin orders. New fields are `record_origin VARCHAR(16) NN`,
`customer_account_id BIGINT ? FK -> customer_accounts RESTRICT`, `order_status
VARCHAR(16) ?`, and `updated_at`. Allowed statuses are `pending`, `processing`,
`ready_shipped`, `delivered`, `cancelled`, and `refunded`. Migration 004 adds
nullable `delivered_at` and non-null `delivered_confirmed_by_customer` (default
false). A delivered order requires both a timestamp and customer confirmation.

The existing unique `orders.website_session_id` remains. Consequently a
non-null website session has 0..1 order, while a customer-origin order has no
website session and PostgreSQL permits multiple null values.

### `order_items` (existing, extended)

Original PK, order/product FKs, monetary columns, creator, and row version plus
`record_origin VARCHAR(16) NN`. There is deliberately no
`customer_account_id`: customer ownership is derived and authorized through
`order_items.order_id -> orders.customer_account_id`. A composite FK enforces
`(order_id, record_origin) -> orders(order_id, record_origin)`.

### `order_shipping_addresses`

One immutable checkout snapshot per applicable customer order: `order_id BIGINT
PK`; `customer_account_id BIGINT NN`; optional source address; recipient/contact
and full address snapshot; row version and timestamps. Composite FKs enforce
that the order and optional saved address belong to the same customer. Source
address edits never rewrite this snapshot.

### `order_payments`

`order_payment_id BIGINT IDENTITY PK`; unique `order_id BIGINT NN`;
`customer_account_id BIGINT NN`; optional saved `payment_method_id`; safe
`method_type` and immutable `payment_display_snapshot`; status in `pending`,
`paid`, `failed`, `partially_refunded`, `refunded`; positive amount; optional
simulated reference and processed timestamp; row version and timestamps.
Composite FKs enforce order/payment-method ownership. Imported orders receive
no payment row from this migration.

### `refund_requests`

`refund_request_id BIGINT IDENTITY PK`; customer, order, and order-item FKs;
reason; positive requested amount; status in `pending`, `approved`, `rejected`,
`processed`; optional resolution note; optional reviewing `app_user`; reviewed
timestamp; row version and timestamps. Composite FKs prove the customer owns
the order and the item belongs to it. Only one pending request per customer/item
is permitted. Non-pending requests require reviewer and reviewed timestamp.

### `order_item_refunds` (existing, extended)

Original fields plus `record_origin VARCHAR(16) NN` and `refund_request_id
BIGINT ?`. A composite FK requires a referenced request to name the same order
and item. A customer-origin refund means the customer requested it and staff
approved/processed it; it never means the customer inserted the refund.

## Exact record-origin rules

Actor attribution (`created_by_app_user_id`) and business context
(`record_origin`) are separate concepts.

| Entity | Constraint |
|---|---|
| products | `imported` iff creator is null; `staff` requires a creator |
| orders | `imported`: creator/customer null, website session and dataset user non-null, status null; `staff`: creator non-null, customer null, website session/user/status non-null; `customer`: customer/status non-null, website session/user null, creator optional |
| order_items | `imported` requires null creator; `staff` requires creator; `customer` allows optional staff creator; origin must equal parent order origin |
| order_item_refunds | `imported`: creator/request null; `staff`: creator non-null/request null; `customer`: creator and matching refund request non-null |

Compatibility triggers infer an origin only when an older importer/client omits
it. Orders with a customer account become `customer`; items inherit their parent
order's origin; refunds with a request become `customer`; otherwise a null staff
creator becomes `imported` and a populated creator becomes `staff`. Existing
staff order inserts that omit status receive `ready_shipped` after Migration
004. Future customer APIs
must still set origin explicitly. The triggers never reinterpret an explicit
origin, and the origin-context CHECK constraints reject inconsistent input.

## Relationships and multiplicities

```text
AppUser 1 -> 0..* application-created Product / Order / OrderItem / Refund
AppUser 1 -> 0..* ProductCatalogDetail updates and RefundRequest reviews
CustomerAccount 1 -> 0..1 CustomerProfile
CustomerAccount 1 -> 0..* CustomerAddress / PaymentMethod / ShoppingCart
ShoppingCart 1 -> 0..* CartItem
Product 1 -> 0..1 ProductCatalogDetail; Product 1 -> 0..* CartItem / OrderItem
WebsiteSession 1 -> 0..* WebsitePageview
WebsiteSession 1 -> 0..1 Order (only orders with non-null website_session_id)
CustomerAccount 1 -> 0..* customer-origin Order
Order 1 -> 0..* OrderItem
Order 1 -> 0..1 OrderShippingAddress / OrderPayment
CustomerAccount 1 -> 0..* RefundRequest
OrderItem 1 -> 0..* RefundRequest / OrderItemRefund
RefundRequest 1 -> 0..1 processed customer-origin OrderItemRefund
```

There is intentionally no FK from `app_users` to dataset `user_id`, and no
duplicated customer ownership column on `order_items`.

The database permits `CustomerAccount -> CustomerProfile` and
`Order -> Shipping/Payment Snapshot` as 1:0..1 relationships because the child
owns the FK. The application makes the profile mandatory during registration
and creates both snapshots atomically for every successful customer checkout;
imported historical orders correctly have no portal snapshots.

## Implemented transaction and lifecycle rules

Checkout runs in one PostgreSQL transaction: lock/validate the active cart,
revalidate catalog availability and server prices/COGS, verify address/payment
ownership, create the customer order and matching-origin items, copy immutable
shipping/payment snapshots, mark the cart converted, then commit once.

Customer-origin orders are lifecycle records. They have no generic DELETE;
customers may request a validated `pending -> cancelled` transition. Admin and
Operations Staff use only validated `pending -> processing -> ready_shipped` or
pending-order cancellation actions in the final UI. The owning customer alone
confirms `ready_shipped -> delivered`. Order Items are created by
checkout rather than manually, and processing an approved Refund Request creates
the linked Actual Refund. Compatibility deletion remains only for disposable
staff-origin records outside the normal final transaction workflow. All mutable
actions require the last-read `row_version`.

## Analytical boundary

The four canonical views retain their exact names and original CSV columns and
filter exclusively on `record_origin = 'imported'`. Sessions 1–3 therefore keep
their established analytical meaning. `historical_customer_summary` separately
aggregates sessions, orders, and refunds before joining, avoiding multiplicative
totals and exposing only dataset user ID, counts, totals, last visit, latest UTM
source, and latest device type.
