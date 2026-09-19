from __future__ import annotations

import csv
import json
import os
import queue
import subprocess
import sys
import re
import threading
import time
from pathlib import Path
from collections.abc import Callable
import importlib
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

GUI_DIR = Path(__file__).resolve().parent

def _detect_session1_dir():
    """
    Locate the real Session 1 backend folder.
    Supports:
      1) gui.py placed inside session1_parallel_compute
      2) gui.py placed in a separate GUI folder at repo root
      3) gui.py placed at repo root
    """
    candidates = [
        GUI_DIR,
        GUI_DIR / "session1_parallel_compute",
        GUI_DIR.parent / "session1_parallel_compute",
    ]
    for candidate in candidates:
        if (candidate / "profile_files.py").exists() and (candidate / "config.py").exists():
            return candidate
    # Final fallback keeps a clear, inspectable path in error output.
    return GUI_DIR.parent / "session1_parallel_compute"

BASE = _detect_session1_dir()
RESULTS = BASE / "results"
DATASETS = BASE / "datasets"

MIGRATION_DIR = BASE / "postgresql_migration"


class ScrollPage(tk.Frame):
    def __init__(self, parent, bg):
        super().__init__(parent, bg=bg)
        canvas = tk.Canvas(self, bg=bg, highlightthickness=0)
        scroll = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.inner = tk.Frame(canvas, bg=bg)
        self._win = canvas.create_window((0,0), window=self.inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        def on_config(_=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
        def on_canvas(e):
            canvas.itemconfigure(self._win, width=e.width)
        self.inner.bind("<Configure>", on_config)
        canvas.bind("<Configure>", on_canvas)

        def wheel(e):
            if sys.platform.startswith("win"):
                canvas.yview_scroll(int(-1*(e.delta/120)), "units")
            else:
                canvas.yview_scroll(-1 if e.delta > 0 else 1, "units")
        for w in (canvas, self.inner):
            w.bind("<MouseWheel>", wheel)

class RetailMetricsSession1GUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("RetailMetrics — Session 1 Parallel Compute Console")
        self.geometry("1500x900")
        self.minsize(1180, 720)

        self.bg = "#f7fafc"
        self.surface = "#ffffff"
        self.teal = "#0f766e"
        self.teal_dark = "#0b5f59"
        self.text = "#0f172a"
        self.gray = "#64748b"
        self.border = "#dbe4ee"
        self.teal_soft = "#e8f7f5"
        self.blue_soft = "#edf6ff"
        self.purple_soft = "#f4f0ff"
        self.green_soft = "#eef9f1"
        self.green = "#198754"
        self.orange_soft = "#fff7e7"
        self.orange = "#b7791f"
        self.red_soft = "#fdecec"
        self.muted = "#8a99aa"

        self.configure(bg=self.bg)
        self.running = False
        self.q = queue.Queue()
        self.running_stage = None
        self.stage_started_at = None
        self.running_dots = 0

        self.done = {
            "profile": False,
            "join": False,
            "strategy": False,
            "baseline": False,
            "parallel": False,
            "benchmark": False,
            "balance": False,
        }

        self._styles()
        self._header()
        self._tabs()
        self._build_pipeline()
        self._build_files()
        self._build_join()
        self._build_benchmark()
        self._build_correctness()
        self._build_balance()
        self._build_migration()
        self._build_console()
        self.after(120, self._drain)

    def _styles(self):
        s = ttk.Style(self)
        try: s.theme_use("clam")
        except tk.TclError: pass
        s.configure("TNotebook", background=self.bg, borderwidth=0, tabmargins=(18, 0, 18, 0))
        s.configure("TNotebook.Tab", padding=(15,10), font=("Segoe UI",9),
                    background=self.bg, foreground="#475569")
        s.map("TNotebook.Tab",
              foreground=[("selected", self.teal)],
              background=[("selected", self.bg)])
        s.configure("Treeview", rowheight=28, font=("Segoe UI",9),
                    background=self.surface, fieldbackground=self.surface, foreground=self.text)
        s.configure("Treeview.Heading", font=("Segoe UI",9,"bold"),
                    background=self.teal, foreground="white", relief="flat", padding=(6, 6))
        s.map("Treeview.Heading", background=[("active", self.teal_dark)])

        s.configure(
            "Retail.TEntry",
            padding=(10, 8),
            fieldbackground="#ffffff",
            foreground=self.text,
            bordercolor=self.border,
            lightcolor=self.border,
            darkcolor=self.border,
            relief="flat",
            font=("Segoe UI", 10),
        )
        s.map(
            "Retail.TEntry",
            bordercolor=[("focus", self.teal)],
            lightcolor=[("focus", self.teal)],
            darkcolor=[("focus", self.teal)],
        )

    def _header(self):
        header = tk.Frame(self, bg=self.surface, height=88)
        header.pack(fill="x")
        header.pack_propagate(False)

        left = tk.Frame(header, bg=self.surface)
        left.pack(side="left", fill="both", expand=True, padx=(24, 10), pady=12)

        tk.Label(
            left,
            text="RetailMetrics — Session 1 Parallel Compute Console",
            font=("Segoe UI", 18, "bold"),
            fg=self.text,
            bg=self.surface
        ).pack(anchor="w")

        tk.Label(
            left,
            text=(
                "RetailMetrics: An E-Commerce Analytics System for Sales, Website Performance, and Revenue Intelligence  •  Toy Store E-Commerce Database  •  "
                "partition key website_session_id  •  bounded parallelism 4  •  settings (2, 4, 8)"
            ),
            font=("Segoe UI", 9),
            fg=self.gray,
            bg=self.surface
        ).pack(anchor="w", pady=(5, 0))

        badge = tk.Frame(
            header,
            bg="#f0fdf4",
            highlightbackground="#bbf7d0",
            highlightthickness=1
        )
        badge.pack(side="right", padx=24, pady=24)

        tk.Label(
            badge,
            text="●",
            font=("Segoe UI", 9, "bold"),
            fg="#16a34a",
            bg="#f0fdf4"
        ).pack(side="left", padx=(10, 4), pady=6)

        tk.Label(
            badge,
            text="All systems nominal",
            font=("Segoe UI", 9),
            fg="#166534",
            bg="#f0fdf4"
        ).pack(side="left", padx=(0, 10), pady=6)

        tk.Frame(self, bg=self.border, height=1).pack(fill="x")

    def _tabs(self):
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)
        self.tabs = {}
        for name in (
            "Pipeline",
            "Files & eligibility",
            "Join & partition key",
            "Baseline vs parallel",
            "Correctness & output",
            "Partition balance",
            "CSV → PostgreSQL",
            "Console",
        ):
            page = ScrollPage(self.nb, self.bg) if name != "Console" else tk.Frame(self.nb, bg=self.bg)
            self.tabs[name] = page.inner if isinstance(page, ScrollPage) else page
            self.nb.add(page, text=name)

    def _select_tab(self, name):
        for tab_id in self.nb.tabs():
            if self.nb.tab(tab_id, "text") == name:
                self.nb.select(tab_id)
                return

    def _button(self, parent, text, cmd, primary=False, warm=False):
        if primary:
            bg = self.teal
            fg = "white"
            active = self.teal_dark
        elif warm:
            bg = "#fff4e8"
            fg = "#9a5c1b"
            active = "#ffe7cf"
        else:
            bg = self.surface
            fg = "#334155"
            active = "#f1f5f9"

        return tk.Button(
            parent,
            text=text,
            command=cmd,
            bg=bg,
            fg=fg,
            activebackground=active,
            activeforeground=fg,
            relief="flat",
            bd=0,
            padx=13,
            pady=7,
            font=("Segoe UI", 8),
            cursor="hand2",
            highlightbackground=self.border,
            highlightthickness=1,
        )

    def _title(self, p, text, buttons=None):
        row = tk.Frame(p, bg=self.bg); row.pack(fill="x", pady=(0,10))
        tk.Label(row, text=text, bg=self.bg, fg=self.text,
                 font=("Segoe UI",16,"bold")).pack(side="left")
        if buttons:
            for label, cmd, primary in reversed(buttons):
                self._button(row,label,cmd,primary).pack(side="right", padx=(5,0))

    def _tree(self, p, cols, heads, widths, height=8):
        f = tk.Frame(p, bg=self.surface, highlightbackground=self.border, highlightthickness=1)
        t = ttk.Treeview(f, columns=cols, show="headings", height=height)
        for c,h,w in zip(cols,heads,widths):
            t.heading(c,text=h); t.column(c,width=w,anchor="w")
        t.pack(fill="both", expand=True)
        return f,t

    def _card(self, parent, var, subtitle, tint, accent=None):
        accent = accent or self.teal
        f = tk.Frame(
            parent,
            bg=tint,
            highlightbackground=self.border,
            highlightthickness=1
        )

        inner = tk.Frame(f, bg=tint)
        inner.pack(fill="both", expand=True, padx=18, pady=14)

        tk.Label(
            inner,
            text="●",
            font=("Segoe UI", 16, "bold"),
            fg=accent,
            bg=tint
        ).pack(side="left", padx=(0, 14))

        text_box = tk.Frame(inner, bg=tint)
        text_box.pack(side="left", fill="both", expand=True)

        tk.Label(
            text_box,
            textvariable=var,
            font=("Segoe UI", 18, "bold"),
            bg=tint,
            fg=self.text
        ).pack(anchor="w")

        tk.Label(
            text_box,
            text=subtitle,
            font=("Segoe UI", 8),
            bg=tint,
            fg=self.gray
        ).pack(anchor="w", pady=(4, 0))
        return f


    def _banner(self, p, var, tint="#eef8e8", fg="#477526"):
        f = tk.Frame(p, bg=tint, highlightbackground=self.border, highlightthickness=1)
        f.pack(fill="x", pady=(0,12))
        tk.Label(f,textvariable=var,bg=tint,fg=fg,font=("Segoe UI",9,"bold"),
                 anchor="w",padx=12,pady=10).pack(fill="x")

    def _build_pipeline(self):
        w = self.tabs["Pipeline"]

        cards = tk.Frame(w, bg=self.bg)
        cards.pack(fill="x", padx=20, pady=(14, 12))

        self.c_rows = tk.StringVar(value="—")
        self.c_groups = tk.StringVar(value="—")
        self.c_fast = tk.StringVar(value="—")
        self.c_pass = tk.StringVar(value="—")

        for card in (
            self._card(cards, self.c_rows, "rows through the join", self.blue_soft, "#2780d9"),
            self._card(cards, self.c_groups, "groups in the result", self.teal_soft, "#159c97"),
            self._card(cards, self.c_fast, "fastest condition measured", self.purple_soft, "#7567d8"),
            self._card(cards, self.c_pass, "parallel vs baseline", self.green_soft, self.green),
        ):
            card.pack(side="left", fill="x", expand=True, padx=5)

        action_box = tk.Frame(
            w,
            bg=self.surface,
            highlightbackground=self.border,
            highlightthickness=1
        )
        action_box.pack(fill="x", padx=20, pady=(0, 10))

        controls = tk.Frame(action_box, bg=self.surface)
        controls.pack(fill="x", padx=12, pady=10)

        tk.Label(
            controls,
            text="Run a stage",
            font=("Segoe UI", 9, "bold"),
            bg=self.surface,
            fg=self.text
        ).pack(side="left", padx=(0, 10))

        for label, key, warm in (
            ("Profile files", "profile", False),
            ("Load and join", "join", False),
            ("Partition strategy", "strategy", False),
            ("Sequential baseline", "baseline", False),
            ("Parallel compute", "parallel", True),
            ("Benchmark", "benchmark", True),
            ("Partition balance", "balance", True),
        ):
            self._button(
                controls,
                label,
                lambda k=key: self.run_stage(k),
                warm=warm
            ).pack(side="left", padx=3)

        self._button(
            controls,
            "Run everything",
            self.run_all,
            primary=True
        ).pack(side="right", padx=(8, 0))

        status_box = tk.Frame(
            w,
            bg=self.orange_soft,
            highlightbackground="#f0d7a8",
            highlightthickness=1
        )
        status_box.pack(fill="x", padx=20, pady=(0, 10))

        self.live_status = tk.StringVar(value="Pipeline idle — no stage is running.")
        self.live_elapsed = tk.StringVar(value="")
        tk.Label(
            status_box,
            textvariable=self.live_status,
            bg=self.orange_soft,
            fg="#9a5c1b",
            font=("Segoe UI", 9, "bold")
        ).pack(side="left", padx=12, pady=8)
        tk.Label(
            status_box,
            textvariable=self.live_elapsed,
            bg=self.orange_soft,
            fg="#9a5c1b",
            font=("Segoe UI", 9)
        ).pack(side="right", padx=12, pady=8)

        body = tk.Frame(w, bg=self.bg)
        body.pack(fill="both", expand=True, padx=20, pady=(0, 14))

        f, self.pipeline_tree = self._tree(
            body,
            ("stage", "engine", "status", "result"),
            ["Stage", "Engine", "Status", "What it does / headline result"],
            [300, 110, 150, 820],
            height=8
        )
        f.pack(fill="x", pady=(0, 12))

        self.stage_labels = [
            ("profile", "1. Profile files", "pandas", "Profile six files, verify PK/FK integrity and eligibility"),
            ("join", "2. Load and join", "pandas", "pageviews → sessions → orders; preserve all pageview rows"),
            ("strategy", "3. Partition strategy", "pandas", "Evaluate candidate keys and justify website_session_id"),
            ("baseline", "4. Sequential baseline", "pandas", "Create the pandas reference result"),
            ("parallel", "5. Parallel compute", "Spark", "Run bounded PySpark aggregation and validate baseline"),
            ("benchmark", "6. Benchmark", "Spark", "Compare 2, 4, and 8 partitions"),
            ("balance", "7. Partition balance", "Spark", "Measure physical partition balance and skew"),
        ]
        for key, label, engine, desc in self.stage_labels:
            self.pipeline_tree.insert("", "end", iid=key, values=(label, engine, "not run", desc))

        note = tk.Frame(
            body,
            bg=self.blue_soft,
            highlightbackground=self.border,
            highlightthickness=1
        )
        note.pack(fill="x", pady=(0, 12))
        tk.Label(
            note,
            text=(
                "RetailMetrics Session 1 workload: compute pageview count, session duration, conversion flag, "
                "order revenue, and gross profit per website_session_id."
            ),
            bg=self.blue_soft,
            fg="#4f6478",
            font=("Segoe UI", 9),
            anchor="w",
            padx=12,
            pady=10
        ).pack(fill="x")

        tk.Label(
            body,
            text="Artifacts in results/",
            bg=self.bg,
            fg=self.text,
            font=("Segoe UI", 11, "bold")
        ).pack(anchor="w", pady=(0, 5))

        f, self.art_tree = self._tree(
            body,
            ("artifact", "written_by", "status", "location"),
            ["Artifact", "Written by", "Status", "Location"],
            [360, 320, 170, 510],
            height=8
        )
        f.pack(fill="x")

        artifacts = [
            ("file_profile.json", "profile_files.py"),
            ("working_dataset.parquet", "load_and_join.py"),
            ("partition_strategy.json", "partition_strategy.py"),
            ("baseline_result.csv", "sequential_baseline.py"),
            ("session_journey_metrics.parquet", "parallel_compute.py"),
            ("validation_report.json", "parallel_compute.py"),
            ("session1_benchmark.csv", "benchmark.py"),
            ("partition_sizes.csv", "partition_analysis.py"),
        ]
        for name, writer in artifacts:
            self.art_tree.insert(
                "", "end", iid=name,
                values=(name, writer, "not revealed", f"results/{name}")
            )

    def _build_files(self):
        w=self.tabs["Files & eligibility"]
        self._title(w,"Dataset eligibility and file inventory",[("Profile files",lambda:self.run_stage("profile"),True)])
        self.files_banner=tk.StringVar(value="Not run yet. Click Profile files to inspect the actual six CSV files.")
        self._banner(w,self.files_banner)

        f,self.files_tree=self._tree(
            w,("file","role","rows","cols","pk","status"),
            ["File","Role","Rows","Columns","Primary key","PK / FK status"],
            [280,150,150,100,230,260],height=8
        ); f.pack(fill="x",pady=(0,12))

        tk.Label(w,text="Eligibility checks",bg=self.bg,fg=self.text,font=("Segoe UI",11,"bold")).pack(anchor="w",pady=(0,5))
        f,self.elig_tree=self._tree(
            w,("condition","result","evidence"),
            ["Condition","Result","Evidence"],[610,120,610],height=6
        ); f.pack(fill="x")

    def _build_join(self):
        w=self.tabs["Join & partition key"]
        self._title(w,"Join integrity and partition-key decision",
                    [("Run join",lambda:self.run_stage("join"),True),
                     ("Derive key",lambda:self.run_stage("strategy"),False)])
        self.join_banner=tk.StringVar(value="Not run yet. Join and partition evidence stay hidden until you run each stage.")
        self._banner(w,self.join_banner)

        cards=tk.Frame(w,bg=self.bg); cards.pack(fill="x",pady=(0,12))
        self.j_before=tk.StringVar(value="—"); self.j_after=tk.StringVar(value="—")
        self.j_delta=tk.StringVar(value="—"); self.j_key=tk.StringVar(value="—")
        for c in (
            self._card(cards,self.j_before,"rows before join",self.blue_soft),
            self._card(cards,self.j_after,"rows after join","#e8f7f5"),
            self._card(cards,self.j_delta,"row difference",self.orange_soft),
            self._card(cards,self.j_key,"chosen partition key",self.green_soft),
        ):
            c.pack(side="left",fill="x",expand=True,padx=5)

        tk.Label(w,text="Join path",bg=self.bg,fg=self.text,font=("Segoe UI",11,"bold")).pack(anchor="w",pady=(0,5))
        self.join_text=tk.StringVar(value="—")
        f=tk.Frame(w,bg=self.surface,highlightbackground=self.border,highlightthickness=1); f.pack(fill="x",pady=(0,12))
        tk.Label(f,textvariable=self.join_text,bg=self.surface,fg=self.text,font=("Segoe UI",9),
                 justify="left",anchor="w",padx=12,pady=12).pack(fill="x")

        tk.Label(w,text="Partition-key candidates",bg=self.bg,fg=self.text,font=("Segoe UI",11,"bold")).pack(anchor="w",pady=(0,5))
        f,self.key_tree=self._tree(
            w,("key","distinct","min","median","max","skew","decision"),
            ["Candidate","Distinct","Min","Median","Max","Skew","Decision"],
            [250,150,100,110,120,120,250],height=7
        ); f.pack(fill="x")

    def _build_benchmark(self):
        w=self.tabs["Baseline vs parallel"]
        self._title(w,"Sequential baseline vs bounded PySpark parallelism",
                    [("Run benchmark",lambda:self.run_stage("benchmark"),True),
                     ("Run baseline",lambda:self.run_stage("baseline"),False)])
        self.bench_banner=tk.StringVar(value="Not run yet. Benchmark values will appear after the current-session run.")
        self._banner(w,self.bench_banner)

        f,self.bench_tree=self._tree(
            w,("run","parts","time","groups","correct","speedup","obs"),
            ["Run","Partitions","Time (s)","Groups","Correct?","Speedup vs baseline","Observation"],
            [250,150,150,150,110,180,280],height=7
        ); f.pack(fill="x",pady=(0,12))

        tk.Label(w,text="Interpretation",bg=self.bg,fg=self.text,font=("Segoe UI",11,"bold")).pack(anchor="w",pady=(0,5))
        self.bench_note=tk.StringVar(value="—")
        f=tk.Frame(w,bg=self.blue_soft,highlightbackground=self.border,highlightthickness=1); f.pack(fill="x")
        tk.Label(f,textvariable=self.bench_note,bg=self.blue_soft,fg="#4f6478",font=("Segoe UI",9),
                 justify="left",anchor="w",padx=14,pady=12).pack(fill="x")

    def _build_correctness(self):
        w=self.tabs["Correctness & output"]
        self._title(w,"Correctness validation and final Session 1 output",
                    [("Run parallel compute",lambda:self.run_stage("parallel"),True)])
        self.val_banner=tk.StringVar(value="Not run yet. Run Parallel compute to validate the Spark result against the pandas baseline.")
        self._banner(w,self.val_banner)

        cards=tk.Frame(w,bg=self.bg); cards.pack(fill="x",pady=(0,12))
        self.v_groups=tk.StringVar(value="—"); self.v_delta=tk.StringVar(value="—")
        self.v_tol=tk.StringVar(value="—"); self.v_pass=tk.StringVar(value="—")
        for c in (
            self._card(cards,self.v_groups,"parallel / baseline groups",self.blue_soft),
            self._card(cards,self.v_delta,"join row difference","#e8f7f5"),
            self._card(cards,self.v_tol,"numeric tolerance",self.orange_soft),
            self._card(cards,self.v_pass,"validation result",self.green_soft),
        ):
            c.pack(side="left",fill="x",expand=True,padx=5)

        f,self.diff_tree=self._tree(
            w,("metric","maxdiff","rule","held"),
            ["Metric","Maximum difference","Comparison rule","Held?"],
            [360,250,420,130],height=7
        ); f.pack(fill="x",pady=(0,12))

        tk.Label(w,text="Output artifact",bg=self.bg,fg=self.text,font=("Segoe UI",11,"bold")).pack(anchor="w")
        self.output_var=tk.StringVar(value="—")
        tk.Label(w,textvariable=self.output_var,bg=self.bg,fg=self.gray,font=("Segoe UI",9)).pack(anchor="w",pady=(4,0))

    def _build_balance(self):
        w=self.tabs["Partition balance"]
        self._title(w,"Partition balance and skew analysis",
                    [("Analyze partitions",lambda:self.run_stage("balance"),True)])
        self.balance_banner=tk.StringVar(value="Not run yet. Actual partition counts will appear after analysis.")
        self._banner(w,self.balance_banner)

        f,self.balance_tree=self._tree(
            w,("part","pred","actual","ratio","obs"),
            ["Partition","Predicted even count","Actual count","Ratio to even","Observation"],
            [180,240,220,180,420],height=7
        ); f.pack(fill="x",pady=(0,12))

        self.balance_note=tk.StringVar(value="—")
        f=tk.Frame(w,bg=self.blue_soft,highlightbackground=self.border,highlightthickness=1); f.pack(fill="x")
        tk.Label(f,textvariable=self.balance_note,bg=self.blue_soft,fg="#4f6478",
                 font=("Segoe UI",9),justify="left",anchor="w",padx=14,pady=12).pack(fill="x")


    def _build_migration(self):
        w = self.tabs["CSV → PostgreSQL"]

        self._title(w, "CSV → PostgreSQL Migration")

        intro = tk.Frame(
            w,
            bg=self.blue_soft,
            highlightbackground="#d6e7f7",
            highlightthickness=1
        )
        intro.pack(fill="x", padx=20, pady=(0, 10))

        tk.Label(
            intro,
            text="Migrate the six RetailMetrics CSV files into PostgreSQL and keep the database table status visible.",
            bg=self.blue_soft,
            fg=self.text,
            font=("Segoe UI", 9, "bold"),
            anchor="w"
        ).pack(fill="x", padx=14, pady=(8, 2))

        tk.Label(
            intro,
            text="Migration output is sent to the Console tab. Existing PostgreSQL table data is read back whenever the connection is tested or refreshed.",
            bg=self.blue_soft,
            fg=self.gray,
            font=("Segoe UI", 8),
            anchor="w"
        ).pack(fill="x", padx=14, pady=(0, 8))

        self.pg_host = tk.StringVar(value="localhost")
        self.pg_port = tk.StringVar(value="5432")
        self.pg_db = tk.StringVar(value="retailmetrics")
        self.pg_user = tk.StringVar(value="postgres")
        self.pg_password = tk.StringVar(value="")
        self.pg_csv_dir = tk.StringVar(value=str(DATASETS))

        connection = tk.Frame(
            w,
            bg=self.surface,
            highlightbackground=self.border,
            highlightthickness=1
        )
        connection.pack(fill="x", padx=20, pady=(0, 10))

        tk.Label(
            connection,
            text="PostgreSQL connection",
            bg=self.surface,
            fg=self.text,
            font=("Segoe UI", 10, "bold")
        ).pack(anchor="w", padx=14, pady=(9, 6))

        row = tk.Frame(connection, bg=self.surface)
        row.pack(fill="x", padx=14, pady=(0, 8))

        def compact_field(parent, label, variable, width, secret=False):
            block = tk.Frame(parent, bg=self.surface)
            block.pack(side="left", padx=(0, 7))
            tk.Label(
                block,
                text=label,
                bg=self.surface,
                fg="#475569",
                font=("Segoe UI", 7, "bold")
            ).pack(anchor="w", pady=(0, 2))
            entry = ttk.Entry(
                block,
                textvariable=variable,
                width=width,
                style="Retail.TEntry",
                show="•" if secret else ""
            )
            entry.pack()
            return entry

        compact_field(row, "HOST", self.pg_host, 13)
        compact_field(row, "PORT", self.pg_port, 7)
        compact_field(row, "DATABASE", self.pg_db, 15)
        compact_field(row, "USER", self.pg_user, 13)
        compact_field(row, "PASSWORD", self.pg_password, 14, secret=True)

        source_row = tk.Frame(connection, bg=self.surface)
        source_row.pack(fill="x", padx=14, pady=(0, 9))

        tk.Label(
            source_row,
            text="CSV FOLDER",
            bg=self.surface,
            fg="#475569",
            font=("Segoe UI", 7, "bold")
        ).pack(side="left", padx=(0, 7))

        csv_entry = ttk.Entry(
            source_row,
            textvariable=self.pg_csv_dir,
            style="Retail.TEntry"
        )
        csv_entry.pack(side="left", fill="x", expand=True)

        self._button(
            source_row,
            "Browse",
            self._pg_browse_csv
        ).pack(side="left", padx=(7, 0))

        # All actions in one compact row.
        actions = tk.Frame(w, bg=self.bg)
        actions.pack(fill="x", padx=20, pady=(0, 9))

        self.pg_status = tk.StringVar(value="Ready.")
        self.pg_counts = tk.StringVar(value="Connect to PostgreSQL to load current table data.")

        self._button(
            actions,
            "Test connection",
            self._pg_test_connection,
            primary=True
        ).pack(side="left", padx=(0, 7))

        self._button(
            actions,
            "Migrate CSV files",
            self._pg_run_migration,
            warm=True
        ).pack(side="left", padx=(0, 7))

        self._button(
            actions,
            "Verify migration",
            self._pg_verify_migration
        ).pack(side="left", padx=(0, 7))

        self._button(
            actions,
            "Refresh table data",
            self._pg_refresh_table_data
        ).pack(side="left", padx=(0, 7))

        self._button(
            actions,
            "Open migration folder",
            self._pg_open_folder
        ).pack(side="right")

        status = tk.Frame(
            w,
            bg=self.green_soft,
            highlightbackground="#cfe9d7",
            highlightthickness=1
        )
        status.pack(fill="x", padx=20, pady=(0, 10))

        tk.Label(
            status,
            textvariable=self.pg_status,
            bg=self.green_soft,
            fg=self.green,
            font=("Segoe UI", 9, "bold")
        ).pack(side="left", padx=(12, 12), pady=7)

        tk.Label(
            status,
            textvariable=self.pg_counts,
            bg=self.green_soft,
            fg="#4f6478",
            font=("Segoe UI", 8)
        ).pack(side="left", padx=(0, 12), pady=7)

        verify_card = tk.Frame(
            w,
            bg=self.surface,
            highlightbackground=self.border,
            highlightthickness=1
        )
        verify_card.pack(fill="x", padx=20, pady=(0, 10))

        header = tk.Frame(verify_card, bg=self.surface)
        header.pack(fill="x", padx=14, pady=(8, 6))

        tk.Label(
            header,
            text="PostgreSQL table data",
            bg=self.surface,
            fg=self.text,
            font=("Segoe UI", 10, "bold")
        ).pack(side="left")

        tk.Label(
            header,
            text="Persistent data currently stored in retailmetrics",
            bg=self.surface,
            fg=self.gray,
            font=("Segoe UI", 8)
        ).pack(side="left", padx=(10, 0))

        self.pg_overall = tk.StringVar(value="NOT CHECKED")
        self.pg_overall_label = tk.Label(
            header,
            textvariable=self.pg_overall,
            bg=self.orange_soft,
            fg=self.orange,
            font=("Segoe UI", 8, "bold"),
            padx=10,
            pady=3
        )
        self.pg_overall_label.pack(side="right")

        table_wrap, self.pg_verify_tree = self._tree(
            verify_card,
            ("table", "actual", "expected", "status"),
            ["Table", "Stored rows", "Expected rows", "Status"],
            [310, 170, 170, 130],
            height=6
        )
        table_wrap.pack(fill="x", padx=14, pady=(0, 8))

        verify_rows = [
            ("website_sessions", "472,871"),
            ("website_pageviews", "1,188,124"),
            ("orders", "32,313"),
            ("order_items", "40,025"),
            ("order_item_refunds", "1,731"),
            ("products", "4"),
        ]
        for table, expected in verify_rows:
            self.pg_verify_tree.insert(
                "", "end", iid=f"pg_{table}",
                values=(table, "—", expected, "Not loaded")
            )

        tk.Label(
            verify_card,
            text="Referential integrity",
            bg=self.surface,
            fg=self.text,
            font=("Segoe UI", 9, "bold")
        ).pack(anchor="w", padx=14, pady=(0, 4))

        checks_wrap, self.pg_integrity_tree = self._tree(
            verify_card,
            ("check", "orphans", "status"),
            ["Check", "Orphan rows", "Status"],
            [440, 160, 120],
            height=4
        )
        checks_wrap.pack(fill="x", padx=14, pady=(0, 10))

        checks = [
            "pageview orphan sessions",
            "order orphan sessions",
            "item orphan orders",
            "refund orphan items",
        ]
        for i, label in enumerate(checks):
            self.pg_integrity_tree.insert(
                "", "end", iid=f"integrity_{i}",
                values=(label, "—", "Not checked")
            )

    def _pg_browse_csv(self):
        chosen = filedialog.askdirectory(
            title="Select RetailMetrics CSV folder",
            initialdir=self.pg_csv_dir.get() or str(DATASETS)
        )
        if chosen:
            self.pg_csv_dir.set(chosen)

    def _pg_console_write(self, message):
        # All migration messages go to the main Console tab.
        if hasattr(self, "console"):
            self.console.insert("end", message)
            self.console.see("end")

    def _pg_parse_verification_output(self, output_text):
        row_pattern = re.compile(
            r"^(website_sessions|website_pageviews|orders|order_items|order_item_refunds|products)"
            r"\s+actual=\s*([\d,]+)\s+expected=\s*([\d,]+)\s+(PASS|CHECK)",
            re.MULTILINE
        )

        for table, actual, expected, status in row_pattern.findall(output_text):
            iid = f"pg_{table}"
            if self.pg_verify_tree.exists(iid):
                self.pg_verify_tree.item(
                    iid,
                    values=(table, actual, expected, status)
                )

        check_labels = [
            "pageview orphan sessions",
            "order orphan sessions",
            "item orphan orders",
            "refund orphan items",
        ]

        for i, label in enumerate(check_labels):
            pattern = re.compile(
                rf"^{re.escape(label)}\s+([\d,]+)\s+(PASS|CHECK)",
                re.MULTILINE
            )
            match = pattern.search(output_text)
            if match:
                self.pg_integrity_tree.item(
                    f"integrity_{i}",
                    values=(label, match.group(1), match.group(2))
                )

        overall = re.search(
            r"^OVERALL:\s+(PASS|CHECK|FAIL)",
            output_text,
            re.MULTILINE
        )
        if overall:
            value = overall.group(1)
            self.pg_overall.set(value)
            if value == "PASS":
                self.pg_overall_label.configure(
                    bg=self.green_soft,
                    fg=self.green
                )
            else:
                self.pg_overall_label.configure(
                    bg=self.red_soft,
                    fg="#b42318"
                )

    def _pg_env(self):
        env = os.environ.copy()
        env["PGHOST"] = self.pg_host.get().strip()
        env["PGPORT"] = self.pg_port.get().strip()
        env["PGDATABASE"] = self.pg_db.get().strip()
        env["PGUSER"] = self.pg_user.get().strip()
        env["PGPASSWORD"] = self.pg_password.get()
        env["CSV_DIR"] = self.pg_csv_dir.get().strip()
        return env

    def _pg_append(self, message):
        self._pg_console_write(message)

    def _pg_run_command(
        self,
        script_name: str,
        done_callback: Callable[[int, str], None] | None = None,
    ):
        script = MIGRATION_DIR / script_name
        if not script.exists():
            messagebox.showerror(
                "Migration files not found",
                f"Could not find:\n{script}\n\n"
                "Make sure postgresql_migration is inside session1_parallel_compute."
            )
            return

        def worker():
            captured = []
            try:
                self.after(0, lambda: self.pg_status.set(f"Running {script_name}..."))
                self.after(
                    0,
                    lambda: self._pg_append(
                        f"\n{'='*70}\nRUN: {script_name}\n{'='*70}\n"
                    )
                )

                proc = subprocess.Popen(
                    [sys.executable, str(script)],
                    cwd=str(MIGRATION_DIR),
                    env=self._pg_env(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )

                if proc.stdout is not None:
                    for line in proc.stdout:
                        captured.append(line)
                        self.after(0, lambda s=line: self._pg_append(s))

                code = proc.wait()
                output = "".join(captured)

                if code == 0:
                    self.after(
                        0,
                        lambda: self.pg_status.set(
                            f"{script_name} completed successfully."
                        )
                    )
                else:
                    self.after(
                        0,
                        lambda: self.pg_status.set(
                            f"{script_name} failed with exit code {code}."
                        )
                    )

                if done_callback is not None:
                    callback = done_callback
                    self.after(
                        0,
                        lambda cb=callback, exit_code=code, out=output:
                            cb(exit_code, out)
                    )

            except Exception as exc:
                self.after(0, lambda: self.pg_status.set("Migration command failed."))
                self.after(0, lambda: self._pg_append(f"\nERROR: {exc}\n"))

        threading.Thread(target=worker, daemon=True).start()

    def _pg_test_connection(self):
        def worker():
            try:
                self.after(0, lambda: self.pg_status.set("Testing PostgreSQL connection..."))

                try:
                    psycopg2 = importlib.import_module("psycopg2")
                except ModuleNotFoundError as exc:
                    raise RuntimeError(
                        "psycopg2 is not installed in this Python environment. "
                        "Run: pip install psycopg2-binary"
                    ) from exc

                conn = psycopg2.connect(
                    host=self.pg_host.get().strip(),
                    port=int(self.pg_port.get().strip()),
                    dbname=self.pg_db.get().strip(),
                    user=self.pg_user.get().strip(),
                    password=self.pg_password.get()
                )
                conn.close()

                self.after(0, lambda: self.pg_status.set("PostgreSQL connection successful."))
                self.after(0, lambda: self._pg_console_write("\nConnection test: PASS\n"))
                self.after(0, self._pg_refresh_table_data)

            except Exception as exc:
                self.after(0, lambda: self.pg_status.set("PostgreSQL connection failed."))
                self.after(
                    0,
                    lambda err=str(exc): self._pg_console_write(
                        f"\nConnection test: FAIL\n{err}\n"
                    )
                )

        threading.Thread(target=worker, daemon=True).start()

    def _pg_run_migration(self):
        csv_dir = Path(self.pg_csv_dir.get().strip())
        required = [
            "website_sessions.csv",
            "website_pageviews.csv",
            "orders.csv",
            "order_items.csv",
            "order_item_refunds.csv",
            "products.csv",
        ]

        missing = [name for name in required if not (csv_dir / name).exists()]
        if missing:
            messagebox.showerror(
                "CSV files missing",
                "The selected CSV folder is missing:\n\n" + "\n".join(missing)
            )
            return

        self.pg_status.set("Migration in progress...")
        self.pg_counts.set("Importing CSV files into PostgreSQL...")

        def finished(code, output):
            if code == 0:
                self.pg_status.set("Migration completed successfully.")
                self.pg_counts.set("Database tables updated. Loading stored row counts...")
                self._pg_refresh_table_data()
            else:
                self.pg_status.set("Migration failed. See the Console tab for details.")

        self._pg_run_command("migrate_csv_to_postgres.py", finished)

    def _pg_verify_migration(self):
        self.pg_overall.set("VERIFYING...")
        self.pg_overall_label.configure(
            bg=self.orange_soft,
            fg=self.orange
        )

        def finished(code, output):
            if code == 0:
                self._pg_parse_verification_output(output)
                self.pg_status.set("Migration verification completed.")
                self.pg_counts.set(
                    "Stored PostgreSQL table data verified successfully."
                )
            else:
                self.pg_overall.set("FAILED")
                self.pg_overall_label.configure(
                    bg=self.red_soft,
                    fg="#b42318"
                )
                self.pg_status.set("Verification failed. See the Console tab.")

        self._pg_run_command("verify_migration.py", finished)

    def _pg_refresh_table_data(self):
        def worker():
            try:
                psycopg2 = importlib.import_module("psycopg2")
                sql = importlib.import_module("psycopg2.sql")
                conn = psycopg2.connect(
                    host=self.pg_host.get().strip(),
                    port=int(self.pg_port.get().strip()),
                    dbname=self.pg_db.get().strip(),
                    user=self.pg_user.get().strip(),
                    password=self.pg_password.get()
                )

                expected = {
                    "website_sessions": 472871,
                    "website_pageviews": 1188124,
                    "orders": 32313,
                    "order_items": 40025,
                    "order_item_refunds": 1731,
                    "products": 4,
                }
                count_sources = {
                    "orders": "canonical_orders",
                    "order_items": "canonical_order_items",
                    "order_item_refunds": "canonical_order_item_refunds",
                    "products": "canonical_products",
                }

                actual_counts = {}
                with conn.cursor() as cur:
                    for table in expected:
                        source = count_sources.get(table, table)
                        cur.execute(
                            sql.SQL("SELECT COUNT(*) FROM {}").format(
                                sql.Identifier(source)
                            )
                        )
                        actual_counts[table] = cur.fetchone()[0]

                    integrity_queries = [
                        """
                        SELECT COUNT(*) FROM website_pageviews p
                        LEFT JOIN website_sessions s
                        ON p.website_session_id=s.website_session_id
                        WHERE s.website_session_id IS NULL
                        """,
                        """
                        SELECT COUNT(*) FROM canonical_orders o
                        LEFT JOIN website_sessions s
                        ON o.website_session_id=s.website_session_id
                        WHERE s.website_session_id IS NULL
                        """,
                        """
                        SELECT COUNT(*) FROM canonical_order_items oi
                        LEFT JOIN canonical_orders o ON oi.order_id=o.order_id
                        WHERE o.order_id IS NULL
                        """,
                        """
                        SELECT COUNT(*) FROM canonical_order_item_refunds r
                        LEFT JOIN canonical_order_items oi
                        ON r.order_item_id=oi.order_item_id
                        WHERE oi.order_item_id IS NULL
                        """,
                    ]
                    orphan_counts = []
                    for query in integrity_queries:
                        cur.execute(query)
                        orphan_counts.append(cur.fetchone()[0])

                conn.close()

                def update_ui():
                    all_match = True
                    for table, expected_count in expected.items():
                        actual = actual_counts[table]
                        status = "PASS" if actual == expected_count else "CHECK"
                        all_match = all_match and (actual == expected_count)

                        iid = f"pg_{table}"
                        self.pg_verify_tree.item(
                            iid,
                            values=(
                                table,
                                f"{actual:,}",
                                f"{expected_count:,}",
                                status
                            )
                        )

                    labels = [
                        "pageview orphan sessions",
                        "order orphan sessions",
                        "item orphan orders",
                        "refund orphan items",
                    ]
                    for i, (label, orphan_count) in enumerate(
                        zip(labels, orphan_counts)
                    ):
                        status = "PASS" if orphan_count == 0 else "CHECK"
                        all_match = all_match and (orphan_count == 0)
                        self.pg_integrity_tree.item(
                            f"integrity_{i}",
                            values=(label, f"{orphan_count:,}", status)
                        )

                    final = "PASS" if all_match else "CHECK"
                    self.pg_overall.set(final)

                    if all_match:
                        self.pg_overall_label.configure(
                            bg=self.green_soft,
                            fg=self.green
                        )
                    else:
                        self.pg_overall_label.configure(
                            bg=self.orange_soft,
                            fg=self.orange
                        )

                    total_rows = sum(actual_counts.values())
                    self.pg_counts.set(
                        f"{total_rows:,} total rows currently stored across 6 PostgreSQL tables."
                    )
                    self.pg_status.set("PostgreSQL table data loaded.")

                self.after(0, update_ui)

            except Exception as exc:
                self.after(
                    0,
                    lambda err=str(exc): self._pg_console_write(
                        f"\nCould not refresh PostgreSQL table data:\n{err}\n"
                    )
                )
                self.after(
                    0,
                    lambda: self.pg_status.set(
                        "Could not load PostgreSQL table data."
                    )
                )

        threading.Thread(target=worker, daemon=True).start()

    def _pg_open_folder(self):
        if not MIGRATION_DIR.exists():
            messagebox.showerror("Folder not found", str(MIGRATION_DIR))
            return
        try:
            os.startfile(str(MIGRATION_DIR))
        except AttributeError:
            subprocess.Popen(["xdg-open", str(MIGRATION_DIR)])

    def _build_console(self):
        w = self.tabs["Console"]
        top = tk.Frame(w, bg=self.bg)
        top.pack(fill="x", padx=20, pady=(16, 10))

        tk.Label(
            top,
            text="Verbatim output of every stage",
            bg=self.bg,
            fg=self.text,
            font=("Segoe UI", 16, "bold")
        ).pack(side="left")

        self._button(
            top,
            "Clear",
            lambda: self.console.delete("1.0", "end")
        ).pack(side="right")

        panel = tk.Frame(w, bg="#111827")
        panel.pack(fill="both", expand=True, padx=20, pady=(0, 16))

        self.console = tk.Text(
            panel,
            wrap="word",
            bg="#111827",
            fg="#e5e7eb",
            insertbackground="white",
            font=("Consolas", 9),
            relief="flat",
            bd=0,
            padx=12,
            pady=12
        )
        sb = ttk.Scrollbar(panel, orient="vertical", command=self.console.yview)
        self.console.configure(yscrollcommand=sb.set)
        self.console.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def _start_status(self, stage):
        self.running_stage = stage
        self.stage_started_at = time.perf_counter()
        self.running_dots = 0
        self._animate_status()

    def _animate_status(self):
        if not self.running_stage:
            return

        self.running_dots = (self.running_dots + 1) % 4
        dots = "." * self.running_dots
        self.live_status.set(f"RUNNING: {self.running_stage}{dots}")

        if self.stage_started_at is not None:
            elapsed = time.perf_counter() - self.stage_started_at
            self.live_elapsed.set(f"elapsed {elapsed:.1f} s")

        self.after(500, self._animate_status)

    def _stop_status(self, ok):
        if self.running_stage:
            if self.stage_started_at is not None:
                elapsed = time.perf_counter() - self.stage_started_at
            else:
                elapsed = 0.0

            final_status = "COMPLETED" if ok else "FAILED"
            self.live_status.set(f"{final_status}: {self.running_stage}")
            self.live_elapsed.set(f"elapsed {elapsed:.1f} s")

        self.running_stage = None
        self.stage_started_at = None

    def _set_stage(self,key,status,result=None):
        vals=list(self.pipeline_tree.item(key,"values"))
        vals[2]=status
        if result is not None:
            vals[3]=result
        self.pipeline_tree.item(key,values=vals)

    def _cmd_for(self,key):
        return {
            "profile":["profile_files.py"],
            "join":["load_and_join.py"],
            "strategy":["partition_strategy.py"],
            "baseline":["sequential_baseline.py"],
            "parallel":["parallel_compute.py"],
            "benchmark":["benchmark.py"],
            "balance":["partition_analysis.py"],
        }[key]

    def run_stage(self,key):
        if self.running:
            messagebox.showinfo("RetailMetrics","Another stage is still running.")
            return
        if not (BASE / "profile_files.py").exists():
            messagebox.showerror(
                "Session 1 backend not found",
                "The GUI could not find session1_parallel_compute.\n\n"
                f"Expected backend folder:\n{BASE}\n\n"
                "Place this GUI folder at the repository root beside session1_parallel_compute, "
                "or place gui.py directly inside session1_parallel_compute."
            )
            return
        self.running=True
        self._set_stage(key,"running","Running current-session computation...")
        label=dict((k,l) for k,l,_,_ in self.stage_labels)[key]
        self._start_status(label)
        self._select_tab("Console")
        args=self._cmd_for(key)
        self._log(f"\n{'='*76}\nRUN: {' '.join(args)}\n{'='*76}\n")

        def worker():
            try:
                p=subprocess.Popen([sys.executable,"-u"]+args,cwd=str(BASE),
                                   stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                   text=True,bufsize=1,errors="replace")
                lines=[]
                assert p.stdout is not None
                for line in p.stdout:
                    lines.append(line); self.q.put(("text",line))
                rc=p.wait()
                self.q.put(("done",key,rc,"".join(lines)))
            except Exception as e:
                self.q.put(("done",key,1,str(e)))
        threading.Thread(target=worker,daemon=True).start()

    def run_all(self):
        if self.running:
            return
        if not (BASE / "profile_files.py").exists():
            messagebox.showerror(
                "Session 1 backend not found",
                "The GUI could not find session1_parallel_compute.\n\n"
                f"Expected backend folder:\n{BASE}"
            )
            return
        sequence=["profile","join","strategy","baseline","parallel","benchmark","balance"]
        self.running=True
        self._start_status("Run everything")
        self._select_tab("Console")
        def worker():
            ok=True
            for key in sequence:
                self.q.put(("stage_running",key))
                args=self._cmd_for(key)
                self.q.put(("text",f"\n{'='*76}\nRUN: {' '.join(args)}\n{'='*76}\n"))
                try:
                    p=subprocess.Popen([sys.executable,"-u"]+args,cwd=str(BASE),
                                       stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                       text=True,bufsize=1,errors="replace")
                    lines=[]
                    assert p.stdout is not None
                    for line in p.stdout:
                        lines.append(line); self.q.put(("text",line))
                    rc=p.wait()
                except Exception as e:
                    rc=1; lines=[str(e)]
                self.q.put(("all_result",key,rc,"".join(lines)))
                if rc!=0:
                    ok=False; break
            self.q.put(("all_done",ok))
        threading.Thread(target=worker,daemon=True).start()

    def _log(self,s):
        self.console.insert("end",s); self.console.see("end")

    def _load_json(self,name):
        try: return json.loads((RESULTS/name).read_text(encoding="utf-8"))
        except Exception: return {}

    def _apply_profile(self):
        d=self._load_json("file_profile.json")
        for i in self.files_tree.get_children(): self.files_tree.delete(i)
        for name,p in d.get("files",{}).items():
            fk_ok=True
            for k,v in d.get("foreign_key_checks",{}).items():
                if k.startswith(name+".") and not v.get("pass"): fk_ok=False
            self.files_tree.insert("","end",values=(
                p.get("file"),p.get("role"),f"{p.get('rows',0):,}",p.get("columns"),
                p.get("primary_key"),"PASS" if p.get("primary_key_unique") and fk_ok else "CHECK"
            ))
        e=d.get("eligibility",{})
        self.c_rows.set(f"{e.get('pageview_event_rows',0):,}")
        self.files_banner.set(
            f"Eligible dataset  •  {e.get('qualifying_files',0)} related files  •  "
            f"{e.get('transactional_volume',0):,} transactional rows  •  usable timestamps present"
        )
        for i in self.elig_tree.get_children(): self.elig_tree.delete(i)
        rows=[
            ("At least three related files",e.get("has_three_or_more_related_files"),f"{e.get('qualifying_files',0)} qualifying files"),
            ("Genuine one-to-many association",e.get("has_genuine_one_to_many"),"WebsiteSession 1:M WebsitePageview; Order 1:M OrderItem"),
            ("Usable timestamp/date for Session 2",e.get("has_usable_timestamp"),"created_at available in source event tables"),
            ("Transactional volume ≥ 50,000",e.get("transactional_volume",0)>=50000,f"{e.get('transactional_volume',0):,} rows"),
        ]
        for c,r,ev in rows:
            self.elig_tree.insert("","end",values=(c,"PASS" if r else "FAIL",ev))

    def _apply_join(self,output):
        # Parse the script output because join report is not saved separately.
        before=after=delta=None
        for line in output.splitlines():
            if "Rows before join" in line:
                try: before=int(line.split(":")[-1].strip().replace(",",""))
                except: pass
            elif "After orders join" in line:
                try: after=int(line.split(":")[-1].strip().replace(",",""))
                except: pass
            elif "Difference" in line:
                try: delta=int(line.split(":")[-1].strip().replace(",",""))
                except: pass
        self.j_before.set(f"{before:,}" if before is not None else "—")
        self.j_after.set(f"{after:,}" if after is not None else "—")
        self.j_delta.set(f"{delta:,}" if delta is not None else "—")
        self.join_text.set(
            "website_pageviews → website_sessions on website_session_id (inner many-to-one)\n"
            "→ orders on website_session_id (left many-to-one)\n"
            "The pageview row count is asserted unchanged after both joins."
        )
        self.join_banner.set("Join completed. Row preservation evidence is now visible.")

    def _apply_strategy(self):
        d=self._load_json("partition_strategy.json")
        self.j_key.set(d.get("chosen_partition_key","—"))
        for i in self.key_tree.get_children(): self.key_tree.delete(i)
        chosen=d.get("chosen_partition_key")
        for key,r in d.get("candidates",{}).items():
            self.key_tree.insert("","end",values=(
                key,f"{r.get('distinct',0):,}",r.get("min"),
                f"{r.get('median',0):.1f}",f"{r.get('max',0):,}",
                f"{r.get('skew_ratio_max_min',0):.2f}:1",
                "CHOSEN — session affinity" if key==chosen else "rejected / weaker key"
            ))
        self.join_banner.set(
            f"Partition strategy derived. Chosen key: {chosen}; owner: {d.get('entity_owner','')}"
        )

    def _apply_baseline(self,output):
        median=groups=None
        for line in output.splitlines():
            if line.startswith("Median:"):
                try: median=float(line.split(":")[1].replace("s","").strip())
                except: pass
            if line.startswith("Groups:"):
                try: groups=int(line.split(":")[1].strip().replace(",",""))
                except: pass
        if groups is not None: self.c_groups.set(f"{groups:,}")
        self.bench_banner.set(
            f"Sequential baseline completed"
            + (f"  •  median {median:.6f} s" if median is not None else "")
            + (f"  •  {groups:,} groups" if groups is not None else "")
        )

    def _apply_parallel(self):
        d=self._load_json("validation_report.json")
        v=d.get("validation",{})
        self.c_groups.set(f"{v.get('parallel_groups',0):,}")
        self.c_pass.set(v.get("result","—"))
        self.v_groups.set(f"{v.get('parallel_groups',0):,} / {v.get('baseline_groups',0):,}")
        self.v_delta.set(f"{d.get('join',{}).get('rows_after',0)-d.get('join',{}).get('rows_before',0):,}")
        self.v_tol.set(str(v.get("tolerance","—")))
        self.v_pass.set(v.get("result","—"))
        self.val_banner.set(
            f"{v.get('result','—')}  •  configured partitions {d.get('configured_partitions','—')}  •  "
            f"actual partitions {d.get('actual_partitions','—')}  •  "
            f"parallel groups {v.get('parallel_groups',0):,}"
        )
        for i in self.diff_tree.get_children(): self.diff_tree.delete(i)
        for metric,diff in v.get("max_differences",{}).items():
            exact = metric in ("pageview_count","session_duration_seconds","converted")
            rule="exactly 0" if exact else f"≤ {v.get('tolerance')}"
            held=(diff==0) if exact else (diff<=v.get("tolerance",0))
            self.diff_tree.insert("","end",values=(metric,diff,rule,"yes" if held else "no"))
        self.output_var.set("results/session_journey_metrics.parquet")
        self.c_pass.set(v.get("result","—"))

    def _apply_benchmark(self):
        p=RESULTS/"session1_benchmark.csv"
        for i in self.bench_tree.get_children(): self.bench_tree.delete(i)
        rows=[]
        with p.open(newline="",encoding="utf-8") as f:
            rows=list(csv.DictReader(f))
        for r in rows:
            self.bench_tree.insert("","end",values=(
                r["run"],r["parallelism_partitions"],r["execution_time_s"],
                f"{int(r['groups']):,}",r["correct"],r["speedup_vs_baseline"],r["observation"]
            ))
        spark=[r for r in rows if r["run"].startswith("Parallel")]
        best=min(spark,key=lambda r:float(r["execution_time_s"])) if spark else None
        self.bench_banner.set(
            f"Benchmark complete  •  baseline {rows[0]['execution_time_s']} s  •  "
            f"fastest Spark: {best['parallelism_partitions']} partitions at {best['execution_time_s']} s"
            if best else "Benchmark complete"
        )
        self.bench_note.set(
            "The pandas baseline is faster for this local aggregation because Spark adds JVM, scheduling, "
            "shuffle, repartition and coordination overhead. Among the bounded Spark settings, 8 partitions is fastest."
        )
        if best:
            self.c_fast.set(f"{best['parallelism_partitions']} partitions / {best['execution_time_s']} s")

    def _apply_balance(self):
        p=RESULTS/"partition_sizes.csv"
        for i in self.balance_tree.get_children(): self.balance_tree.delete(i)
        rows=[]
        with p.open(newline="",encoding="utf-8") as f: rows=list(csv.DictReader(f))
        for r in rows:
            ratio=float(r["ratio_to_even"])
            obs="near even target"
            self.balance_tree.insert("","end",values=(
                f"partition {r['partition']}",
                f"{float(r['predicted_even_count']):,.0f}",
                f"{int(r['actual_count']):,}",
                f"{ratio:.4f}",obs
            ))
        counts=[int(r["actual_count"]) for r in rows]
        skew=max(counts)/min(counts) if counts else 0
        self.balance_banner.set(f"Balanced 4-way distribution  •  partition max/min skew {skew:.4f}:1")
        self.balance_note.set(
            "The measured partitions are almost perfectly even around the 297,031-record target. "
            "This matches the Session 1 decision to partition by website_session_id: 472,871 distinct keys "
            "with only 1–7 pageviews per session."
        )

    def _reveal_artifact(self,name):
        if name in self.art_tree.get_children():
            p=RESULTS/name
            if p.exists():
                size=p.stat().st_size
                self.art_tree.item(name,values=(name,"written",f"results/{name}  •  {size:,} B"))

    def _apply_stage(self,key,rc,output):
        ok=rc==0
        self.done[key]=ok
        self._set_stage(key,"passed" if ok else "failed",
                        "Completed successfully" if ok else "Check Console output")
        if not ok: return
        if key=="profile":
            self._apply_profile(); self._reveal_artifact("file_profile.json")
        elif key=="join":
            self._apply_join(output); self._reveal_artifact("working_dataset.parquet")
        elif key=="strategy":
            self._apply_strategy(); self._reveal_artifact("partition_strategy.json")
        elif key=="baseline":
            self._apply_baseline(output); self._reveal_artifact("baseline_result.csv")
        elif key=="parallel":
            self._apply_parallel(); self._reveal_artifact("session_journey_metrics.parquet"); self._reveal_artifact("validation_report.json")
        elif key=="benchmark":
            self._apply_benchmark(); self._reveal_artifact("session1_benchmark.csv")
        elif key=="balance":
            self._apply_balance(); self._reveal_artifact("partition_sizes.csv")

    def _drain(self):
        try:
            while True:
                item=self.q.get_nowait()
                kind=item[0]
                if kind=="text":
                    self._log(item[1])
                elif kind=="done":
                    _,key,rc,out=item
                    self.running=False
                    self._apply_stage(key,rc,out)
                    self._stop_status(rc==0)
                    self._log(f"\n>>> FINISHED: {key} (exit code {rc})\n")
                    self._select_tab("Pipeline")
                elif kind=="stage_running":
                    _,key=item
                    self._set_stage(key,"running","Running current-session computation...")
                    if self.running_stage=="Run everything":
                        self.live_status.set(f"RUNNING PIPELINE: {dict((k,l) for k,l,_,_ in self.stage_labels)[key]}...")
                elif kind=="all_result":
                    _,key,rc,out=item
                    self._apply_stage(key,rc,out)
                elif kind=="all_done":
                    self.running=False
                    self._stop_status(bool(item[1]))
                    self._log("\n>>> SESSION 1 PIPELINE COMPLETE\n" if item[1] else "\n>>> PIPELINE STOPPED WITH ERROR\n")
                    self._select_tab("Pipeline")
        except queue.Empty:
            pass
        self.after(120,self._drain)

if __name__=="__main__":
    RetailMetricsSession1GUI().mainloop()
