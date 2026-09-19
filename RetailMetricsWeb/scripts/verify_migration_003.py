"""Read-only cumulative notification migration and canonical baseline verification."""
from __future__ import annotations

import psycopg2

from migration_support import connection_settings, print_postgresql_error


COUNTS = {
    "website_sessions": 472871,
    "website_pageviews": 1188124,
    "canonical_products": 4,
    "canonical_orders": 32313,
    "canonical_order_items": 40025,
    "canonical_order_item_refunds": 1731,
}


def main() -> int:
    settings = connection_settings()
    if settings["dbname"] != "retailmetrics":
        print("FAIL: wrong database")
        return 1
    conn = None
    failed = 0
    try:
        conn = psycopg2.connect(**settings)
        conn.set_session(isolation_level="REPEATABLE READ", readonly=True)
        with conn.cursor() as cur:
            def check(label, okay):
                nonlocal failed
                print(("PASS: " if okay else "FAIL: ") + label)
                failed += not okay

            for relation in ("app_users", "customer_accounts", "refund_requests", "notification_outbox"):
                cur.execute("SELECT to_regclass(%s)", ("public." + relation,))
                check(relation + " exists", cur.fetchone()[0] is not None)
            cur.execute("""SELECT column_name FROM information_schema.columns
                           WHERE table_schema='public' AND table_name='notification_outbox'""")
            actual = {row[0] for row in cur.fetchall()}
            expected = {"notification_id","customer_account_id","order_id","refund_request_id","event_type",
                        "channel","delivery_status","recipient_address","attempt_count","created_at",
                        "last_attempt_at","sent_at","provider_message_id","error_code"}
            check("outbox columns", actual == expected)
            cur.execute("""SELECT conname FROM pg_constraint WHERE conrelid='public.notification_outbox'::regclass""")
            constraints = {row[0] for row in cur.fetchall()}
            for name in ("fk_notification_outbox_customer","fk_notification_outbox_order_owner",
                         "fk_notification_outbox_refund_request","ck_notification_outbox_target",
                         "ck_notification_outbox_channel","ck_notification_outbox_event_channel",
                         "ck_notification_outbox_status","ck_notification_outbox_recipient",
                         "ck_notification_outbox_attempts","ck_notification_outbox_delivery_state"):
                check(name, name in constraints)
            cur.execute("""SELECT indexname FROM pg_indexes WHERE schemaname='public' AND tablename='notification_outbox'""")
            indexes = {row[0] for row in cur.fetchall()}
            for name in ("uq_notification_outbox_order_event_channel","uq_notification_outbox_refund_event_channel"):
                check(name, name in indexes)
            for relation, expected_count in COUNTS.items():
                cur.execute("SELECT count(*) FROM public." + relation)
                check(relation + " canonical count", cur.fetchone()[0] == expected_count)
            cur.execute("SELECT COALESCE(SUM(price_usd),0),COALESCE(SUM(cogs_usd),0) FROM public.canonical_orders")
            gross, cogs = cur.fetchone()
            cur.execute("SELECT COALESCE(SUM(refund_amount_usd),0) FROM public.canonical_order_item_refunds")
            refunds = cur.fetchone()[0]
            check("canonical gross/cogs/profit/refunds/net",
                  (str(gross),str(cogs),str(gross-cogs),str(refunds),str(gross-refunds)) ==
                  ("1938509.75","722370.25","1216139.50","85338.69","1853171.06"))
            cur.execute("""SELECT COUNT(*) FROM public.customer_accounts WHERE
                           email LIKE 'rmitcheckout_%' OR email LIKE 'rmitworkflow_%'
                           OR email LIKE 'rmitrefund_%'""")
            check("notification integration customer fixtures cleaned", cur.fetchone()[0] == 0)
            cur.execute("""SELECT COUNT(*) FROM public.app_users WHERE
                           username LIKE 'rmitcheckout_%' OR username LIKE 'rmitworkflow_%'
                           OR username LIKE 'rmitrefund_%'""")
            check("notification integration staff fixtures cleaned", cur.fetchone()[0] == 0)
        conn.rollback()
    except psycopg2.Error as exc:
        print_postgresql_error(exc)
        return 1
    finally:
        if conn is not None:
            conn.close()
    print("OVERALL: " + ("PASS" if not failed else f"FAIL ({failed})"))
    return int(bool(failed))


if __name__ == "__main__":
    raise SystemExit(main())
