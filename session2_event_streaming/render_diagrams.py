from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import config as cfg

BLUE = "#2E74B5"
LIGHT = "#D9EAF7"
GREEN = "#E2EFDA"
AMBER = "#FFF2CC"
NAVY = "#1F3864"
ORANGE = "#FCE4D6"
GRAY = "#F2F2F2"

BASE = Path(__file__).resolve().parent
DOCS_DIR = getattr(cfg, "DOCS_DIR", BASE / "docs")
ARCH_DIR = getattr(cfg, "ARCH_DIR", BASE / "architecture")
DOCS_DIR.mkdir(parents=True, exist_ok=True)
ARCH_DIR.mkdir(parents=True, exist_ok=True)

EVENT_MODEL = f"""
digraph EventModel {{
  rankdir=LR;
  bgcolor="white";
  fontname="Helvetica";
  labelloc="t";
  fontsize=17;
  label=<<b>RetailMetrics — Session 2 Event / Topic Model</b><br/>
  <font point-size="11">durable event history, partition affinity, conversion and refund events</font><br/>>;

  node [shape=plaintext fontname="Helvetica"];
  edge [color="{BLUE}" fontname="Helvetica" fontsize=9 penwidth=1.5];

  Source [label=<
    <table border="0" cellborder="1" cellspacing="0" cellpadding="5">
      <tr><td bgcolor="{LIGHT}"><b>Session 1 PostgreSQL Source</b></td></tr>
      <tr><td align="left">website_pageviews</td></tr>
      <tr><td align="left">website_sessions</td></tr>
      <tr><td align="left">orders</td></tr>
      <tr><td align="left">order_item_refunds</td></tr>
    </table>>];

  Pageview [label=<
    <table border="0" cellborder="1" cellspacing="0" cellpadding="5">
      <tr><td bgcolor="{GREEN}"><b>pageview.recorded</b><br/><font point-size="9">event_version = 1</font></td></tr>
      <tr><td align="left">event_id : String «unique»</td></tr>
      <tr><td align="left"><b>website_session_id : Integer «partitionKey»</b></td></tr>
      <tr><td align="left"><b>created_at : Timestamp «eventTime»</b></td></tr>
      <tr><td align="left">website_pageview_id / pageview_url</td></tr>
      <tr><td align="left">utm_source / campaign / content</td></tr>
      <tr><td align="left">is_last_pageview / converted</td></tr>
      <tr><td align="left">order revenue / COGS / gross profit</td></tr>
    </table>>];

  Refund [label=<
    <table border="0" cellborder="1" cellspacing="0" cellpadding="5">
      <tr><td bgcolor="{ORANGE}"><b>refund.recorded</b><br/><font point-size="9">event_version = 1</font></td></tr>
      <tr><td align="left">event_id : String «unique»</td></tr>
      <tr><td align="left"><b>website_session_id : Integer «partitionKey»</b></td></tr>
      <tr><td align="left"><b>created_at : Timestamp «eventTime»</b></td></tr>
      <tr><td align="left">order_item_refund_id / order_id</td></tr>
      <tr><td align="left">refund_amount_usd : Double</td></tr>
    </table>>];

  Topic [label=<
    <table border="0" cellborder="1" cellspacing="0" cellpadding="5">
      <tr><td bgcolor="{AMBER}"><b>{cfg.TOPIC}</b><br/><font point-size="9">durable logical topic</font></td></tr>
      <tr><td align="left"><b>{cfg.NUM_PARTITIONS} logical partitions</b></td></tr>
      <tr><td align="left">routing = website_session_id % {cfg.NUM_PARTITIONS}</td></tr>
      <tr><td align="left">stored in retailmetrics_event_log</td></tr>
      <tr><td align="left">non-destructive retained history</td></tr>
    </table>>];

  Source -> Pageview [label="enrich + event-time sort"];
  Source -> Refund [label="join refund to session"];
  Pageview -> Topic [label="publish"];
  Refund -> Topic [label="publish"];
}}
"""

ARCH = f"""
digraph Architecture {{
  rankdir=LR;
  bgcolor="white";
  fontname="Helvetica";
  labelloc="t";
  fontsize=17;
  label=<<b>RetailMetrics — Session 2 Event Streaming &amp; Messaging Backbone</b><br/>
  <font point-size="11">actual repository components and PostgreSQL durable-log implementation</font><br/>>;

  node [shape=box style="rounded,filled" fontname="Helvetica" fontsize=9];
  edge [color="{BLUE}" fontname="Helvetica" fontsize=8 penwidth=1.5];

  s1 [label="Session 1 handover\nPostgreSQL source tables +\nsession_journey_metrics.parquet" fillcolor="{LIGHT}"];
  handover [label="handover_verify.py\nsource + batch continuity checks" fillcolor="{AMBER}"];
  selfpre [label="self_test.py --pre\nbackbone/config/routing checks" fillcolor="{AMBER}"];
  producer [label="produce_events.py\nenrich • sort • publish --reset" fillcolor="{GREEN}"];
  log [label="retailmetrics_event_log\ntopic: {cfg.TOPIC}\n{cfg.NUM_PARTITIONS} partitions\nkey: website_session_id" fillcolor="{LIGHT}" color="{NAVY}" penwidth=2];
  selfpost [label="self_test.py --post\nordering • replay • retained-log checks" fillcolor="{AMBER}"];

  projector [label="session-metrics-projector\nconsumers.py\nidempotent session projection" fillcolor="{GREEN}"];
  audit [label="conversion-audit-writer\nconsumers.py\nevent_id dedup" fillcolor="{GREEN}"];
  refunds [label="refund-monitor\nconsumers.py\nidempotent refund projection" fillcolor="{GREEN}"];
  offsets [label="consumer offsets\nindependent group progress + lag" fillcolor="{GRAY}"];

  reconcile [label="reconcile.py\nSession 2 stream vs Session 1 batch" fillcolor="{ORANGE}"];
  failure [label="failure_recovery.py\nat-least-once crash + redelivery" fillcolor="{ORANGE}"];
  replay [label="replay_suite.py\nlate join • rewind • catch-up • partial replay" fillcolor="{ORANGE}"];
  monet [label="monetization_snapshot.json\nrevenue • profit • refunds • traffic source" fillcolor="{LIGHT}"];
  s3 [label="Session 3 handoff\ndurable history + projections + reports" fillcolor="{LIGHT}" color="{NAVY}"];

  s1 -> handover;
  handover -> selfpre;
  selfpre -> producer [label="ready"];
  producer -> log [label="publish once"];
  log -> selfpost [label="verify stored events"];
  log -> projector [label="group 1"];
  log -> audit [label="group 2"];
  log -> refunds [label="group 3"];
  projector -> offsets;
  audit -> offsets;
  refunds -> offsets;
  projector -> reconcile [label="stream projection"];
  s1 -> reconcile [label="batch reference"];
  log -> failure [label="retained backlog"];
  log -> replay [label="retained history"];
  replay -> monet;
  reconcile -> s3;
  failure -> s3;
  monet -> s3;
}}
"""

PIPELINE = f"""
digraph Pipeline {{
  rankdir=LR;
  bgcolor="white";
  fontname="Helvetica";
  labelloc="t";
  fontsize=17;
  label=<<b>RetailMetrics — Session 2 Run-Everything Flow</b><br/>
  <font point-size="11">presentation order with valid pre- and post-produce guarantees</font><br/>>;

  node [shape=box style="rounded,filled" fontname="Helvetica" fontsize=10 width=2.0 height=0.8];
  edge [color="{BLUE}" penwidth=1.6];

  pre [label="1. Log self-test\nPRE-PRODUCE\nconfig • routing • readiness" fillcolor="{AMBER}"];
  prod [label="2. Produce\n1,188,124 pageviews +\n1,731 refunds" fillcolor="{GREEN}"];
  post [label="automatic post-produce\nlog guarantees\nordering • replay • retention" fillcolor="{AMBER}"];
  con [label="3. Consume\n3 independent groups\n+ offsets/lag" fillcolor="{GREEN}"];
  rec [label="4. Reconcile\nstream = Session 1 batch" fillcolor="{ORANGE}"];
  fail [label="5. Failure & recovery\nat-least-once + idempotency" fillcolor="{ORANGE}"];
  rep [label="6. Replay\nlate join • rewind • partial" fillcolor="{LIGHT}"];

  pre -> prod -> post -> con -> rec -> fail -> rep;
}}
"""


def render(text: str, output: Path) -> None:
    dot = shutil.which("dot")
    output.parent.mkdir(parents=True, exist_ok=True)
    dot_file = output.with_suffix(".dot")
    dot_file.write_text(text, encoding="utf-8")
    if not dot:
        raise RuntimeError(
            f"Graphviz 'dot' not found. DOT source written to {dot_file}. "
            "Install Graphviz and make sure dot.exe is on PATH."
        )
    subprocess.run([dot, "-Tpng", str(dot_file), "-o", str(output)], check=True)


def main() -> int:
    outputs = [
        (EVENT_MODEL, DOCS_DIR / "event-topic-model-session2.png"),
        (ARCH, ARCH_DIR / "architecture-session2.png"),
        (PIPELINE, DOCS_DIR / "pipeline-flow-session2.png"),
    ]
    try:
        for source, output in outputs:
            render(source, output)
    except Exception as exc:
        print(f"Diagram rendering failed: {exc}")
        return 1

    print("Session 2 diagrams rendered successfully:")
    for _, output in outputs:
        print(f"  - {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
