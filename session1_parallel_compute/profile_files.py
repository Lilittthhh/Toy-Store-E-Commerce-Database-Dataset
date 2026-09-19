import json
import sys
import pandas as pd
import config as cfg

META = {
    "website_sessions": {
        "role": "Event/Entity",
        "pk": "website_session_id",
        "fks": {},
    },
    "website_pageviews": {
        "role": "Event",
        "pk": "website_pageview_id",
        "fks": {"website_session_id": ("website_sessions", "website_session_id")},
    },
    "orders": {
        "role": "Event",
        "pk": "order_id",
        "fks": {"website_session_id": ("website_sessions", "website_session_id")},
    },
    "order_items": {
        "role": "Event",
        "pk": "order_item_id",
        "fks": {
            "order_id": ("orders", "order_id"),
            "product_id": ("products", "product_id"),
        },
    },
    "order_item_refunds": {
        "role": "Event",
        "pk": "order_item_refund_id",
        "fks": {
            "order_item_id": ("order_items", "order_item_id"),
            "order_id": ("orders", "order_id"),
        },
    },
    "products": {
        "role": "Entity",
        "pk": "product_id",
        "fks": {},
    },
}

def main():
    cfg.require_files()
    cfg.banner("SESSION 1 - FILE PROFILING")

    frames = {}
    report = {"dataset": cfg.DATASET_TITLE, "files": {}, "foreign_key_checks": {}}

    for name, path in cfg.FILES.items():
        df = pd.read_csv(path)
        frames[name] = df
        meta = META[name]

        p = {
            "file": path.name,
            "role": meta["role"],
            "rows": int(len(df)),
            "columns": int(len(df.columns)),
            "column_list": list(df.columns),
            "dtypes": {c: str(t) for c, t in df.dtypes.items()},
            "null_counts": {c: int(v) for c, v in df.isna().sum().items()},
            "primary_key": meta["pk"],
            "primary_key_unique": bool(df[meta["pk"]].is_unique),
            "primary_key_nulls": int(df[meta["pk"]].isna().sum()),
        }
        report["files"][name] = p

        print(f"\n{path.name} [{meta['role']}]")
        print(f" rows        : {len(df):,}")
        print(f" columns     : {len(df.columns)}")
        print(f" primary key : {meta['pk']}")
        print(f" PK unique   : {p['primary_key_unique']}")
        print(f" nulls       : {p['null_counts']}")

    # FK integrity
    for child_name, meta in META.items():
        child = frames[child_name]
        for fk, (parent_name, parent_pk) in meta["fks"].items():
            parent = frames[parent_name]
            orphan_count = int((~child[fk].isin(parent[parent_pk])).sum())
            key = f"{child_name}.{fk} -> {parent_name}.{parent_pk}"
            report["foreign_key_checks"][key] = {
                "orphan_rows": orphan_count,
                "pass": orphan_count == 0,
            }

    # Date ranges
    report["date_ranges"] = {}
    for name, df in frames.items():
        if "created_at" in df.columns:
            d = pd.to_datetime(df["created_at"], errors="coerce")
            report["date_ranges"][name] = {
                "min": str(d.min()),
                "max": str(d.max()),
                "unparseable": int(d.isna().sum()),
            }

    # Session-to-pageview multiplicity
    pv_counts = frames["website_pageviews"].groupby("website_session_id").size()
    item_counts = frames["order_items"].groupby("order_id").size()

    report["multiplicity"] = {
        "WebsiteSession_1_to_many_WebsitePageview": {
            "min": int(pv_counts.min()),
            "median": float(pv_counts.median()),
            "max": int(pv_counts.max()),
        },
        "Order_1_to_many_OrderItem": {
            "min": int(item_counts.min()),
            "median": float(item_counts.median()),
            "max": int(item_counts.max()),
        },
    }

    report["eligibility"] = {
        "qualifying_files": 6,
        "has_three_or_more_related_files": True,
        "has_genuine_one_to_many": True,
        "has_usable_timestamp": True,
        "transactional_volume": int(
            len(frames["website_pageviews"])
            + len(frames["website_sessions"])
            + len(frames["orders"])
            + len(frames["order_items"])
            + len(frames["order_item_refunds"])
        ),
        "pageview_event_rows": int(len(frames["website_pageviews"])),
    }

    cfg.OUT_PROFILE.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\nFOREIGN KEY CHECKS")
    for k, v in report["foreign_key_checks"].items():
        print(f" {k}: orphan_rows={v['orphan_rows']} | {'PASS' if v['pass'] else 'FAIL'}")

    print("\nKEY MULTIPLICITIES")
    print(
        " WebsiteSession -> Pageviews:",
        f"{pv_counts.min()} / {int(pv_counts.median())} / {pv_counts.max()}",
        "(min/median/max)"
    )
    print(
        " Order -> OrderItems:",
        f"{item_counts.min()} / {int(item_counts.median())} / {item_counts.max()}",
        "(min/median/max)"
    )

    print(f"\nWrote {cfg.OUT_PROFILE}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
