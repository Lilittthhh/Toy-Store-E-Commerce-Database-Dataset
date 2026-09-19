# RetailMetrics Final CRUD/RBAC Responsibility Matrix

RetailMetrics applies CRUD according to business responsibility. Master and
profile resources use conventional CRUD with deactivation where audit history
must be retained. Commerce transactions use validated lifecycle actions rather
than unrestricted edits or physical deletion. FastAPI authorization remains
authoritative even when the Streamlit UI omits an action.

`app_users` contains staff identities only (`admin`, `operations_staff`, and
`analyst`). Customers authenticate separately through `customer_accounts`.

CRUD is intentionally distributed across the roles that own each business
responsibility. The assignment therefore demonstrates complete CRUD without
giving one staff role unsafe authority over every table. **Cart Items are the
literal full-CRUD example:** a Customer adds an item (Create), views the cart
(Read), changes quantity (Update), and removes the item (Delete).

| Resource | Admin | Operations Staff | Analyst | Customer | Delete / lifecycle meaning |
|---|---|---|---|---|---|
| Staff Users | Create and read; change role/status; unlock | Read/change own password only | Read/change own password only | No access | Deactivate/reactivate; never physical deletion |
| Customer Account Status | Read; activate, deactivate, unlock | Operational customer read only | Deidentified summary only | Register, authenticate, read own security-safe account data | Admin deactivation replaces deletion |
| Customer Profile | Administrative/operational read where supported | Read only operationally necessary information | Deidentified summary only | Create with registration; read/update own profile | No physical-delete workflow |
| Customer Addresses | No normal address-book mutation | No normal address-book mutation | No access | Create/read/update/deactivate own; set own default | Deactivation replaces deletion |
| Payment Methods | No real credentials; order snapshot read only | Safe order snapshot read only | No access | Create/read/update/deactivate own simulated metadata; set own default | Deactivation replaces deletion; no real payment credentials |
| Products | Create/read/update/delete staff-origin products; imported rows protected | Read | Read | Read available storefront products | Generic delete applies only to permitted staff-origin product records |
| Storefront Catalog | Read/configure/update availability | Read only | No direct configuration UI | Read available configuration | Mark unavailable instead of deleting catalog history |
| Cart | No normal customer-cart mutation | No normal customer-cart mutation | No access | Create/read/update/remove own cart items | Item removal is permitted before checkout; conversion closes the cart atomically |
| Orders | Read; validated start-processing/ready-shipped/cancel | Read; validated start-processing/ready-shipped/cancel | Read-only reporting | Create through checkout; read own; cancel own pending order; confirm own ready/shipped delivery | Cancellation replaces deletion; no generic transaction edit/delete in the final UI |
| Order Items | Read as order evidence | Read as order evidence | Read-only reporting | Created by checkout and read through own parent order | No independent manual Create/Update/Delete in the final UI |
| Refund Requests | Read; approve/reject/process | Read; approve/reject/process | No workflow UI; reporting only | Create/read own eligible requests | Reject or process through explicit state transitions |
| Actual Refunds | Read processed refunds | Read processed refunds | Read-only reporting | Read own linked outcome | Exactly one actual refund is created by processing an approved request; no standalone CRUD UI |
| Website Sessions | Read only | Read only | Read only | No direct dataset access | Immutable imported evidence |
| Website Pageviews | Read only | No normal Operations UI | Read only | No direct dataset access | Immutable imported evidence |
| Analytics / Reports | Global system, operational, and analytical read | Operational dashboard/read | Deidentified read-only analytics and reports | No staff analytics access | No mutation |

## Interpretation notes

- **Create:** Customer checkout creates an Order and its Order Items atomically.
  Customers create Refund Requests; authorized staff processing creates Actual
  Refunds. Those are workflow operations, not raw table inserts exposed in the
  normal UI.
- **Read:** Staff visibility follows operational need. Analyst customer output
  excludes email, phone, address, payment metadata, and security state.
- **Update:** Orders and Refund Requests accept only validated state transitions
  with the last-read `row_version`; stale requests return HTTP 409.
- **Delete:** Addresses, simulated payment methods, staff accounts, and customer
  accounts use deactivation where retention matters. Orders are cancelled, not
  physically deleted. Imported records remain read-only.
- **Literal Delete:** Removing a Cart Item physically removes that pre-checkout
  line. This is safe because it is not yet a financial transaction.
- **Soft delete/deactivation:** Staff Users, Customer Accounts, Customer
  Addresses, and simulated Payment Methods retain history by changing active
  state rather than deleting retained identity or ownership records.
- Customer order-item ownership is derived through
  `order_items.order_id -> orders.customer_account_id`.
- `record_origin` is business context. Staff actor attribution remains separate
  in fields such as `created_by_app_user_id`.
- Any retained compatibility endpoints are excluded from the professor-facing
  workflow and normal staff navigation. They cannot be used to mutate protected
  historical or customer-origin transaction records.

## Professor-facing CRUD examples

| CRUD operation | Primary demonstration | Responsible role | Safety interpretation |
|---|---|---|---|
| Create | Add Cart Item | Customer | Owned active cart only |
| Read | View Cart Item | Customer | Own cart only |
| Update | Change Cart Item quantity | Customer | Optimistic concurrency and server validation |
| Delete | Remove Cart Item | Customer | Literal delete before checkout |
| Create/Read/Update/Deactivate | Address or simulated Payment Method | Customer | Deactivation preserves retained history |
| Create/Read/Update/Deactivate | Staff User | Admin | No physical identity deletion |
| Create/Read/Update/Delete | Application-created Product | Admin | Historical Products remain protected |
| Create/Read/Update lifecycle | Order | Customer checkout and authorized staff | No physical transaction deletion |
| Create/Read/Update lifecycle | Refund Request | Customer and authorized staff | Processing creates one read-only Actual Refund |
