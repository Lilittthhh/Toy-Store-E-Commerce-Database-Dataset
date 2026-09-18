from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from ..config import RESULTS, Settings, settings
from ..experiments.contract import contract_report, verify_generated_modules
from ..experiments.pipeline import Session3Runtime
from .components import ScrollPage, draw_bars, replace_tree
from .transcript import save_transcript


class RetailMetricsSession3GUI(tk.Tk):
    TAB_NAMES = (
        "Pipeline", "Contract", "Payload size", "Latency",
        "Round trips & streaming", "Adapter swap", "Reconciliation", "Console",
    )

    STAGES = (
        "Contract", "Wire format", "Serve", "Payload size", "Unary latency",
        "Round trips", "Streaming", "Adapter swap", "Deadline", "Compose", "Reconcile",
    )

    def __init__(self, cfg: Settings | None = None):
        super().__init__()
        self.cfg = cfg or settings()
        self.title("RetailMetrics — Session 3 Inter-Service Communication")
        self.geometry("1540x920"); self.minsize(1180, 720)
        self.bg = "#f7fafc"; self.surface = "#ffffff"; self.teal = "#0f766e"
        self.teal_dark = "#0b5f59"; self.text = "#0f172a"; self.gray = "#64748b"
        self.border = "#dbe4ee"; self.green = "#477526"; self.orange = "#c65d18"
        self.configure(bg=self.bg)
        self.events: queue.Queue = queue.Queue(); self.runtime = Session3Runtime(self.cfg, self._thread_log)
        self.busy = False; self.stage_rows = {name: {"stage": name, "status": "Not run", "headline": "—"} for name in self.STAGES}
        self._styles(); self._header(); self._tabs(); self._build_pages()
        self.after(100, self._drain_events); self.protocol("WM_DELETE_WINDOW", self._close)

    def _styles(self):
        style = ttk.Style(self)
        try: style.theme_use("clam")
        except tk.TclError: pass
        style.configure("TNotebook", background=self.bg, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(14, 10), font=("Segoe UI", 9), background=self.bg, foreground="#475569")
        style.map("TNotebook.Tab", background=[("selected", self.bg)], foreground=[("selected", self.teal)])
        style.configure("Treeview", font=("Segoe UI", 9), rowheight=27, background=self.surface, fieldbackground=self.surface, foreground=self.text)
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"), background=self.teal, foreground="white", relief="flat")

    def _header(self):
        header = tk.Frame(self, bg=self.surface, height=92); header.pack(fill="x"); header.pack_propagate(False)
        left = tk.Frame(header, bg=self.surface); left.pack(side="left", fill="both", expand=True, padx=24, pady=12)
        tk.Label(left, text="RetailMetrics — Session 3 Inter-Service Communication", bg=self.surface, fg=self.text, font=("Segoe UI", 18, "bold")).pack(anchor="w")
        tk.Label(left, text="MIT 261 Parallel and Distributed Systems  ·  typed contracts  ·  JSON vs protobuf  ·  service communication", bg=self.surface, fg=self.gray, font=("Segoe UI", 9)).pack(anchor="w", pady=(5, 0))
        badge = tk.Label(header, text="●  canonical data · read-only", bg="#ecfdf5", fg="#166534", font=("Segoe UI", 9), padx=12, pady=7)
        badge.pack(side="right", padx=24)
        tk.Frame(self, bg=self.border, height=1).pack(fill="x")

    def _tabs(self):
        self.notebook = ttk.Notebook(self); self.notebook.pack(fill="both", expand=True)
        self.pages = {}
        for name in self.TAB_NAMES:
            page = tk.Frame(self.notebook, bg=self.bg) if name == "Console" else ScrollPage(self.notebook, self.bg)
            self.notebook.add(page, text=name)
            self.pages[name] = page if name == "Console" else page.content

    def _button(self, parent, text, command, primary=False):
        return tk.Button(parent, text=text, command=command, bg=self.teal if primary else self.surface,
                         fg="white" if primary else "#334155", activebackground=self.teal_dark if primary else "#f1f5f9",
                         activeforeground="white" if primary else "#334155", relief="flat", bd=0,
                         padx=13, pady=7, font=("Segoe UI", 8), cursor="hand2",
                         highlightbackground=self.border, highlightthickness=1)

    def _title(self, parent, text, controls=()):
        row = tk.Frame(parent, bg=self.bg); row.pack(fill="x", padx=26, pady=(20, 10))
        tk.Label(row, text=text, bg=self.bg, fg=self.text, font=("Segoe UI", 16, "bold")).pack(side="left")
        for label, command, primary in reversed(controls): self._button(row, label, command, primary).pack(side="right", padx=(7, 0))

    def _tree(self, parent, columns, headings, widths, height=7):
        frame = tk.Frame(parent, bg=self.surface, highlightbackground=self.border, highlightthickness=1)
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=height)
        for column, heading, width in zip(columns, headings, widths): tree.heading(column, text=heading); tree.column(column, width=width, anchor="w")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview); tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True); scroll.pack(side="right", fill="y")
        frame.pack(fill="both", expand=True, padx=26, pady=(0, 14)); return tree

    def _card(self, parent, variable, caption, tint):
        frame = tk.Frame(parent, bg=tint, highlightbackground=self.border, highlightthickness=1)
        tk.Label(frame, textvariable=variable, bg=tint, fg=self.teal, font=("Segoe UI", 20, "bold")).pack(pady=(14, 2))
        tk.Label(frame, text=caption, bg=tint, fg=self.gray, font=("Segoe UI", 8)).pack(pady=(0, 13))
        return frame

    def _build_pages(self):
        self._pipeline_page(); self._contract_page(); self._payload_page(); self._latency_page()
        self._round_page(); self._adapter_page(); self._reconcile_page(); self._console_page()

    def _pipeline_page(self):
        page = self.pages["Pipeline"]
        self._title(page, "Session 3 experiment pipeline", (("Run everything", lambda: self._run("Everything", self.runtime.run_all), True),))
        cards = tk.Frame(page, bg=self.bg); cards.pack(fill="x", padx=26, pady=(0, 14))
        self.contract_card = tk.StringVar(value="Not run"); self.payload_card = tk.StringVar(value="Not run")
        self.calls_card = tk.StringVar(value="Not run"); self.reconcile_card = tk.StringVar(value="Not run")
        for i, args in enumerate(((self.contract_card, "messages / RPC methods", "#e8f7f5"), (self.payload_card, "measured payload result", "#edf6ff"), (self.calls_card, "RPC calls served", "#f4f0ff"), (self.reconcile_card, "Session 1/2 agreement", "#f0fdf4"))):
            card = self._card(cards, *args); card.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 6, 0)); cards.grid_columnconfigure(i, weight=1)
        controls = tk.Frame(page, bg=self.bg); controls.pack(fill="x", padx=26, pady=(0, 12))
        actions = {
            "Contract": self.runtime.run_contract, "Wire format": self.runtime.run_payload,
            "Serve": self.runtime.start_services, "Payload size": self.runtime.run_payload,
            "Unary latency": self.runtime.run_latency, "Round trips": self.runtime.run_roundtrips,
            "Streaming": self.runtime.run_streaming, "Adapter swap": self.runtime.run_adapter_swap,
            "Deadline": self.runtime.run_deadline, "Compose": self.runtime.run_compose,
            "Reconcile": self.runtime.run_reconcile,
        }
        for name in self.STAGES: self._button(controls, name, lambda n=name, fn=actions[name]: self._run(n, fn)).pack(side="left", padx=(0, 5))
        self.pipeline_tree = self._tree(page, ("stage", "status", "headline"), ("Stage", "Status", "Headline result"), (180, 110, 750), 11)
        self._refresh_pipeline()

    def _contract_page(self):
        page = self.pages["Contract"]
        self.contract_status = tk.StringVar(value="Not run")
        self._title(page, "Typed RetailMetrics contract", (("Validate contract", lambda: self._run("Contract", self.runtime.run_contract), True), ("Verify generated modules", self._verify_modules, False)))
        tk.Label(page, textvariable=self.contract_status, bg="#f1f5f9", fg=self.gray, anchor="w", padx=14, pady=10, font=("Segoe UI", 9, "bold")).pack(fill="x", padx=26, pady=(0, 12))
        report = contract_report()
        methods = [{"service": s["name"], **m} for s in report["services"] for m in s["methods"]]
        tree = self._tree(page, ("service", "name", "request", "response", "kind"), ("Service", "Method", "Request", "Response", "Kind"), (180, 190, 190, 200, 130), 8)
        replace_tree(tree, methods, ("service", "name", "request", "response", "kind"))
        fields = [{"message": m["name"], **f} for m in report["messages"] for f in m["fields"]]
        tree = self._tree(page, ("message", "number", "name", "type", "wire_type"), ("Message", "#", "Field", "Type", "Wire type"), (180, 45, 210, 220, 130), 8)
        replace_tree(tree, fields, ("message", "number", "name", "type", "wire_type"))
        source = tk.Text(page, height=18, bg="#0f172a", fg="#dbeafe", insertbackground="white", font=("Consolas", 9), relief="flat", padx=12, pady=10)
        source.insert("1.0", (Path(__file__).parents[1] / "proto" / "retailmetrics.proto").read_text(encoding="utf-8")); source.configure(state="disabled")
        source.pack(fill="both", expand=True, padx=26, pady=(0, 20))

    def _payload_page(self):
        page = self.pages["Payload size"]
        self._title(page, "The same RetailMetrics data, two formats", (("Measure payloads", lambda: self._run("Payload size", self.runtime.run_payload), True),))
        self.payload_note = tk.StringVar(value="Not run — sizes will be measured from compact UTF-8 JSON and real protobuf bytes.")
        tk.Label(page, textvariable=self.payload_note, bg="#f1f5f9", fg=self.gray, anchor="w", padx=14, pady=10).pack(fill="x", padx=26, pady=(0, 12))
        self.payload_chart = tk.Canvas(page, height=260, bg=self.surface, highlightbackground=self.border, highlightthickness=1); self.payload_chart.pack(fill="x", padx=26, pady=(0, 12)); draw_bars(self.payload_chart, [], [])
        self.payload_tree = self._tree(page, ("message", "fields", "json_bytes", "protobuf_bytes", "bytes_saved", "reduction_pct"), ("Message", "Fields", "JSON bytes", "Protobuf bytes", "Saved", "Reduction %"), (180, 70, 120, 130, 100, 110), 9)

    def _latency_page(self):
        page = self.pages["Latency"]
        self._title(page, "One operation, three call paths", (("Run benchmark", lambda: self._run("Unary latency", self.runtime.run_latency), True),))
        tk.Label(page, text="Local observations only: results include this Python implementation and loopback transport. No protocol is assumed to win.", bg="#fff7ed", fg="#9a3412", anchor="w", padx=14, pady=10).pack(fill="x", padx=26, pady=(0, 12))
        self.latency_chart = tk.Canvas(page, height=280, bg=self.surface, highlightbackground=self.border, highlightthickness=1); self.latency_chart.pack(fill="x", padx=26, pady=(0, 12)); draw_bars(self.latency_chart, [], [])
        self.latency_tree = self._tree(page, ("transport", "codec", "calls", "median_ms", "p95_ms", "calls_per_sec", "response_bytes"), ("Transport", "Codec", "Calls", "Median ms", "p95 ms", "Calls/sec", "Payload bytes"), (150, 100, 75, 110, 100, 110, 110), 5)

    def _round_page(self):
        page = self.pages["Round trips & streaming"]
        self._title(page, "Batching, round trips, and first usable result", (("Run streaming", lambda: self._run("Streaming", self.runtime.run_streaming), True), ("Run round trips", lambda: self._run("Round trips", self.runtime.run_roundtrips), False)))
        tk.Label(page, text="Batching reduces socket crossings. Streaming is evaluated by time to first usable message; total completion time is reported separately.", bg="#e8f7f5", fg=self.teal_dark, anchor="w", padx=14, pady=10).pack(fill="x", padx=26, pady=(0, 12))
        self.round_tree = self._tree(page, ("transport", "rows", "batch_ms", "individual_ms", "speedup", "round_trips_saved", "equivalent"), ("Transport", "Rows", "Batch ms", "N calls ms", "Measured speedup", "Trips saved", "Equal"), (140, 70, 110, 110, 130, 100, 80), 4)
        self.stream_tree = self._tree(page, ("transport", "rows", "unary_total_ms", "stream_total_ms", "first_message_ms", "first_result_earlier_x", "equivalent"), ("Transport", "Rows", "Unary total ms", "Stream total ms", "First message ms", "First-result ratio", "Equal"), (140, 80, 130, 130, 130, 130, 80), 4)

    def _adapter_page(self):
        page = self.pages["Adapter swap"]
        self._title(page, "RetailMetrics Analytics Adapter: one interface, two transports", (("Deadline test", lambda: self._run("Deadline", self.runtime.run_deadline), False), ("Compare adapters", lambda: self._run("Adapter swap", self.runtime.run_adapter_swap), True)))
        self.adapter_note = tk.StringVar(value="Not run — both adapters call the same service logic through an unchanged caller.")
        tk.Label(page, textvariable=self.adapter_note, bg="#f1f5f9", fg=self.gray, anchor="w", padx=14, pady=10).pack(fill="x", padx=26, pady=(0, 12))
        cards = tk.Frame(page, bg=self.bg); cards.pack(fill="x", padx=26, pady=(0, 12))
        self.adapter_equal_card = tk.StringVar(value="Not run")
        self.adapter_bytes_card = tk.StringVar(value="Not run")
        self.adapter_callsites_card = tk.StringVar(value="Not run")
        self.adapter_deadline_card = tk.StringVar(value="Not run")
        adapter_cards = (
            (self.adapter_equal_card, "results identical", "#e8f7f5"),
            (self.adapter_bytes_card, "response bytes saved / call", "#edf6ff"),
            (self.adapter_callsites_card, "caller-site changes", "#f4f0ff"),
            (self.adapter_deadline_card, "deadline result", "#f0fdf4"),
        )
        for i, args in enumerate(adapter_cards):
            card = self._card(cards, *args)
            card.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 6, 0))
            cards.grid_columnconfigure(i, weight=1)
        self.adapter_tree = self._tree(page, ("adapter", "calls", "median_ms_per_call", "bytes_received_per_call", "identical_results", "caller_sites_changed"), ("Adapter", "Calls", "Median ms/call", "Response bytes/call", "Identical", "Caller changes"), (170, 80, 140, 160, 100, 120), 5)
        self.deadline_tree = self._tree(page, ("case", "timeout", "status", "elapsed"), ("Deadline case", "Timeout ms", "Status", "Elapsed ms"), (180, 130, 190, 130), 3)

    def _reconcile_page(self):
        page = self.pages["Reconciliation"]
        self._title(page, "Canonical service results against Sessions 1 and 2", (("Reconcile now", lambda: self._run("Reconcile", self.runtime.run_reconcile), True), ("Compose summary", lambda: self._run("Compose", self.runtime.run_compose), False)))
        self.reconcile_note = tk.StringVar(value="Not run — previous-session artifacts are read-only inputs.")
        tk.Label(page, textvariable=self.reconcile_note, bg="#f1f5f9", fg=self.gray, anchor="w", padx=14, pady=10).pack(fill="x", padx=26, pady=(0, 12))
        self.reconcile_tree = self._tree(page, ("compared_against", "session3_records", "reference_records", "max_duration_difference", "max_revenue_difference_cents", "tolerance", "passed"), ("Compared against", "Session 3", "Reference", "Max duration diff", "Revenue diff cents", "Tolerance", "Verdict"), (260, 100, 100, 140, 150, 100, 90), 5)
        tk.Label(page, text="Session 3 Product Performance", bg=self.bg, fg=self.text, font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=26, pady=(5, 7))
        tk.Label(page, text="Session 3 result only — not compared with Sessions 1 or 2.", bg="#fff7ed", fg="#9a3412", anchor="w", padx=14, pady=9).pack(fill="x", padx=26, pady=(0, 10))
        self.product_performance_tree = self._tree(
            page,
            ("product_name", "order_count", "units", "revenue", "cogs", "refunds", "net_revenue"),
            ("Product", "Orders", "Units", "Revenue", "COGS", "Refunds", "Net Revenue"),
            (250, 80, 75, 115, 105, 105, 120),
            5,
        )

    def _console_page(self):
        page = self.pages["Console"]
        row = tk.Frame(page, bg=self.bg); row.pack(fill="x", padx=26, pady=(18, 10))
        tk.Label(row, text="Verbatim output from every stage", bg=self.bg, fg=self.text, font=("Segoe UI", 16, "bold")).pack(side="left")
        self._button(row, "Clear", lambda: self.console.delete("1.0", "end")).pack(side="right")
        self._button(row, "Save transcript", self._save_transcript).pack(side="right", padx=(0, 7))
        self.console = tk.Text(page, bg="#0f172a", fg="#dbeafe", insertbackground="white", font=("Consolas", 9), relief="flat", padx=14, pady=12, wrap="word")
        scroll = ttk.Scrollbar(page, orient="vertical", command=self.console.yview); self.console.configure(yscrollcommand=scroll.set)
        self.console.pack(side="left", fill="both", expand=True, padx=(26, 0), pady=(0, 22)); scroll.pack(side="right", fill="y", padx=(0, 26), pady=(0, 22))

    def _run(self, name, function):
        if self.busy: messagebox.showinfo("Session 3", "Another experiment is already running."); return
        self.busy = True
        if name in self.stage_rows: self.stage_rows[name].update(status="Running", headline="Working…"); self._refresh_pipeline()
        def worker():
            try: self.events.put(("result", name, function()))
            except Exception as exc: self.events.put(("error", name, exc))
        threading.Thread(target=worker, daemon=True).start()

    def _thread_log(self, text): self.events.put(("log", text))

    def _drain_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "log": self._append_console(event[1])
                elif event[0] == "result": self.busy = False; self._apply_result(event[1], event[2])
                elif event[0] == "error":
                    self.busy = False; name, exc = event[1], event[2]
                    if name in self.stage_rows: self.stage_rows[name].update(status="Failed", headline=str(exc))
                    self._append_console(f"ERROR [{name}] {exc}"); self._refresh_pipeline(); messagebox.showerror("Session 3", str(exc))
        except queue.Empty: pass
        self.after(100, self._drain_events)

    def _apply_result(self, name, value):
        if name == "Everything":
            for stage in self.STAGES: self.stage_rows[stage].update(status="Passed", headline="Completed with measured output")
            for key, result in self.runtime.results.items(): self._show_result(key, result)
        else:
            if name in self.stage_rows: self.stage_rows[name].update(status="Passed", headline=self._headline(name, value))
            aliases = {"Contract":"contract", "Wire format":"payload", "Payload size":"payload", "Unary latency":"latency", "Round trips":"roundtrips", "Streaming":"streaming", "Adapter swap":"adapter", "Deadline":"deadline", "Compose":"compose", "Reconcile":"reconciliation"}
            if name in aliases: self._show_result(aliases[name], value)
        self._refresh_pipeline()

    def _headline(self, name, value):
        if name == "Contract": return f"{value['message_count']} messages, {value['method_count']} RPCs"
        if name in {"Wire format", "Payload size"}: return f"{len(value)} message types measured"
        if name == "Serve": return "REST 8100 and gRPC 50051 on loopback"
        if name == "Reconcile": return "PASS" if value["passed"] else "FAIL"
        return "Measured successfully"

    def _show_result(self, key, value):
        if key == "contract":
            self.contract_card.set(f"{value['message_count']} / {value['method_count']}"); self.contract_status.set("PASS — source descriptors and generated modules agree")
        elif key == "payload":
            replace_tree(self.payload_tree, value, ("message","fields","json_bytes","protobuf_bytes","bytes_saved","reduction_pct"))
            draw_bars(self.payload_chart, [v["message"] for v in value], [("JSON bytes", "#2563eb", [v["json_bytes"] for v in value]), ("protobuf bytes", "#0f766e", [v["protobuf_bytes"] for v in value])])
            best = max(value, key=lambda v: v["reduction_pct"]); self.payload_card.set(f"{best['reduction_pct']:.1f}% best"); self.payload_note.set("Measured serialized payload sizes; transport framing is excluded.")
        elif key == "latency":
            replace_tree(self.latency_tree, value, ("transport","codec","calls","median_ms","p95_ms","calls_per_sec","response_bytes"))
            draw_bars(self.latency_chart, [v["transport"] for v in value], [("Median ms", "#0f766e", [v["median_ms"] for v in value])])
        elif key == "roundtrips": replace_tree(self.round_tree, value, ("transport","rows","batch_ms","individual_ms","speedup","round_trips_saved","equivalent"))
        elif key == "streaming": replace_tree(self.stream_tree, value, ("transport","rows","unary_total_ms","stream_total_ms","first_message_ms","first_result_earlier_x","equivalent"))
        elif key == "adapter":
            replace_tree(self.adapter_tree, value, ("adapter","calls","median_ms_per_call","bytes_received_per_call","identical_results","caller_sites_changed")); self.adapter_note.set("Equivalent normalized results through one unchanged caller; latency is local measurement only.")
            self.adapter_equal_card.set("Yes" if value and all(v["identical_results"] for v in value) else "No")
            response_sizes = [int(v["bytes_received_per_call"]) for v in value]
            saved = max(response_sizes) - min(response_sizes) if response_sizes else 0
            self.adapter_bytes_card.set(f"{saved:,} B")
            changes = max((int(v["caller_sites_changed"]) for v in value), default=0)
            self.adapter_callsites_card.set(str(changes))
        elif key == "deadline":
            rows = [{"case":"short", "timeout":value["short_timeout_ms"], "status":value["short_status"], "elapsed":value["short_elapsed_ms"]}, {"case":"generous", "timeout":value["generous_timeout_ms"], "status":value["generous_status"], "elapsed":value["generous_elapsed_ms"]}]
            replace_tree(self.deadline_tree, rows, ("case","timeout","status","elapsed"))
            self.adapter_deadline_card.set(
                "Exceeded → pass"
                if value["short_status"] == "DEADLINE_EXCEEDED" and value["generous_status"] == "SUCCESS"
                else f"{value['short_status']} → {value['generous_status']}"
            )
        elif key == "compose":
            self._show_product_performance(value["product_performance"])
        elif key == "reconciliation":
            replace_tree(self.reconcile_tree, value["comparisons"], ("compared_against","session3_records","reference_records","max_duration_difference","max_revenue_difference_cents","tolerance","passed")); self.reconcile_card.set("PASS" if value["passed"] else "FAIL"); self.reconcile_note.set("PASS — canonical Session 3 metrics agree with valid Session 1 and Session 2 references." if value["passed"] else "FAIL — inspect differences before presenting.")
            if self.runtime.core:
                self._show_product_performance(self.runtime.core.snapshot.product_performance)
        if self.runtime.core: self.calls_card.set(f"{sum(self.runtime.core.call_counts().values()):,}")

    def _show_product_performance(self, products):
        rows = []
        for product in products:
            rows.append({
                "product_name": product["product_name"],
                "order_count": f"{product['order_count']:,}",
                "units": f"{product['units']:,}",
                "revenue": self._usd(product["revenue_cents"]),
                "cogs": self._usd(product["cogs_cents"]),
                "refunds": self._usd(product["refund_cents"]),
                "net_revenue": self._usd(product["net_revenue_cents"]),
            })
        replace_tree(self.product_performance_tree, rows, ("product_name", "order_count", "units", "revenue", "cogs", "refunds", "net_revenue"))

    @staticmethod
    def _usd(cents):
        return f"${int(cents) / 100:,.2f}"

    def _refresh_pipeline(self): replace_tree(self.pipeline_tree, list(self.stage_rows.values()), ("stage","status","headline"))
    def _append_console(self, text): self.console.insert("end", text + "\n"); self.console.see("end")
    def _verify_modules(self):
        try: verify_generated_modules(); self.contract_status.set("PASS — committed protobuf modules import successfully")
        except Exception as exc: self.contract_status.set(f"FAIL — {exc}")
    def _save_transcript(self):
        path = save_transcript(RESULTS, self.console.get("1.0", "end")); messagebox.showinfo("Transcript saved", str(path))
    def _close(self): self.runtime.stop(); self.destroy()


def main():
    RetailMetricsSession3GUI().mainloop()


if __name__ == "__main__": main()
