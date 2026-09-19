# Dataset Source and Justification

RetailMetrics uses the **Toy Store E-Commerce Database** dataset published on
[Kaggle](https://www.kaggle.com/datasets/siddharth0935/toy-store-e-commerce-database).
The historical baseline contains six related CSV entities: website sessions,
website pageviews, products, orders, order items, and order-item refunds. Their
primary- and foreign-key relationships form a realistic e-commerce journey from
customer acquisition and browsing through purchase and refund activity.

This dataset is appropriate for the CRUD/RBAC assignment because it is large
enough to demonstrate meaningful filtering, pagination, aggregation, and
multi-table relationships while remaining understandable during a classroom
demonstration. The application demonstrates literal Create, Read, Update, and
Delete through customer Cart Items, while Addresses, simulated Payment Methods,
staff accounts, and customer accounts use deactivation where physical deletion
would be unsafe. Products support authorized Admin management for
application-created records. Orders, Order Items, Refund Requests, and Actual
Refunds use checkout and validated lifecycle workflows because they are
financial or audit records, not disposable CRUD rows. Website sessions and
pageviews are high-volume historical events, so RetailMetrics exposes them as
read-only reference data rather than allowing the web application to rewrite
the imported event history.

RetailMetrics preserves the CSV import as the canonical analytical baseline.
For the four original mutable business tables, `record_origin='imported'`
identifies protected historical rows. Application records use the appropriate
`staff` or `customer` business origin; creator/processor attribution remains a
separate concern. This boundary allows the assignment to demonstrate safe CRUD
and commerce workflows without changing the original evidence used by the
analytical sessions. The added staff and customer identity tables supply
separate authentication domains, one-user-one-role staff RBAC, account status,
lockout, password-reset metadata, and meaningful ownership/actor relationships
without copying or redesigning the source dataset.

At the verified migration baseline, the source contains 472,871 website
sessions, 1,188,124 pageviews, 4 products, 32,313 orders, 40,025 order items,
and 1,731 refunds. The original CSV files remain unchanged; PostgreSQL is the
application database used by FastAPI.
