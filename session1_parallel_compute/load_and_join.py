import sys
import time
import pandas as pd
import config as cfg

def load_tables():
    cfg.require_files()

    sessions = pd.read_csv(cfg.FILES["website_sessions"])
    pageviews = pd.read_csv(cfg.FILES["website_pageviews"])
    orders = pd.read_csv(cfg.FILES["orders"])

    sessions["created_at"] = pd.to_datetime(sessions["created_at"], errors="raise")
    pageviews["created_at"] = pd.to_datetime(pageviews["created_at"], errors="raise")
    orders["created_at"] = pd.to_datetime(orders["created_at"], errors="raise")

    sessions = sessions.rename(columns={"created_at": "session_created_at"})
    pageviews = pageviews.rename(columns={"created_at": "pageview_created_at"})
    orders = orders.rename(columns={
        "created_at": "order_created_at",
        "price_usd": "order_revenue_usd",
        "cogs_usd": "order_cogs_usd",
    })

    return sessions, pageviews, orders

def build_working_dataset(verbose=True, write=True):
    t0 = time.perf_counter()
    sessions, pageviews, orders = load_tables()

    before = len(pageviews)

    # Pageview -> Session is many-to-one and must preserve pageview rows.
    working = pageviews.merge(
        sessions,
        on="website_session_id",
        how="inner",
        validate="many_to_one",
    )
    after_sessions = len(working)

    # Each converting session has at most one order in this dataset.
    # Left join preserves non-converting pageview events as well.
    order_cols = [
        "order_id", "order_created_at", "website_session_id", "user_id",
        "primary_product_id", "items_purchased",
        "order_revenue_usd", "order_cogs_usd",
    ]
    working = working.merge(
        orders[order_cols],
        on="website_session_id",
        how="left",
        validate="many_to_one",
        suffixes=("", "_order"),
    )
    after_orders = len(working)

    assert after_sessions == before
    assert after_orders == before

    # Derived fields are safe at pageview level because session aggregation uses max()
    # for order values, preventing repeated revenue across pageviews.
    working["converted"] = working["order_id"].notna().astype("int8")
    working["gross_profit_usd"] = (
        working["order_revenue_usd"] - working["order_cogs_usd"]
    )

    elapsed = time.perf_counter() - t0

    report = {
        "rows_before": int(before),
        "rows_after_session_join": int(after_sessions),
        "rows_after_order_join": int(after_orders),
        "row_difference": int(after_orders - before),
        "join_seconds": elapsed,
        "join_path": (
            "website_pageviews -> website_sessions on website_session_id "
            "-> orders on website_session_id (left)"
        ),
    }

    if write:
        working.to_parquet(cfg.OUT_JOINED, index=False)

    if verbose:
        cfg.banner("SESSION 1 - LOAD AND JOIN")
        print("Join path:")
        print(" website_pageviews.csv")
        print("   -> website_sessions.csv on website_session_id (many-to-one)")
        print("   -> orders.csv on website_session_id (left, many-to-one)")
        print()
        print(f"Rows before join       : {before:,}")
        print(f"After sessions join    : {after_sessions:,}")
        print(f"After orders join      : {after_orders:,}")
        print(f"Difference             : {after_orders - before:,}")
        print(f"Join/reconcile time    : {elapsed:.4f} s")
        if write:
            print(f"\nWrote {cfg.OUT_JOINED}")

    return working, report

def main():
    build_working_dataset()
    return 0

if __name__ == "__main__":
    sys.exit(main())
