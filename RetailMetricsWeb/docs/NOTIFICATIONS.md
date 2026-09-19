# Notification operations and safety

RetailMetrics queues notifications only for registered customers and
customer-origin order/refund events. The outbox stores an email or mobile
destination snapshot, **not** a message body, API key, payment credential, or
authentication secret. Email comes from `customer_accounts.email`; SMS comes
only from `customer_profiles.phone` after unambiguous E.164 normalization.
Missing/invalid phone skips SMS without blocking a supported email event.

| Event | Email | SMS |
| --- | --- | --- |
| Order confirmation (invoice) | Yes | Yes |
| Order processing | Yes | Yes |
| Order ready / shipped | Yes | Yes |
| Customer-confirmed delivery | Yes | Yes |
| Order cancelled | Yes | Yes |
| Refund request submitted | No | Yes |
| Refund rejected | Yes | Yes |
| Refund processed (receipt) | Yes | Yes |

The new fulfillment events are `order_ready_shipped` and `order_delivered`.
The old `order_completed` event remains renderable for previously queued outbox
rows, but is no longer emitted by the order workflow. Order-status messages
share a branded HTML card and a plain-text fallback. Migration 004 must be
applied before the new events can be queued in PostgreSQL.

Each successful workflow inserts rows in its own business transaction. Unique
indexes on target/event/channel prevent duplicate enqueue across requests or
processes. Post-commit dispatch claims a pending row as `sending` and commits
that claim before calling a provider. Provider failure marks the row `failed`;
it never rolls back a committed checkout, order transition, or refund. There
is deliberately no automatic retry. If a process stops during an uncertain
external send, the row may remain `sending` and requires investigation before
any future manual retry mechanism is designed. Database enqueue is exactly
once per target/event/channel; external delivery cannot be guaranteed exactly
once when a provider response is lost.

`NOTIFICATION_MODE=mock` is the default and performs **zero network requests**.
It renders the intended HTML/SMS message and returns a simulated success.
The mock provider exposes its messages in memory for focused tests. The
customer UI reports notification status separately from the primary business
success. The Admin-only **Notification Test** page and
`POST /admin/notifications/test` require an explicit action; Operations Staff,
Analyst, and Customer tokens cannot use the endpoint.

Customer and staff password-recovery requests use their existing independent
token stores and validators. For a matching active account, the temporary code
is placed in a branded email and handed to the configured email provider only
after the token hash commits. The public response is identical for known and
unknown addresses. Raw reset codes can appear in an API/browser response only
when both `NOTIFICATION_MODE=mock` and the default-off
`AUTH_EXPOSE_RESET_TOKEN=true` development flag are set; live mode always
suppresses them.

Email and SMS transports are selected independently. For an intentional Gmail
SMTP email run, set `NOTIFICATION_MODE=live`, `EMAIL_PROVIDER=smtp`, the
`SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`,
`SMTP_FROM_EMAIL`, and `SMTP_FROM_NAME` values in the ignored local `.env`,
then set `SMTP_LIVE_SEND_ENABLED=true`. Gmail commonly requires an app
password rather than the normal account password. The Admin test endpoint
requires `confirm_live=true` for each live email send.

Transactional SMS uses Brevo. Configure `SMS_PROVIDER=brevo`, `BREVO_API_KEY`,
and `BREVO_SMS_SENDER` in the ignored local `.env`. A real SMS requires both
`NOTIFICATION_MODE=live` and `BREVO_SMS_LIVE_SEND_ENABLED=true`; otherwise SMS
is simulated, independently of Gmail SMTP. Only Philippine mobile numbers in
`09...`, `639...`, or `+639...` format are accepted and sent as `+639...`.
Before enabling live delivery, confirm the sender is approved by Brevo;
its documented alphanumeric sender limit is 11 characters, so the suggested
`RetailMetrics` label may need a shorter approved equivalent.
Automated tests force all live gates off and use in-memory HTTP transports.

The Admin test action is intentionally outside the business outbox because it
is not a business event. No destination or provider response is displayed in
the normal customer status projection; raw provider failures are not returned
to customers. A live operations run should use restricted access to the
database and logs, and should not print recipient snapshots or secrets.
