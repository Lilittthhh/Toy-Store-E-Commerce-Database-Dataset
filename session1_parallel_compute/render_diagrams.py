import shutil
import subprocess
import sys
import config as cfg

BLUE = "#2E74B5"
LIGHT = "#D9EAF7"
GREEN = "#E2EFDA"
AMBER = "#FFF2CC"
NAVY = "#1F3864"

ENTITY = f"""
digraph EntityModel {{
  rankdir=LR;
  bgcolor="white";
  fontname="Helvetica";
  labelloc="t";
  fontsize=17;
  label=<<b>Toy Store E-Commerce — Session 1 Entity Model</b><br/>
  <font point-size="11">customer journey + conversion + revenue</font><br/>>;

  node [shape=plaintext fontname="Helvetica"];
  edge [color="{BLUE}" fontname="Helvetica" fontsize=9 penwidth=1.5];

  Session [label=<
    <table border="0" cellborder="1" cellspacing="0" cellpadding="5">
      <tr><td bgcolor="{LIGHT}"><b>WebsiteSession</b><br/><font point-size="9">Event/Entity · website_sessions.csv</font></td></tr>
      <tr><td align="left"><b>website_session_id : Integer «PK» «partitionKey»</b></td></tr>
      <tr><td align="left">created_at : Timestamp</td></tr>
      <tr><td align="left">user_id : Integer</td></tr>
      <tr><td align="left">utm_source / campaign / content</td></tr>
      <tr><td align="left">device_type : String</td></tr>
    </table>>];

  Pageview [label=<
    <table border="0" cellborder="1" cellspacing="0" cellpadding="5">
      <tr><td bgcolor="{LIGHT}"><b>WebsitePageview</b><br/><font point-size="9">Event · website_pageviews.csv</font></td></tr>
      <tr><td align="left"><b>website_pageview_id : Integer «PK»</b></td></tr>
      <tr><td align="left">created_at : Timestamp <b>«eventTime»</b></td></tr>
      <tr><td align="left">website_session_id : Integer «FK»</td></tr>
      <tr><td align="left">pageview_url : String</td></tr>
    </table>>];

  Order [label=<
    <table border="0" cellborder="1" cellspacing="0" cellpadding="5">
      <tr><td bgcolor="{AMBER}"><b>Order</b><br/><font point-size="9">Event · orders.csv</font></td></tr>
      <tr><td align="left"><b>order_id : Integer «PK»</b></td></tr>
      <tr><td align="left">website_session_id : Integer «FK»</td></tr>
      <tr><td align="left">created_at : Timestamp</td></tr>
      <tr><td align="left">price_usd : Double «revenueMetric»</td></tr>
      <tr><td align="left">cogs_usd : Double</td></tr>
    </table>>];

  Item [label=<
    <table border="0" cellborder="1" cellspacing="0" cellpadding="5">
      <tr><td bgcolor="{GREEN}"><b>OrderItem</b><br/><font point-size="9">Event · order_items.csv</font></td></tr>
      <tr><td align="left"><b>order_item_id : Integer «PK»</b></td></tr>
      <tr><td align="left">order_id : Integer «FK»</td></tr>
      <tr><td align="left">product_id : Integer «FK»</td></tr>
      <tr><td align="left">price_usd / cogs_usd : Double</td></tr>
    </table>>];

  Product [label=<
    <table border="0" cellborder="1" cellspacing="0" cellpadding="5">
      <tr><td bgcolor="#F2F2F2"><b>Product</b><br/><font point-size="9">Entity · products.csv</font></td></tr>
      <tr><td align="left"><b>product_id : Integer «PK»</b></td></tr>
      <tr><td align="left">product_name : String</td></tr>
    </table>>];

  Refund [label=<
    <table border="0" cellborder="1" cellspacing="0" cellpadding="5">
      <tr><td bgcolor="#FCE4D6"><b>OrderItemRefund</b><br/><font point-size="9">Event · order_item_refunds.csv</font></td></tr>
      <tr><td align="left"><b>order_item_refund_id : Integer «PK»</b></td></tr>
      <tr><td align="left">order_item_id : Integer «FK»</td></tr>
      <tr><td align="left">order_id : Integer «FK»</td></tr>
      <tr><td align="left">refund_amount_usd : Double</td></tr>
    </table>>];

  Session -> Pageview [label="1    1..*\\nwebsite_session_id"];
  Session -> Order [label="1    0..1\\nwebsite_session_id"];
  Order -> Item [label="1    1..*\\norder_id"];
  Product -> Item [label="1    0..*\\nproduct_id"];
  Item -> Refund [label="1    0..1\\norder_item_id"];
}}
"""

ARCH = f"""
digraph Architecture {{
  rankdir=LR;
  bgcolor="white";
  fontname="Helvetica";
  labelloc="t";
  fontsize=17;
  label=<<b>Toy Store E-Commerce — Session 1 Parallel-Compute Layer</b><br/>
  <font point-size="11">customer journey, conversion and revenue analytics</font><br/>>;

  node [shape=box style="rounded,filled" fontname="Helvetica" fontsize=9];
  edge [color="{BLUE}"];

  pv [label="website_pageviews.csv\\n1,188,124 events" fillcolor="{LIGHT}"];
  sess [label="website_sessions.csv\\n472,871 sessions" fillcolor="{LIGHT}"];
  ord [label="orders.csv\\n32,313 orders" fillcolor="{AMBER}"];

  profile [label="profile_files.py\\nprofile + PK/FK checks" fillcolor="#FFF2CC"];
  join [label="load_and_join.py\\npageviews -> sessions -> orders\\nrow reconciliation" fillcolor="#FFF2CC"];
  repart [label="repartition({cfg.CHOSEN_PARTITIONS}, 'website_session_id')" fillcolor="#E2EFDA"];
  agg [label="parallel_compute.py\\npageviews · duration · conversion\\nrevenue · gross profit" fillcolor="#E2EFDA"];
  base [label="sequential_baseline.py\\npandas reference" fillcolor="#FCE4D6"];
  valid [label="correctness validation" fillcolor="#FCE4D6"];
  out [label="session_journey_metrics.parquet" fillcolor="{LIGHT}" color="{NAVY}"];
  bench [label="session1_benchmark.csv" fillcolor="{LIGHT}" color="{NAVY}"];

  pv -> profile;
  sess -> profile;
  ord -> profile;
  profile -> join;
  join -> repart;
  repart -> agg;
  join -> base;
  agg -> valid;
  base -> valid;
  valid -> out;
  agg -> bench;
}}
"""

def render(text, output):
    dot = shutil.which("dot")
    dot_file = output.with_suffix(".dot")
    dot_file.write_text(text, encoding="utf-8")
    if not dot:
        raise RuntimeError(f"Graphviz 'dot' not found. DOT source written to {dot_file}")
    subprocess.run([dot, "-Tpng", str(dot_file), "-o", str(output)], check=True)

def main():
    try:
        render(ENTITY, cfg.DOCS_DIR / "entity-model-session1.png")
        render(ARCH, cfg.ARCH_DIR / "architecture-session1.png")
    except Exception as exc:
        print(f"Diagram rendering failed: {exc}")
        return 1

    print(f"Wrote {cfg.DOCS_DIR / 'entity-model-session1.png'}")
    print(f"Wrote {cfg.ARCH_DIR / 'architecture-session1.png'}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
