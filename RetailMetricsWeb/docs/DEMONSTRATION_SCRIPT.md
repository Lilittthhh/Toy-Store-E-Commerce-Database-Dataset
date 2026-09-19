# RetailMetrics CRUD/RBAC Demonstration Script

## Before presenting

- [ ] Use a trusted Private LAN and keep PostgreSQL bound to loopback only.
- [ ] Start `RUN_WEB.bat`; verify Streamlit, FastAPI `/health`, and the approved
  presentation starting state.
- [ ] Keep all passwords, tokens, reset values, cookies, and `.env` contents out
  of screenshots.

## 1. Customer authentication

- [ ] Register or log in as the presentation Customer.
- [ ] Explain that Customer authentication is separate from staff identities.

## 2. Customer CRUD

- [ ] **Create:** add a clearly labelled presentation address.
- [ ] **Read:** show it in My Account -> Addresses.
- [ ] **Update:** edit a safe field and set it as the default address.
- [ ] **Deactivate:** deactivate it and explain that this safe delete-equivalent preserves
  audit integrity instead of physically deleting retained customer data.
- [ ] Add a simulated Payment Method. Never
  enter a real card number, CVV, account identifier, OTP, or credential.
- [ ] Add a product to the Cart (**Create**) and view it (**Read**).
- [ ] Change its quantity (**Update**), then select **Remove** (**literal Delete**).
- [ ] Add the product again so checkout can be demonstrated.

## 3. Checkout

- [ ] Complete Checkout and show that it atomically creates the Order, Order
  Items, immutable shipping/payment snapshots, and simulated payment.
- [ ] Explain why Order Items are generated automatically and are not manually
  created by staff.

## 4. RBAC and unauthorized refusal

- [ ] In Swagger, authenticate as Analyst and attempt an Admin-only mutation
  such as `POST /products`; capture HTTP **403 Forbidden** without creating data.
- [ ] Optionally demonstrate customer ownership isolation with a
  privacy-preserving refusal for another customer's resource.

## 5. Operations workflow

- [ ] As Operations Staff, locate the Customer's pending Order.
- [ ] Move it **Pending -> Processing -> Ready / Shipped**; as the owning Customer, confirm **Delivered** with **Mark as Received**.
- [ ] Explain that Orders are retained lifecycle records, never physically
  deleted, and cancellation is not described as Delete.

## 6. Refund workflow

- [ ] As Customer, submit an eligible Refund Request for a Ready / Shipped or Delivered item.
- [ ] As Operations Staff or Admin, approve and process it.
- [ ] Show the linked Actual Refund in the read-only Refunds page.
- [ ] Explain that processing creates the Actual Refund exactly once; there is no
  generic Create Refund form.

## 7. Analyst workspace

- [ ] Show Analytics Dashboard, deidentified Customers, read-only Products,
  Orders, Refunds, unified Website Traffic, and Business Reports.
- [ ] Confirm there are no mutation, workflow, account-management, or Project
  Evidence controls.

## 8. Admin oversight

- [ ] Show Admin User Management: create or view a staff account, safely change
  role/status, deactivate/reactivate, and unlock where appropriate.
- [ ] Show Admin product and storefront-catalog management. Imported products
  remain protected; catalog availability is configuration, not a historical-row
  rewrite.
- [ ] Confirm Operations Staff and Analyst do not see User Management; confirm
  Operations sees Storefront Catalog as read-only.
- [ ] Point out that neither Admin nor Operations receives generic Create Order,
  Create Order Item, Update/Delete Order, or standalone Create Refund controls.
- [ ] Open Project Evidence only as Admin if Session 1–3 technical validation is
  part of the allotted presentation.

## 9. Historical-data boundary

- [ ] Show that Historical Products, Orders, Refunds, Sessions, and Pageviews are
  protected reference/analytics data.
- [ ] Contrast them with Customer-created application transactions without
  inventing dataset user IDs or website sessions.
- [ ] Attempt to mutate an imported row through an authenticated direct request
  and capture the protected refusal.

## Optional concurrency evidence

- [ ] Read the same mutable customer address or other appropriate application
  resource in two browser sessions.
- [ ] Update it once, then submit the older `row_version`; show HTTP
  **409 Conflict** and refresh to obtain the current version.

## Closing explanation

> RetailMetrics applies CRUD according to business responsibility. Master and
> profile resources use standard CRUD or deactivation. Transaction records use
> controlled lifecycle actions to preserve audit integrity. Customers create
> orders through checkout, while authorized staff process order and refund
> lifecycles. Orders are cancelled rather than physically deleted.

After rehearsal, use only the documented exact-ID presentation reset procedure.
Never use `TRUNCATE`, broad deletes, or imported records.
