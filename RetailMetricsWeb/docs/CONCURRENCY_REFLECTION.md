# Concurrency and Distributed-Systems Reflection

## RetailMetrics as a distributed application

RetailMetricsWeb is small enough to run on one classroom computer, but its
architecture still has the essential boundaries of a distributed system. A
user's browser renders a Streamlit interface, Streamlit sends HTTP requests to
a separate FastAPI service, and FastAPI performs authorized transactions in
PostgreSQL. The browser never connects directly to the database. Each boundary
introduces independent state, delay, and possible failure: a browser may hold
an older view, an HTTP request may fail or arrive later than expected, and a
database transaction may conflict with another transaction.

This separation is valuable because responsibility is explicit. Streamlit is a
presentation client. It can hide controls that do not apply to a user's role,
but this is only a usability feature. FastAPI is the security boundary: it
validates the signed access token, reloads the account's current role and
status from PostgreSQL, and checks the required permission for every protected
request. PostgreSQL is responsible for durable state, primary and foreign keys,
uniqueness, and transactional consistency. Consequently, a user cannot bypass
RBAC by manually constructing an HTTP request that the Streamlit interface
would not normally offer.

## Concurrent users and stale state

LAN access allows several users and devices to work with the same data at the
same time. For example, an Administrator and an Operations Staff user may both
open the same application-created order. Each browser initially receives the
same values and the same `row_version`. If the Administrator saves an update,
the database row changes and its version increments. The Operations Staff form
is now stale even though it still looks valid on that user's screen.

RetailMetrics uses optimistic concurrency control for this situation. The
client submits the version it last read with every Update or Delete. FastAPI's
database operation matches both the primary key and that expected version. A
successful update increments `row_version`; if the row has already changed, the
expected version no longer matches and the API returns HTTP `409 Conflict`.
The second user is asked to refresh the data rather than silently overwriting
the first user's work. This is preferable to holding a database lock while a
person reads or edits a browser form, which could block unrelated work for an
unpredictable amount of time.

Optimistic concurrency assumes that conflicts are possible but relatively
infrequent. That assumption fits a classroom CRUD application and ordinary
administrative workflows. It does not automatically merge competing edits;
the user must review the latest record and decide whether to reapply a change.
It also requires every mutation client to preserve the last-read version.
FastAPI remains authoritative, so hiding `row_version` in the polished user
interface does not weaken the check.

## PostgreSQL consistency and business invariants

PostgreSQL complements version checking with transactions and constraints.
Foreign keys prevent orders, line items, refunds, and creator references from
becoming disconnected. The unique index on `orders.website_session_id`
preserves the dataset's one-order-per-session rule even if two requests pass an
earlier application-level check at nearly the same instant. One transaction can
succeed; the competing request is translated into a clear conflict response.
Refund validation also considers the related order-item price so application
rules are checked close to the authoritative data.

Delete behavior is deliberately restrictive. Imported rows are identified by
a null creator and cannot be updated or deleted through the API. For
application-created rows, existing foreign keys prevent deletion of a parent
that still has dependent records. The presenter therefore removes a demo chain
from refund to item to order to product. This behavior demonstrates that CRUD
does not mean unrestricted destruction: referential integrity and the
canonical-data boundary are maintained under concurrent requests.

Authentication state is distributed as well. FastAPI signs expiring tokens,
while each request reloads `role`, `is_active`, lock status, and
`token_version` from the database. Password changes, resets, logout, role
changes, and activation changes increment the version or otherwise invalidate
the session. A previously issued token cannot preserve authority that the
database has revoked. Streamlit's browser-refresh feature stores the raw token
only in server memory and gives the browser an opaque session handle; restoring
a page still requires an authoritative `/auth/me` validation.

## Limitations and appropriate scope

The current deployment is intended for a trusted local network, not the public
Internet. HTTP traffic is not protected by TLS, the Streamlit session registry
is process-local, and sessions do not survive a Streamlit restart or distribute
across multiple frontend workers. The optional classroom password-reset mode
can expose a one-time reset token in the API response because no email service
is configured; it must be disabled outside a controlled demonstration. The
system also has no cross-node cache, message queue, replicated database, or
automated conflict merge.

These limitations do not remove the system's distributed characteristics.
They define a deliberate scope: one PostgreSQL authority on the host, separate
HTTP client and service processes, multiple concurrent LAN users, transactional
constraints, server-side authorization, and explicit conflict detection. A
production extension would add HTTPS, persistent or shared session storage,
an external reset-delivery channel, centralized audit logging, monitoring, and
deployment controls. For the assignment, RetailMetrics demonstrates the core
lesson that concurrency must be handled at the service and database boundaries,
not assumed away by the user interface.
