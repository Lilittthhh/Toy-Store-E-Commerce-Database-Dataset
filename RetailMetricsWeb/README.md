# RetailMetricsWeb

RetailMetricsWeb is the separate Streamlit and FastAPI application for the Toy
Store PostgreSQL database. It includes authentication, server-side RBAC,
protected business CRUD, Admin account management, and a presentation-ready
Streamlit interface. It also provides a separate customer authentication and
profile area backed by `customer_accounts` and `customer_profiles`. The
original Tkinter and analytical sessions remain separate.

## Prerequisites

- PostgreSQL 10 or newer
- The `retailmetrics` database already populated by the authoritative Session 1
  CSV migration
- Python 3.10 or newer
- Session 1, Session 2, the Tkinter GUI, and any future web process stopped
  during migration and verification

From `RetailMetricsWeb`, create a dedicated environment and install only the
deployment dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Connection configuration

Copy `.env.example` to `.env` and edit the local values:

```powershell
Copy-Item .env.example .env
```

The scripts read `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`,
`PGSSLMODE`, and `PGCONNECT_TIMEOUT`. Process environment variables take
precedence over `.env`. The password is never embedded in source code or printed.
PostgreSQL password-file or other libpq authentication can be used by omitting
`PGPASSWORD`.

The API additionally requires:

```text
JWT_SECRET_KEY
JWT_ACCESS_TOKEN_MINUTES
AUTH_LOCKOUT_ATTEMPTS
AUTH_LOCKOUT_MINUTES
AUTH_RESET_TOKEN_MINUTES
AUTH_EXPOSE_RESET_TOKEN
```

Generate a private `JWT_SECRET_KEY` of at least 32 characters. Never reuse the
placeholder from `.env.example`. `AUTH_EXPOSE_RESET_TOKEN=true` may return the
raw one-time reset token only when `NOTIFICATION_MODE=mock`; keep it false
outside focused local development. Live mode always suppresses the token.

Generate a strong secret locally with:

```powershell
.\GENERATE_JWT_SECRET.bat
```

or:

```powershell
.\.venv\Scripts\python.exe scripts\generate_jwt_secret.py
```

Copy the generated value into the local, ignored `.env` as
`JWT_SECRET_KEY=<generated-value>`. The generator uses Python's cryptographic
randomness source and does not write the secret to source control. Treat the
displayed value as a credential and do not paste it into logs or documentation.

`AUTH_EXPOSE_RESET_TOKEN` defaults to `false`. Set it to `true` only for a
controlled local mock-mode test. It is deliberately ignored for browser/API
token exposure whenever notification delivery is live.

The local `.env` and generated Session 2 snapshot are ignored by Git.
`API_BASE_URL` controls the HTTP endpoint used by Streamlit. For LAN use, set it
to `http://HOST_IP:8000`, replacing `HOST_IP` with this computer's Wi-Fi/LAN
IPv4 address. `RUN_WEB.bat` automatically replaces a missing, placeholder, or
loopback value with the detected LAN address. Streamlit never reads the
PostgreSQL credentials or connects to PostgreSQL directly.

## Exact deployment order

1. Back up the `retailmetrics` database using the normal local PostgreSQL backup
   procedure.
2. Stop Session 1, Session 2, RetailMetricsGUI, and other database writers.
3. Confirm the original Session 1 CSV migration has already populated all six
   Toy Store tables.
4. Run the migration exactly once:

   ```powershell
   .\RUN_WEB_MIGRATION.bat
   ```

   Or run the equivalent Python command:

   ```powershell
   .\.venv\Scripts\python.exe scripts\run_migration.py
   ```

   Review the displayed host, port, database, user, migration path, and SHA-256.
   Type the database name when prompted. Before submitting the SQL once, the
   runner records a local fingerprint of all Session 2 support tables.

5. Do not rerun automatically if the connection drops or PostgreSQL reports an
   error. Read the complete reported diagnostic and inspect/verify the database
   state first. The runner refuses to execute while an existing pre-migration
   snapshot is present, preventing accidental replacement of the original
   before-state.
6. Run the read-only post-migration verifier:

   ```powershell
   .\VERIFY_WEB_MIGRATION.bat
   ```

   Or:

   ```powershell
   .\.venv\Scripts\python.exe scripts\verify_migration.py
   ```

7. Continue only when the verifier ends with `OVERALL: PASS`.

For non-interactive controlled environments, `run_migration.py --yes` skips the
database-name prompt. It does not add retries and still submits the migration
only once.

## Create the initial Admin

After migration verification passes, run the interactive bootstrap once:

```powershell
.\BOOTSTRAP_ADMIN.bat
```

The script securely prompts for the password twice, never displays it, shows the
target database without its password, and requires typing the database name
before it writes. It creates an Argon2id hash and inserts only one row into
`public.app_users`. It makes no schema changes.

The bootstrap refuses duplicate usernames or emails and refuses to create an
Admin whenever any active Admin already exists. There is deliberately no
additional-Admin override. Future Admin management must use an authenticated
Admin-only application workflow.

For controlled non-interactive use, set `BOOTSTRAP_ADMIN_USERNAME`,
`BOOTSTRAP_ADMIN_EMAIL`, and `BOOTSTRAP_ADMIN_PASSWORD`, then run:

```powershell
.\.venv\Scripts\python.exe scripts\bootstrap_admin.py --yes
```

Avoid storing `BOOTSTRAP_ADMIN_PASSWORD` in `.env`; secure interactive entry is
preferred. Clear any temporary environment variables after the command.

## What verification covers

The verifier starts a read-only transaction and checks:

- `public.app_users`
- Creator and row-version columns on all four mutable business tables
- All four validated creator foreign keys and their `ON DELETE SET NULL` action
- The unique `orders.website_session_id` index
- The shared application ID sequence and all four PK defaults
- All four non-updatable canonical views, their filters, and original CSV shapes
- Exact canonical imported counts for products, orders, order items, and refunds
- The original six Toy Store primary keys and seven foreign-key relationships
- An exact pre/post comparison of Session 2 support-table presence, columns,
  defaults, constraints, indexes, and row counts

The verifier performs no writes and rolls back its read-only transaction before
closing the connection.

## Run the API

After the migration and post-migration verification pass, start the backend:

```powershell
.\RUN_API.bat
```

Equivalent command:

```powershell
.\.venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/docs` for the local OpenAPI interface.

## Run the complete web application on the local network

After configuring `.env`, verifying the migration, and bootstrapping the first
Admin, find the host computer's LAN address. In Command Prompt or PowerShell,
run:

```powershell
ipconfig
```

Under the active **Wireless LAN adapter Wi-Fi**, locate **IPv4 Address** (for
example, `192.168.1.25`). Do not use the Default Gateway address. Put that value
in `.env`:

```text
API_BASE_URL=http://192.168.1.25:8000
```

Then start FastAPI and Streamlit together:

```powershell
.\RUN_WEB.bat
```

The launcher binds FastAPI to `0.0.0.0:8000` and Streamlit to `0.0.0.0:8501`,
starts FastAPI as a hidden child process, waits for its local `/health` endpoint,
and then runs Streamlit in the current console. It prints the detected LAN URLs.
On another device connected to the same Wi-Fi/LAN, open:

```text
http://HOST_IP:8501
```

For the example above, that is `http://192.168.1.25:8501`. FastAPI's authenticated
API and documentation are reachable at `http://HOST_IP:8000` and
`http://HOST_IP:8000/docs`. Stopping Streamlit also stops the FastAPI child
process.

### Windows Firewall

Both computers must be on the same trusted network, and the host's Windows
network profile should be **Private**. If Windows prompts when the launcher is
first run, allow Python only on Private networks. If no prompt appears, an
administrator can add narrowly scoped inbound rules in PowerShell:

```powershell
New-NetFirewallRule -DisplayName "RetailMetrics Streamlit LAN" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8501 -Profile Private
New-NetFirewallRule -DisplayName "RetailMetrics FastAPI LAN" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000 -Profile Private
```

Do not enable these rules for the Public profile, and do not configure router
port forwarding. FastAPI still enforces authentication and RBAC on protected
endpoints; LAN binding does not bypass application authorization.

PostgreSQL must remain local to the host. Keep `PGHOST=localhost`, do not add a
Windows Firewall inbound rule for port `5432`, and do not expose or forward that
port on the router. Only FastAPI connects to PostgreSQL; Streamlit and remote
browsers do not.

To run each process separately for host-only development, use `RUN_API.bat` and:

```powershell
.\.venv\Scripts\python.exe -m streamlit run frontend\app.py
```

Authentication endpoints are under `/auth`. Send the signed access token as:

```text
Authorization: Bearer <access-token>
```

Logout, password change, and successful password reset increment
`app_users.token_version`, invalidating all previously issued access tokens for
that account. Every authenticated request reloads the account, role, activation
state, lock state, and token version from PostgreSQL.

### Browser refresh and data refresh behavior

After login, Streamlit keeps the raw FastAPI access token in server memory and
places only a random, opaque session handle in a non-persistent,
`SameSite=Strict` browser-session cookie. A normal browser refresh uses that
handle to recover the server-held token, then calls `/auth/me` before rendering
any protected page. FastAPI remains
authoritative for token expiry and invalidation, account status, lockout, and
role. Logout, password change, and failed session validation revoke the handle
and clear the cookie.

This classroom-oriented persistence survives F5 and new Streamlit connections
while the Streamlit process remains running. It deliberately does not survive a
Streamlit server restart, and it does not place the JWT in a URL, visible field,
or browser storage. Because the application uses plain HTTP on a local LAN, the
cookie cannot use the `Secure` flag there; it is added automatically when the
site is served over HTTPS. Use only a trusted Private network.

Dashboard and data-management pages include **Refresh Data**. The application
does not cache those API responses, so pressing the button reruns the current
page and immediately issues fresh FastAPI requests without changing navigation
or authentication state. Automatic polling is intentionally disabled.

## Business API and final UI boundary

All business endpoints require bearer authentication. Collection responses use
the common shape `items`, `total`, `limit`, and `offset`; `limit` is capped at
100. Mutable collections support `origin=all|imported|web`, and entity-specific
filters are documented in OpenAPI.

| Entity | Collection | Item | Final application workflow |
|---|---|---|---|
| Products | `GET /products` | `GET /products/{product_id}` | Admin CRUD for application-created Products; historical rows protected |
| Orders | `GET /orders` | `GET /orders/{order_id}` | Customer Checkout creates; Customer/staff read; validated lifecycle updates; no physical delete |
| Order items | `GET /order-items` | `GET /order-items/{order_item_id}` | Checkout creates automatically; read through Order; no normal independent mutation UI |
| Refunds | `GET /refunds` | `GET /refunds/{refund_id}` | Approved Refund Request processing creates; read-only outcome history |
| Website sessions | `GET /website-sessions` | `GET /website-sessions/{website_session_id}` | Read-only |
| Website pageviews | `GET /website-pageviews` | `GET /website-pageviews/{website_pageview_id}` | Read-only |

Some server-authorized compatibility routes remain for controlled automated
verification, but they are excluded from the normal final staff workflow and
cannot mutate protected historical or customer-origin transactions. Streamlit
provides generic entity CRUD only for appropriate Product master data. Customer
commerce uses Checkout, order lifecycle, and Refund Request endpoints instead
of manual Order, Order Item, or Actual Refund creation.

`PUT` requests include the last-read `row_version`. `DELETE` sends it as the
required `row_version` query parameter. Successful updates increment the
version; stale updates or deletes return HTTP 409.

FastAPI derives `created_by_app_user_id` from the authenticated account. That
field is forbidden in request bodies. Imported rows remain visible but return
HTTP 403 for mutation attempts. Orders enforce one order per website session,
and cumulative refunds cannot exceed the referenced order-item price.

## Professor CRUD/RBAC alignment

RetailMetrics demonstrates CRUD according to ownership and least privilege
rather than giving one role unrestricted table editing:

- **Cart Items (Customer)** provide literal full CRUD: Add, View, Change
  Quantity, and Remove.
- **Addresses and simulated Payment Methods (Customer)** provide Create, Read,
  Update/default selection, and deactivation. Deactivation is the safe
  delete-equivalent for retained owned resources.
- **Staff Users (Admin)** provide Create, Read, role/status Update, unlock, and
  deactivation; identities are never physically deleted.
- **Products (Admin)** provide CRUD only for application-created Product rows.
  Historical Products remain protected. Catalog configuration is a separate
  customer-facing extension.
- **Orders and Order Items** are created atomically by Customer Checkout. Orders
  use validated lifecycle transitions; Order Items are read-only after creation.
- **Refund Requests** are Customer-created and reviewed by Admin/Operations.
  Processing an approved request creates exactly one read-only Actual Refund.

Financial transactions are retained for audit integrity. Cancellation is an
Order lifecycle action, not Delete. Every mutation travels from Streamlit over
HTTP to FastAPI, where authentication, ownership, RBAC, validation, and
optimistic concurrency remain authoritative. Direct unauthorized requests are
refused even when a UI control is hidden.

## Admin account management API

Only an authenticated Admin can use these endpoints:

- `GET /admin/users` — paginated search and role/status filtering
- `GET /admin/users/{app_user_id}`
- `POST /admin/users` — create Admin, Operations Staff, or Analyst
- `PUT /admin/users/{app_user_id}/role`
- `PUT /admin/users/{app_user_id}/status`
- `POST /admin/users/{app_user_id}/unlock`

Administrative changes use `row_version`. Role or activation changes increment
`token_version`, immediately invalidating the affected user's existing tokens.
An Admin cannot demote or deactivate their own account, and the final active
Admin is protected. There is no physical user-deletion endpoint. Public
`/auth/register` remains restricted to Analyst accounts.

## Customer authentication and profile API

Customers are separate from staff and are never represented as an
`app_users.role`. Staff JWTs retain `type=access`; customer JWTs use
`type=customer_access`. Each protected request validates the expected token
type and reloads the corresponding account, status, lock state, and token
version from PostgreSQL.

Customer endpoints:

- `POST /customer/auth/register`
- `POST /customer/auth/login`
- `GET /customer/auth/me`
- `POST /customer/auth/logout`
- `POST /customer/auth/change-password`
- `POST /customer/auth/forgot-password`
- `POST /customer/auth/reset-password`
- `GET /customer/profile`
- `PUT /customer/profile`

Registration atomically creates one `customer_accounts` row and its required
`customer_profiles` row. Public input cannot set `dataset_user_id`, account
state, security metadata, staff roles, or row versions. Profile updates are
limited to the authenticated customer's first name, last name, and optional
phone and use optimistic concurrency through `row_version`.

Admin-only customer controls:

- `GET /admin/customers`
- `GET /admin/customers/{customer_account_id}`
- `PUT /admin/customers/{customer_account_id}/status`
- `POST /admin/customers/{customer_account_id}/unlock`

These responses omit password/reset hashes and token versions. Operations Staff
and Analysts cannot use the customer-administration endpoints. Customer
accounts are never physically deleted.

## Streamlit pages and roles

The entry screen separates **Customer Portal** from **Staff Portal**. The
customer area includes Customer Login, Customer Register,
Forgot/Reset Password, My Account with Profile, Addresses, Payment Methods and
Security sections, Home/Shop, Cart, Checkout, My Orders, and Logout. Customer and staff tokens use separate
Streamlit state, server-side opaque-handle stores, and browser cookie names.

## Customer addresses and simulated payment methods

Authenticated customers can manage only their own saved resources through:

- `GET|POST /customer/addresses`
- `GET|PUT /customer/addresses/{address_id}`
- `POST /customer/addresses/{address_id}/set-default`
- `POST /customer/addresses/{address_id}/deactivate`
- `GET|POST /customer/payment-methods`
- `GET|PUT /customer/payment-methods/{payment_method_id}`
- `POST /customer/payment-methods/{payment_method_id}/set-default`
- `POST /customer/payment-methods/{payment_method_id}/deactivate`

Resources are deactivated rather than physically deleted. The first active
address or payment method becomes the default automatically. Setting a new
default is atomic. If a default is deactivated, the lowest-ID remaining active
resource is promoted atomically; no default remains only when there is no other
active resource. Every update, default change, and deactivation requires the
last-read `row_version`; stale requests return HTTP 409.

Payment methods are classroom simulations only. The API accepts a simulated
brand and four demo digits for cards and generates every display label on the
server. GCash, PayPal, and Cash on Delivery use fixed safe labels. Full card
numbers, CVVs, expiry details, mobile/account identifiers, credentials, OTPs,
client-supplied display labels, and client-supplied ownership fields are
rejected by strict request schemas.

## Customer storefront and persistent cart

The source `products` rows remain unchanged. Admin configures their storefront
extension in `product_catalog_details`; no descriptions, prices, COGS values,
images, or availability values are seeded or inferred. Staff roles can inspect
configuration through `GET /admin/catalog`, while only Admin can create or
update it through `PUT /admin/catalog/{product_id}`. Updates use
`row_version`, and the customer projection never includes COGS or staff audit
metadata.

Authenticated customer endpoints are:

- `GET /customer/store/products?search=...`
- `GET /customer/store/products/{product_id}`
- `GET /customer/cart`
- `POST /customer/cart/items`
- `PUT /customer/cart/items/{cart_item_id}`
- `DELETE /customer/cart/items/{cart_item_id}?row_version=...`

Only configured, available products appear in the store. Unconfigured or
unavailable product details return 404. The first add creates or reuses the
customer's single active cart. Adding the same product again increments its
quantity up to the database limit of 99 and never creates a duplicate line.
Prices are loaded server-side: the stored cart price is retained when catalog
pricing changes, while the cart response exposes the current catalog price and
a `price_changed` flag. Unavailable products already in a cart remain visible
and removable. Quantity zero is rejected; removal is an explicit cart-item
delete.

## Customer checkout and order history

Authenticated customer checkout and order-history endpoints are:

- `POST /customer/checkout`
- `GET /customer/orders`
- `GET /customer/orders/{order_id}`
- `POST /customer/orders/{order_id}/cancel`

Checkout accepts only an owned active address ID, an owned active simulated
payment-method ID, and the last-read active-cart `row_version`. In one database
transaction it locks the active cart and its lines, locks and validates the
authoritative catalog records, rejects empty, unavailable, or price-changed
carts, validates the selected resources, calculates revenue and COGS with
exact decimal arithmetic, and creates the customer-origin order, one order-item
row per unit, immutable shipping snapshot, and safe simulated-payment snapshot.
It then converts and links the cart before the request-level transaction
commits. Any exception rolls the complete operation back.

Card, GCash, and PayPal simulations begin as `paid`; Cash on Delivery begins as
`pending`. No real payment credential is accepted or stored. A successful
prepaid cancellation changes its simulated payment to `refunded`. Because the
approved payment-status constraint has no cancelled value, cancelling a pending
Cash on Delivery order leaves its payment `pending`, meaning no collection has
occurred, while the order becomes `cancelled`.

Customers can list and view only their own customer-origin orders; inaccessible
IDs return privacy-preserving 404 responses. Customer projections omit COGS,
creator metadata, and security fields. Only a pending order can be cancelled,
and cancellation requires its current `row_version`; stale or invalid lifecycle
transitions return HTTP 409. Converted carts are retained as history and cannot
be checked out twice. A later add-to-cart operation creates a new active cart.

## Customer refund requests and staff processing

Customers submit refund requests through `POST /customer/refund-requests` and
can list or view only their own requests. An item is eligible only when its
customer-origin parent order is `ready_shipped` or `delivered`, its simulated payment is `paid` or
`partially_refunded`, and the requested amount does not exceed the item price
less actual refunds and approved reservations. Foreign, imported, and
staff-origin records receive privacy-preserving 404 responses. Unpaid Cash on
Delivery orders are not refundable because no simulated payment was collected.

Admin and Operations Staff use the dedicated Refund Requests queue to approve,
reject, and process requests. Analyst access is read-only. Every transition
requires the current `row_version`; invalid or stale transitions return HTTP
409. Rejections require a resolution note, while approval notes are optional.

Processing locks the request and related business rows, revalidates ownership
and the remaining refundable amount, creates exactly one customer-origin
`order_item_refunds` row attributed to the authenticated staff processor, and
marks the request processed in one transaction. Cumulative refunds below the
order total set the simulated payment to `partially_refunded` without changing
the operational order status. Cumulative refunds covering the full order set
both payment and order to `refunded`. Customers never insert actual refund rows
directly, and customer-origin refunds remain outside canonical analytical views.

The final staff experience separates resource CRUD from transaction lifecycles:

- Admin sees Dashboard, User Management, Customer Accounts, Customers, Products,
  Storefront Catalog, Orders, Refund Requests, Refunds, Website Traffic,
  Analytics Dashboard, Business Reports, Project Evidence, My Account, and
  Logout.
- Operations Staff sees Dashboard, Customers, Orders, Refund Requests, Refunds,
  read-only Products and Storefront Catalog, My Account, and Logout. Operations
  does not receive generic transaction CRUD controls.
- Analyst sees read-only Analytics Dashboard, Customers, Products, Orders,
  Refunds, Website Traffic, Business Reports, My Account, and Logout.

Order Items remain available through protected API/read projections and within
customer order details, but are not a standalone normal staff navigation item.
Customers create them only as part of atomic checkout. Actual Refunds are
read-only evidence in the Refunds page and are created only when authorized
staff processes an approved Refund Request.

Tables distinguish historical, application-created, and customer-created
records where applicable. Historical rows never appear in permitted mutation
selectors. The
frontend preserves the last-read `row_version`, but FastAPI remains
authoritative for every permission and concurrency decision.

## Customer order operations workflow

Customer-created orders use dedicated lifecycle endpoints rather than generic
CRUD mutations:

- `GET /order-workflow/orders`
- `POST /orders/{order_id}/start-processing`
- `POST /orders/{order_id}/ready-shipped`
- `POST /orders/{order_id}/cancel`
- `POST /customer/orders/{order_id}/confirm-delivery` (owning customer only)

The only allowed transitions are `pending → processing`, `processing →
ready_shipped`, `pending → cancelled`, and customer-confirmed `ready_shipped →
delivered`. Admin and Operations Staff perform only the staff transitions;
Analysts can inspect the deidentified workflow queue but cannot mutate it.
Every action locks the order and simulated payment, requires the current
`row_version`, and returns the incremented version. Historical and
staff-origin orders cannot use these endpoints, and customer-created orders remain protected
from generic staff CRUD.

Prepaid simulated payments stay `paid` through normal processing. Cash on
Delivery remains `pending` while processing and becomes `paid` when staff marks
the order Ready / Shipped, representing classroom-simulated collection. Cancelling a
pending prepaid order changes its payment to `refunded`; cancelling an unpaid
COD order leaves payment `pending`. Creator attribution is never rewritten by a
lifecycle action. Successful transitions are written to application logs with
the staff actor ID; no persistent audit-history table is claimed.

## Safe unit tests

The focused tests use an in-memory repository and never connect to PostgreSQL:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## Database-backed authentication tests

The integration suite is opt-in and uses the configured `retailmetrics`
PostgreSQL database:

```powershell
.\RUN_DB_AUTH_TESTS.bat
```

It tests registration, login, current-user lookup, password change,
forgot/reset password, temporary lockout, logout and token invalidation, and
Admin-only authorization against `public.app_users`. Each run creates uniquely
prefixed disposable authentication users. Cleanup first proves that none of
those users is referenced by a business table, then deletes only those exact
test users. It never inserts, updates, or deletes a business record and never
modifies the schema.

The equivalent command is:

```powershell
$env:RUN_DB_INTEGRATION_TESTS = "1"
.\.venv\Scripts\python.exe -m pytest -m integration tests\integration
Remove-Item Env:RUN_DB_INTEGRATION_TESTS
```

Run only the PostgreSQL-backed CRUD suite with:

```powershell
.\RUN_DB_CRUD_TESTS.bat
```

Run every PostgreSQL-backed authentication and CRUD test with:

```powershell
.\RUN_DB_TESTS.bat
```

CRUD integration cleanup deletes only rows attributed to that run's uniquely
prefixed disposable users, in refund-to-product dependency order. It then
confirms all four canonical analytical counts still equal their before-test
values.

## Data boundary

- Analytics use `canonical_*` views by default.
- Historical analytical rows use `record_origin='imported'` and remain protected.
- Application business context uses `record_origin='staff'` or
  `record_origin='customer'` as appropriate.
- `created_by_app_user_id` is separate actor attribution; it is not the business
  source definition.
- The API must derive creator attribution from the authenticated account and
  must never accept it from client input.

## Role-specific staff experience and analytics

The Staff Portal now opens a distinct workspace for each role:

- **Admin** sees system/security health, staff and customer administration,
  catalog configuration, operational queues, and global business context.
- **Operations Staff** sees daily order/refund queues and operationally
  necessary customer information, without staff-user administration or
  catalog editing.
- **Analyst** opens directly to the read-only Analytics Dashboard and Reports,
  with deidentified customer intelligence and no mutation controls.

The Customers page deliberately separates **Historical Customers**
from **Registered Customers**. Historical shoppers are identified only as
`Historical Shopper #<dataset user ID>` and are derived from canonical
activity; no name or email is invented. Registered-customer output is projected by the API so
Analyst responses omit email, name, phone, lock state, and security data.

Dashboard SQL lives in the dedicated read-only `AnalyticsRepository` and
`AnalyticsService`. Supported report scopes are **Historical Data**,
**Application-Created**, and **Combined**. Aggregation, filtering, and page
limits are server-side; Streamlit never loads all session or pageview rows.
Conversion is reported only for Historical Data because application
orders have no synthetic website session.

Reports may read the known files under
`../session3_distributed_services/results/`. The API does not import or execute
Session 1, 2, or 3 modules. Session 3 benchmark values are labeled as local,
machine/run-specific observations, and product performance is not claimed as
a cross-session comparison.

## Submission documentation

The presentation and submission artifacts are under `docs/`:

- `ERD_SPEC.md` — detailed entities, keys, rules, and multiplicities
- `erd/ERD_FINAL.svg` and `erd/ERD_FINAL.png` — rendered final ERD/UML
- `erd/retailmetrics_erd.dot` — editable Graphviz diagram source
- `CRUD_ROLE_MATRIX.md` — finalized server-enforced permission matrix
- `DATASET_JUSTIFICATION.md` — dataset source and suitability
- `CONCURRENCY_REFLECTION.md` — parallel/distributed-systems reflection
- `DEMONSTRATION_SCRIPT.md` — presentation checklist and safe cleanup order
- `SUBMISSION_EVIDENCE_GUIDE.md` — screenshots and sample-data evidence to
  capture without exposing credentials or changing imported rows

## Final presentation setup

Presentation setup uses the normal FastAPI Admin login, catalog, customer
registration, customer login, address, and simulated-payment endpoints. Run it
interactively so passwords are hidden and never stored or printed:

```powershell
cd RetailMetricsWeb
.\.venv\Scripts\python.exe scripts\setup_presentation_data.py
```

The approved presentation customer is
`presentation.customer@example.com`. Setup is refused if that identity has
existing cart, order, or refund-request activity. The four source products
remain unchanged; presentation fields are stored only in
`product_catalog_details`.

For rehearsal cleanup, supply every exact presentation order ID. Dry-run is
the default:

```powershell
.\.venv\Scripts\python.exe scripts\reset_presentation_data.py --order-id ORDER_ID
```

Replace `ORDER_ID` with the exact ID recorded during the rehearsal; do not
guess or reuse an example ID. Only after reviewing the dry-run targets should
`--execute` be added. The utility
requires exact interactive confirmation, accepts only customer-origin orders
owned by the approved presentation customer, and never uses `TRUNCATE` or a
broad delete. Catalog configuration, customer identity, address, and simulated
payment method are retained.

See `docs/FINAL_PRESENTATION_SCRIPT.md` and
`docs/FINAL_EVIDENCE_CHECKLIST.md` for the final demonstration and screenshot
order.

## Customer notifications (Migration 003)

`public.notification_outbox` is an additive, operational table for registered
customer order/refund events. The business event and outbox rows commit in one
transaction; dispatch starts only after that commit. Historical imported rows
never queue notifications. By default `NOTIFICATION_MODE=mock`: complete email
or SMS payloads are rendered and marked simulated/sent without network access.
Automated tests force this mode and disable the live-send gate.

Live email uses Gmail SMTP independently from SMS. Configure the ignored local
`.env` with `NOTIFICATION_MODE=live`, `EMAIL_PROVIDER=smtp`, the `SMTP_*`
settings documented in `.env.example`, and `SMTP_LIVE_SEND_ENABLED=true` only
when an intentional send is required. Brevo SMS remains simulated by default;
real delivery requires `NOTIFICATION_MODE=live`, `SMS_PROVIDER=brevo`, and
`BREVO_SMS_LIVE_SEND_ENABLED=true` with a configured key and sender.
See [notification operations](docs/NOTIFICATIONS.md)
for the channel-specific safety gates.

Migration 003 has been applied to the local `retailmetrics` database. Its
pre-migration custom-format backup is
`backups/retailmetrics_pre_migration003_20260913_222028.backup`; keep it private
and do not overwrite it. On another database, first take and verify a fresh
custom-format backup in `backups/`, then run:

```powershell
.\.venv\Scripts\python.exe scripts\run_migration_003.py --backup backups\retailmetrics_pre_migration003_YYYYMMDD_HHMMSS.backup
.\.venv\Scripts\python.exe scripts\verify_migration_003.py
```

The runner refuses a second application and requires typing the database name
unless `--yes` is supplied. Do not run it against this already-migrated local
database. The verifier is read-only. See [notification operations](docs/NOTIFICATIONS.md)
for event/channel mapping, recipient rules, delivery limitations, and the
Admin-only test utility.

## Customer-confirmed delivery (pending Migration 004)

`db/migrations/004_order_delivery_confirmation.sql` is prepared but **has not
been applied**. The new `ready_shipped` and `delivered` lifecycle and email
events require this migration before the updated application can run against
the local database. Review and back up `retailmetrics`, stop web writers, and
apply this SQL once through an approved transactional PostgreSQL deployment
process. Do not rerun it: it replaces named constraints, backfills only
application-origin `completed` orders, and increments their `row_version`.
Imported orders and canonical views are untouched. Verify the new columns,
constraints, statuses, outbox event/channel rules, and unchanged canonical
counts before starting the updated web app. No migration was executed while
implementing this feature.

## Audit Trail (Migration 005 pending)

The Admin-only Audit Trail is prepared but disabled by default. Review `db/migrations/005_audit_trail.sql` before applying it; do **not** enable `AUDIT_TRAIL_ENABLED` until the migration has been applied. See `docs/AUDIT_TRAIL.md` for the transaction, privacy, and test gates.
