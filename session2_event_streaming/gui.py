from __future__ import annotations

import csv
import importlib
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

BASE = Path(__file__).resolve().parent
RESULTS = BASE / "results"
RESULTS.mkdir(exist_ok=True)

def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

class RetailMetricsSession2GUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("RetailMetrics — Session 2 Event Streaming & Messaging Backbone")
        self.geometry("1540x920")
        self.minsize(1180, 720)

        self.bg = "#f7fafc"
        self.surface = "#ffffff"
        self.teal = "#0f766e"
        self.teal_dark = "#0b5f59"
        self.green = "#198754"
        self.green_soft = "#eef9f1"
        self.orange = "#c65f08"
        self.orange_soft = "#fff0e4"
        self.red = "#c03d3d"
        self.red_soft = "#fff0f0"
        self.blue_soft = "#eef3fa"
        self.text = "#0f172a"
        self.gray = "#64748b"
        self.border = "#dbe4ee"

        self.configure(bg=self.bg)
        self.running = False
        self.pg_connected = False

        # Session 2 reads the migrated Toy Store tables directly from PostgreSQL.
        # These variables must exist before any stage/button can test the connection.
        self.pg_host_var = tk.StringVar(value="localhost")
        self.pg_port_var = tk.StringVar(value="5432")
        self.pg_database_var = tk.StringVar(value="retailmetrics")
        self.pg_user_var = tk.StringVar(value="postgres")
        self.pg_password_var = tk.StringVar(value="")
        self.pg_status_var = tk.StringVar(value="Not tested")

        self.log_queue = queue.Queue()
        self.running_stage = None
        self.stage_started_at = None
        self.running_dots = 0
        self.stage_state = {
            "Log self-test": "not run",
            "Produce": "not run",
            "Consume": "not run",
            "Reconcile": "not run",
            "Failure & recovery": "not run",
            "Replay": "not run",
        }

        self._styles()
        self._build_header()
        self._build_tabs()
        self._build_pipeline()
        self._build_durable()
        self._build_consumers()
        self._build_failure()
        self._build_replay()
        self._build_reconciliation()
        self._build_monetization()
        self._build_console()
        self.after(120, self._drain)

    def _styles(self):
        s = ttk.Style(self)
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        s.configure("TNotebook", background=self.bg, borderwidth=0)
        s.configure(
            "TNotebook.Tab", padding=(15, 10), font=("Segoe UI", 9),
            background=self.bg, foreground="#475569"
        )
        s.map(
            "TNotebook.Tab",
            background=[("selected", self.bg)],
            foreground=[("selected", self.teal)]
        )
        s.configure(
            "Treeview", font=("Segoe UI", 9), rowheight=28,
            background=self.surface, fieldbackground=self.surface,
            foreground=self.text
        )
        s.configure(
            "Treeview.Heading", font=("Segoe UI", 9, "bold"),
            background=self.teal, foreground="white", relief="flat"
        )

    def _build_header(self):
        h = tk.Frame(self, bg=self.surface, height=92)
        h.pack(fill="x")
        h.pack_propagate(False)
        left = tk.Frame(h, bg=self.surface)
        left.pack(side="left", fill="both", expand=True, padx=24, pady=12)
        tk.Label(
            left,
            text="RetailMetrics — Session 2 Event Streaming & Messaging Backbone",
            bg=self.surface, fg=self.text, font=("Segoe UI", 18, "bold")
        ).pack(anchor="w")
        tk.Label(
            left,
            text=(
                "Toy Store E-Commerce Database  •  topic commerce.activity.recorded  •  "
                "4 logical partitions keyed on website_session_id  •  event time created_at  •  at-least-once"
            ),
            bg=self.surface, fg=self.gray, font=("Segoe UI", 9)
        ).pack(anchor="w", pady=(5, 0))
        badge = tk.Frame(
            h, bg="#f0fdf4", highlightbackground="#bbf7d0",
            highlightthickness=1
        )
        badge.pack(side="right", padx=24, pady=25)
        tk.Label(
            badge,
            text="●  transaction-driven retail monetization",
            bg="#f0fdf4", fg="#166534", font=("Segoe UI", 9)
        ).pack(padx=12, pady=7)
        tk.Frame(self, bg=self.border, height=1).pack(fill="x")

    def _build_tabs(self):
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)
        self.tabs = {}
        self.tab_pages = {}
        self.scroll_canvases = {}

        for name in (
            "Pipeline", "Durable log", "Consumers & lag",
            "Failure & recovery", "Replay", "Reconciliation",
            "Monetization", "Console"
        ):
            shell = tk.Frame(self.nb, bg=self.bg)
            self.tab_pages[name] = shell
            self.nb.add(shell, text=name)

            if name == "Console":
                self.tabs[name] = shell
                continue

            canvas = tk.Canvas(shell, bg=self.bg, highlightthickness=0, bd=0)
            sb = ttk.Scrollbar(shell, orient="vertical", command=canvas.yview)
            canvas.configure(yscrollcommand=sb.set)
            sb.pack(side="right", fill="y")
            canvas.pack(side="left", fill="both", expand=True)

            content = tk.Frame(canvas, bg=self.bg)
            wid = canvas.create_window((0,0), window=content, anchor="nw")

            content.bind(
                "<Configure>",
                lambda e, c=canvas: c.configure(scrollregion=c.bbox("all"))
            )
            canvas.bind(
                "<Configure>",
                lambda e, c=canvas, w=wid: c.itemconfigure(w, width=e.width)
            )

            def wheel(event, c=canvas):
                if getattr(event, "delta", 0):
                    c.yview_scroll(int(-1 * (event.delta / 120)), "units")
                elif getattr(event, "num", None) == 4:
                    c.yview_scroll(-1, "units")
                elif getattr(event, "num", None) == 5:
                    c.yview_scroll(1, "units")
                return "break"

            def bind_wheel(event, c=canvas, handler=wheel):
                c.bind_all("<MouseWheel>", handler)
                c.bind_all("<Button-4>", handler)
                c.bind_all("<Button-5>", handler)

            def unbind_wheel(event, c=canvas):
                c.unbind_all("<MouseWheel>")
                c.unbind_all("<Button-4>")
                c.unbind_all("<Button-5>")

            content.bind("<Enter>", bind_wheel)
            content.bind("<Leave>", unbind_wheel)
            canvas.bind("<Enter>", bind_wheel)
            canvas.bind("<Leave>", unbind_wheel)

            self.tabs[name] = content
            self.scroll_canvases[name] = canvas

        self.nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    def _on_tab_changed(self, event=None):
        try:
            label = self.nb.tab(self.nb.select(), "text")
            canvas = self.scroll_canvases.get(label)
            if canvas is not None:
                canvas.yview_moveto(0.0)
        except Exception:
            pass

    def _button(self, parent, text, command, primary=False, danger=False):
        if primary:
            bg, fg, active = self.teal, "white", self.teal_dark
        elif danger:
            bg, fg, active = "#d44c5a", "white", "#b93d49"
        else:
            bg, fg, active = self.surface, "#334155", "#f1f5f9"
        return tk.Button(
            parent, text=text, command=command, bg=bg, fg=fg,
            activebackground=active, activeforeground=fg,
            relief="flat", bd=0, padx=13, pady=7,
            font=("Segoe UI", 8), cursor="hand2",
            highlightbackground=self.border, highlightthickness=1
        )

    def _title(self, parent, text, buttons=None):
        row = tk.Frame(parent, bg=self.bg)
        row.pack(fill="x", pady=(0,10))
        tk.Label(
            row, text=text, bg=self.bg, fg=self.text,
            font=("Segoe UI", 16, "bold")
        ).pack(side="left")
        if buttons:
            for label, cmd, primary, danger in reversed(buttons):
                self._button(row,label,cmd,primary,danger).pack(
                    side="right", padx=(5,0)
                )

    def _banner(self, parent, var, orange=False):
        bg = self.orange_soft if orange else "#eef8e8"
        fg = self.orange if orange else "#477526"
        border = "#f2c6a5" if orange else "#cfe5c1"
        f = tk.Frame(parent,bg=bg,highlightbackground=border,highlightthickness=1)
        f.pack(fill="x",pady=(0,12))
        tk.Label(
            f,textvariable=var,bg=bg,fg=fg,font=("Segoe UI",9,"bold"),
            anchor="w",padx=12,pady=10
        ).pack(fill="x")

    def _tree(self,parent,columns,headings,widths,height=8):
        f=tk.Frame(
            parent,bg=self.surface,highlightbackground=self.border,
            highlightthickness=1
        )
        tree=ttk.Treeview(f,columns=columns,show="headings",height=height)
        for col,head,width in zip(columns,headings,widths):
            tree.heading(col,text=head)
            tree.column(col,width=width,anchor="w")
        tree.pack(fill="both",expand=True)
        return f,tree

    def _card(self,parent,var,subtitle,tint,value_color=None):
        f=tk.Frame(parent,bg=tint,highlightbackground=self.border,highlightthickness=1)
        tk.Label(
            f,textvariable=var,bg=tint,fg=value_color or self.teal,
            font=("Segoe UI",18,"bold")
        ).pack(anchor="w",padx=15,pady=(13,2))
        tk.Label(
            f,text=subtitle,bg=tint,fg=self.gray,font=("Segoe UI",8)
        ).pack(anchor="w",padx=15,pady=(0,12))
        return f

    def _bar_canvas(self,parent,height=230):
        c=tk.Canvas(
            parent,bg=self.surface,height=height,
            highlightbackground=self.border,highlightthickness=1
        )
        c.pack(fill="x")
        return c

    def _draw_bars(self, canvas, labels, values, even_share=None):
        canvas.delete("all")
        canvas.update_idletasks()
        w=max(canvas.winfo_width(),700)
        h=max(canvas.winfo_height(),200)
        if not values or max(values)<=0:
            canvas.create_text(
                w/2,h/2,text="No measured data yet",
                fill=self.gray,font=("Segoe UI",10)
            )
            return

        maxv=max(values)
        scale_max=max(maxv, even_share or 0) * 1.16
        left,right,top,bottom=45,25,25,45
        usable_w=w-left-right
        usable_h=h-top-bottom
        gap=usable_w/len(values)
        bar_w=gap*.5
        heavy_index=values.index(maxv)

        if even_share:
            y=top+usable_h-(usable_h*(even_share/scale_max))
            canvas.create_line(
                left,y,w-right,y,
                fill="#d26b74",dash=(8,5),width=1
            )

            # Keep the annotation away from the rightmost bar/value label.
            label_x = left + usable_w * 0.73
            label_y = max(top + 10, y - 12)

            # Small background patch improves readability over the chart.
            text_value = f"even share = {even_share:,.0f}"
            bbox_width = 150
            canvas.create_rectangle(
                label_x - bbox_width/2,
                label_y - 9,
                label_x + bbox_width/2,
                label_y + 9,
                fill=self.surface,
                outline=""
            )
            canvas.create_text(
                label_x,
                label_y,
                text=text_value,
                fill="#c95761",
                font=("Segoe UI",8,"bold"),
                anchor="center"
            )

        for i,(lab,val) in enumerate(zip(labels,values)):
            x=left+gap*i+gap/2
            bh=usable_h*(val/scale_max)
            y0=top+usable_h-bh
            y1=top+usable_h
            fill="#c95a09" if i==heavy_index else "#367fb9"
            canvas.create_rectangle(
                x-bar_w/2,y0,x+bar_w/2,y1,
                fill=fill,outline=""
            )
            canvas.create_text(
                x,y0-10,text=f"{val:,.0f}",
                fill="#334155",font=("Segoe UI",8)
            )
            canvas.create_text(
                x,y1+16,text=lab,fill=self.gray,font=("Segoe UI",8)
            )
        canvas.create_line(left,top+usable_h,w-right,top+usable_h,fill=self.border)

    def _build_connection_box(self,parent):
        box=tk.Frame(
            parent,bg=self.surface,highlightbackground=self.border,
            highlightthickness=1
        )
        box.pack(fill="x",pady=(0,12))
        tk.Label(
            box,text="PostgreSQL source + durable log",
            bg=self.surface,fg=self.text,font=("Segoe UI",10,"bold")
        ).grid(row=0,column=0,columnspan=11,sticky="w",padx=12,pady=(9,5))

        self.pg_host_var=tk.StringVar(value="localhost")
        self.pg_port_var=tk.StringVar(value="5432")
        self.pg_database_var=tk.StringVar(value="retailmetrics")
        self.pg_user_var=tk.StringVar(value="postgres")
        self.pg_password_var=tk.StringVar(value="")

        fields=[
            ("Host",self.pg_host_var,14,False),
            ("Port",self.pg_port_var,7,False),
            ("Database",self.pg_database_var,16,False),
            ("User",self.pg_user_var,13,False),
            ("Password",self.pg_password_var,14,True),
        ]
        for i,(label,var,width,secret) in enumerate(fields):
            col=i*2
            tk.Label(
                box,text=label,bg=self.surface,fg=self.gray,
                font=("Segoe UI",7,"bold")
            ).grid(row=1,column=col,sticky="w",
                   padx=(12 if i==0 else 5,3),pady=(0,2))
            tk.Entry(
                box,textvariable=var,width=width,
                show="*" if secret else "",relief="solid",
                bd=1,font=("Segoe UI",9)
            ).grid(row=2,column=col,columnspan=2,sticky="ew",
                   padx=(12 if i==0 else 5,7),pady=(0,9))
        self.pg_status_var=tk.StringVar(value="Not tested")
        tk.Label(
            box,textvariable=self.pg_status_var,bg=self.surface,fg=self.gray,
            font=("Segoe UI",8,"bold")
        ).grid(row=1,column=10,sticky="w",padx=(8,12),pady=(0,2))
        self._button(
            box,"Test connection",self.test_connection,primary=True
        ).grid(row=2,column=10,padx=(8,12),pady=(0,9))

    # ---------- Pipeline ----------
    def _build_pipeline(self):
        wrap=tk.Frame(self.tabs["Pipeline"],bg=self.bg)
        wrap.pack(fill="both",expand=True,padx=20,pady=(16,28))

        cards=tk.Frame(wrap,bg=self.bg)
        cards.pack(fill="x",pady=(0,12))

        self.p_events=tk.StringVar(value="—")
        self.p_groups=tk.StringVar(value="—")
        self.p_lag=tk.StringVar(value="—")
        self.p_pass=tk.StringVar(value="—")

        for c in (
            self._card(cards,self.p_events,"events in the durable log","#edf6ff"),
            self._card(cards,self.p_groups,"consumer groups tracked","#e8f7f5"),
            self._card(cards,self.p_lag,"total lag across all groups","#fff7e7",self.orange),
            self._card(cards,self.p_pass,"reconciliation vs Session 1","#eef9f1",self.green),
        ):
            c.pack(side="left",fill="x",expand=True,padx=5)

        connection=tk.Frame(
            wrap,bg=self.surface,
            highlightbackground=self.border,highlightthickness=1
        )
        connection.pack(fill="x",pady=(0,10))

        tk.Label(
            connection,text="PostgreSQL",
            bg=self.surface,fg=self.text,
            font=("Segoe UI",9,"bold")
        ).pack(side="left",padx=(12,7),pady=8)

        for label,var,width,secret in (
            ("Host",self.pg_host_var,12,False),
            ("Port",self.pg_port_var,6,False),
            ("Database",self.pg_database_var,14,False),
            ("User",self.pg_user_var,12,False),
            ("Password",self.pg_password_var,12,True),
        ):
            tk.Label(
                connection,text=label,
                bg=self.surface,fg=self.gray,
                font=("Segoe UI",7,"bold")
            ).pack(side="left",padx=(4,3))
            tk.Entry(
                connection,textvariable=var,width=width,
                show="*" if secret else "",
                relief="solid",bd=1,font=("Segoe UI",8)
            ).pack(side="left",padx=(0,5),pady=7)

        self._button(
            connection,"Test connection",
            self.test_connection,primary=True
        ).pack(side="left",padx=(8,6),pady=6)

        tk.Label(
            connection,textvariable=self.pg_status_var,
            bg=self.surface,fg=self.teal,
            font=("Segoe UI",8,"bold")
        ).pack(side="left",padx=(2,12))

        controls=tk.Frame(wrap,bg=self.bg)
        controls.pack(fill="x",pady=(0,10))

        tk.Label(
            controls,text="Run a stage",bg=self.bg,fg=self.text,
            font=("Segoe UI",11,"bold")
        ).pack(side="left",padx=(0,10))

        for stage in self.stage_state:
            self._button(
                controls,stage,lambda s=stage:self.run_stage(s)
            ).pack(side="left",padx=3)

        self._button(
            controls,"Run everything",self.run_all,primary=True
        ).pack(side="left",padx=(12,3))

        self._button(
            controls,"Refresh from results/",self.refresh_from_results
        ).pack(side="left",padx=3)

        status=tk.Frame(
            wrap,bg="#fff7e7",highlightbackground="#f0d7a8",
            highlightthickness=1
        )
        status.pack(fill="x",pady=(0,12))

        self.live_status_var=tk.StringVar(value="Pipeline idle — no stage is running.")
        self.live_elapsed_var=tk.StringVar(value="")
        tk.Label(
            status,textvariable=self.live_status_var,bg="#fff7e7",
            fg="#9a5c1b",font=("Segoe UI",9,"bold")
        ).pack(side="left",padx=12,pady=8)
        tk.Label(
            status,textvariable=self.live_elapsed_var,bg="#fff7e7",
            fg="#9a5c1b",font=("Segoe UI",9)
        ).pack(side="right",padx=12,pady=8)

        f,self.pipeline_tree=self._tree(
            wrap,("stage","status","result"),
            ["Stage","Status","Headline result"],
            [300,150,930],height=6
        )
        f.pack(fill="x",pady=(0,12))

        for i,stage in enumerate(self.stage_state, start=1):
            self.pipeline_tree.insert(
                "","end",iid=stage,
                values=(f"{i}. {stage}","not run",self._default_result(stage))
            )

        note=tk.Frame(
            wrap,bg=self.blue_soft,
            highlightbackground=self.border,
            highlightthickness=1
        )
        note.pack(fill="x",pady=(0,12))
        tk.Label(
            note,
            text=(
                "Every button calls the same backend script used from the command line. "
                "The tables read the files written into results/. Log self-test runs first as a readiness check; "
                "Produce then validates the event-dependent guarantees before Consume. Consume must complete before Reconcile."
            ),
            bg=self.blue_soft,fg="#4f6478",
            font=("Segoe UI",9),wraplength=1300,
            justify="left",anchor="w",padx=12,pady=10
        ).pack(fill="x")

        tk.Label(
            wrap,text="Artifacts in results/",bg=self.bg,fg=self.text,
            font=("Segoe UI",11,"bold")
        ).pack(anchor="w",pady=(0,5))

        f,self.artifact_tree=self._tree(
            wrap,
            ("artifact","writer","status","size","last_written"),
            ["Artifact","Written by","Status","Size","Last written"],
            [340,320,120,140,220],height=8
        )
        f.pack(fill="both",expand=True)

        self.artifacts = [
            ("handover_verification.json","handover_verify.py"),
            ("enrichment_report.json","produce_events.py — enrichment guard"),
            ("producer_summary.json","produce_events.py"),
            ("log_self_test.json","self_test.py"),
            ("consumer_summary.json","consumers.py"),
            ("consumer_lag.csv","consumers.py — lag report"),
            ("stream_session_metrics.csv","consumers.py — session projector"),
            ("failure_recovery.json","failure_recovery.py"),
            ("replay_suite.json","replay_suite.py"),
            ("reconciliation_report.json","reconcile.py"),
            ("monetization_snapshot.json","replay_suite.py — late joiner"),
        ]
        for artifact,writer in self.artifacts:
            self.artifact_tree.insert(
                "","end",iid=f"artifact::{artifact}",
                values=(artifact,writer,"not written","—","—")
            )

    # ---------- Durable log ----------
    def _build_durable(self):
        wrap=tk.Frame(self.tabs["Durable log"],bg=self.bg)
        wrap.pack(fill="both",expand=True,padx=20,pady=16)

        self._title(
            wrap,"The log and its partitions",
            [
                ("Produce (--reset)",self.produce_reset,False,False),
                ("Run self-test",lambda:self.run_stage("Log self-test"),True,False),
            ]
        )

        self.durable_banner=tk.StringVar(
            value="No producer run yet. The topic will retain events independently of consumers."
        )
        self._banner(wrap,self.durable_banner)

        body=tk.Frame(wrap,bg=self.bg)
        body.pack(fill="both",expand=True)

        left=tk.Frame(body,bg=self.bg)
        left.pack(side="left",fill="both",expand=True,padx=(0,8))

        right=tk.Frame(body,bg=self.bg)
        right.pack(side="left",fill="both",expand=True,padx=(8,0))

        tk.Label(
            left,text="Partition distribution",
            bg=self.bg,fg=self.text,font=("Segoe UI",11,"bold")
        ).pack(anchor="w",pady=(0,5))

        self.partition_chart=self._bar_canvas(left,280)

        f,self.partition_tree=self._tree(
            left,("partition","events","share","observation"),
            ["Partition","Events","Share","Observation"],
            [130,150,120,380],height=5
        )
        f.pack(fill="x",pady=(8,0))

        tk.Label(
            right,text="Guarantees verified by the self-test",
            bg=self.bg,fg=self.text,font=("Segoe UI",11,"bold")
        ).pack(anchor="w",pady=(0,5))

        f,self.guarantee_tree=self._tree(
            right,("guarantee","result"),
            ["Guarantee","Result"],[430,140],height=6
        )
        f.pack(fill="x",pady=(0,12))

        for guarantee in (
            "Stable key routing",
            "Ordering within a partition",
            "Non-destructive read",
            "Consumer group isolation",
            "Replay",
            "Durability",
        ):
            self.guarantee_tree.insert(
                "","end",values=(guarantee,"NOT RUN")
            )

        tk.Label(
            right,text="Why these four numbers are uneven",
            bg=self.bg,fg=self.text,font=("Segoe UI",11,"bold")
        ).pack(anchor="w",pady=(0,5))

        panel=tk.Frame(
            right,bg=self.orange_soft,
            highlightbackground="#f2c6a5",highlightthickness=1
        )
        panel.pack(fill="x")

        self.durable_explain=tk.StringVar(
            value=(
                "website_session_id values are distributed across four logical partitions. "
                "The session-affinity key keeps one website session in one partition; uneven "
                "partition counts are load imbalance, not data loss."
            )
        )

        tk.Label(
            panel,textvariable=self.durable_explain,
            bg=self.orange_soft,fg=self.orange,
            font=("Segoe UI",9),justify="left",
            anchor="nw",wraplength=520,padx=14,pady=12
        ).pack(fill="x")

    # ---------- Consumers ----------
    def _build_consumers(self):
        wrap=tk.Frame(self.tabs["Consumers & lag"],bg=self.bg)
        wrap.pack(fill="both",expand=True,padx=20,pady=16)

        self._title(
            wrap,"Three groups, one topic, independent offsets",
            [("Run all consumers",lambda:self.run_stage("Consume"),True,False)]
        )

        self.consumer_banner=tk.StringVar(value="No consumer run yet.")
        self._banner(wrap,self.consumer_banner)

        tk.Label(
            wrap,text="Throughput of the last run",
            bg=self.bg,fg=self.text,font=("Segoe UI",11,"bold")
        ).pack(anchor="w",pady=(0,5))

        self.consumer_chart=self._bar_canvas(wrap,210)

        f,self.consumer_summary_tree=self._tree(
            wrap,
            ("group","processed","seconds","eps","duplicates","lag"),
            ["Group","Processed","Seconds","Events/sec","Duplicates skipped","Final lag"],
            [290,140,120,150,170,120],height=4
        )
        f.pack(fill="x",pady=(8,12))

        tk.Label(
            wrap,
            text="Committed offsets, per group per partition (results/consumer_lag.csv)",
            bg=self.bg,fg=self.text,font=("Segoe UI",11,"bold")
        ).pack(anchor="w",pady=(0,5))

        f,self.consumer_offset_tree=self._tree(
            wrap,
            ("group","partition","end_offset","committed","lag"),
            ["Group","Partition","End offset","Committed","Lag"],
            [310,130,160,160,110],height=10
        )
        f.pack(fill="both",expand=True)

    # ---------- Failure ----------
    def _build_failure(self):
        wrap=tk.Frame(self.tabs["Failure & recovery"],bg=self.bg)
        wrap.pack(fill="both",expand=True,padx=20,pady=16)

        top=tk.Frame(wrap,bg=self.bg)
        top.pack(fill="x",pady=(0,10))

        tk.Label(
            top,text="Crash the audit consumer on purpose",
            bg=self.bg,fg=self.text,font=("Segoe UI",16,"bold")
        ).pack(side="left")

        self.fail_after_var=tk.StringVar(value="250000")
        tk.Label(
            top,text="fail after N events:",
            bg=self.bg,fg=self.gray,font=("Segoe UI",8)
        ).pack(side="right",padx=(8,5))

        tk.Entry(
            top,textvariable=self.fail_after_var,width=12,
            relief="solid",bd=1,font=("Segoe UI",9),
            justify="right"
        ).pack(side="right",padx=(8,5))

        self._button(
            top,"Inject failure, then recover",
            self.run_failure_custom,primary=True,danger=True
        ).pack(side="right")

        self.failure_banner=tk.StringVar(value="No failure has been injected.")
        self._banner(wrap,self.failure_banner,orange=True)

        tk.Label(
            wrap,text="Blast radius — what else failed with it",
            bg=self.bg,fg=self.text,font=("Segoe UI",11,"bold")
        ).pack(anchor="w",pady=(0,5))

        f,self.failure_blast_tree=self._tree(
            wrap,("component","status","evidence"),
            ["Component","Status","Evidence"],
            [310,180,800],height=5
        )
        f.pack(fill="x",pady=(0,12))

        cards=tk.Frame(wrap,bg=self.bg)
        cards.pack(fill="x",pady=(0,12))

        self.fail_handled=tk.StringVar(value="—")
        self.fail_backlog=tk.StringVar(value="—")
        self.fail_entries=tk.StringVar(value="—")
        self.fail_redelivered=tk.StringVar(value="—")

        for c in (
            self._card(cards,self.fail_handled,"handled before the crash","#edf6ff"),
            self._card(cards,self.fail_backlog,"backlog left in the log","#e8f7f5"),
            self._card(cards,self.fail_entries,"unique audit records after recovery","#fff7e7",self.orange),
            self._card(cards,self.fail_redelivered,"redelivered on restart","#fff0f0",self.red),
        ):
            c.pack(side="left",fill="x",expand=True,padx=5)

        panel=tk.Frame(
            wrap,bg=self.blue_soft,
            highlightbackground=self.border,highlightthickness=1
        )
        panel.pack(fill="x")

        tk.Label(
            panel,
            text=(
                "The arithmetic reconciles rather than being assumed. The audit consumer can "
                "handle events after its last committed position; those events are delivered again "
                "after restart. That gap is at-least-once delivery. An idempotent sink should key "
                "writes by event_id so the repeat does not change the final state."
            ),
            bg=self.blue_soft,fg="#4f6478",
            font=("Segoe UI",9),justify="left",
            wraplength=1250,anchor="w",padx=14,pady=12
        ).pack(fill="x")

    # ---------- Replay ----------
    def _build_replay(self):
        wrap=tk.Frame(self.tabs["Replay"],bg=self.bg)
        wrap.pack(fill="both",expand=True,padx=20,pady=16)

        top=tk.Frame(wrap,bg=self.bg)
        top.pack(fill="x",pady=(0,10))

        tk.Label(
            top,text="What a durable log gives you for free",
            bg=self.bg,fg=self.text,font=("Segoe UI",16,"bold")
        ).pack(side="left")

        self.partial_replay_var=tk.StringVar(value="")
        self._button(
            top,"Run all four demonstrations",
            self.run_replay_custom,primary=True
        ).pack(side="right")

        tk.Entry(
            top,textvariable=self.partial_replay_var,width=26,
            relief="solid",bd=1,font=("Segoe UI",9)
        ).pack(side="right",padx=(5,8))

        tk.Label(
            top,text="partial replay from:",
            bg=self.bg,fg=self.gray,font=("Segoe UI",8)
        ).pack(side="right")

        self.replay_banner=tk.StringVar(value="No replay demo run yet.")
        self._banner(wrap,self.replay_banner)

        f,self.replay_tree=self._tree(
            wrap,
            ("demo","proof","result"),
            ["Demonstration","What it proves","Result"],
            [410,610,330],height=5
        )
        f.pack(fill="x",pady=(0,12))

        tk.Label(
            wrap,
            text=(
                "Revenue by traffic source — computed by a consumer that did not exist "
                "when the events were produced"
            ),
            bg=self.bg,fg=self.text,font=("Segoe UI",11,"bold")
        ).pack(anchor="w",pady=(0,5))

        f,self.replay_money_tree=self._tree(
            wrap,
            ("source","sessions","conversions","rate","revenue"),
            ["UTM source","Sessions","Conversions","Conversion rate","Revenue"],
            [260,160,170,170,220],height=8
        )
        f.pack(fill="both",expand=True)

    # ---------- Reconciliation ----------
    def _build_reconciliation(self):
        wrap=tk.Frame(self.tabs["Reconciliation"],bg=self.bg)
        wrap.pack(fill="both",expand=True,padx=20,pady=16)

        self._title(
            wrap,"Does the stream agree with Session 1's batch answer?",
            [("Reconcile now",lambda:self.run_stage("Reconcile"),True,False)]
        )

        self.rec_banner=tk.StringVar(value="Not run yet.")
        self._banner(wrap,self.rec_banner)

        f,self.rec_tree=self._tree(
            wrap,
            ("measure","batch","stream","difference"),
            ["Measure","Session 1 — batch","Session 2 — stream","Difference"],
            [360,300,300,300],height=7
        )
        f.pack(fill="x",pady=(0,12))

        tk.Label(
            wrap,text="The four conditions Session 6 will enforce in CI",
            bg=self.bg,fg=self.text,font=("Segoe UI",11,"bold")
        ).pack(anchor="w",pady=(0,5))

        f,self.ci_tree=self._tree(
            wrap,("condition","kind","held"),
            ["Condition","Kind","Held?"],
            [900,190,140],height=5
        )
        f.pack(fill="x",pady=(0,12))

        for row in (
            ("The streamed website_session_id set equals the batch session set","EXACT","NOT RUN"),
            ("Maximum absolute difference in pageview_count and converted is exactly 0","EXACT","NOT RUN"),
            ("Maximum absolute difference in duration, revenue, and profit is below tolerance","APPROXIMATE","NOT RUN"),
            ("Every consumer group finishes at lag 0","EXACT","NOT RUN"),
        ):
            self.ci_tree.insert("","end",values=row)

        panel=tk.Frame(
            wrap,bg=self.blue_soft,
            highlightbackground=self.border,highlightthickness=1
        )
        panel.pack(fill="x")

        tk.Label(
            panel,
            text=(
                "Any residual in floating-point fields can come from summation or representation "
                "order, not necessarily from a lost event. Integer counts and conversion flags must "
                "match exactly; only numeric duration/revenue/profit fields use the 1e-6 tolerance."
            ),
            bg=self.blue_soft,fg="#4f6478",
            font=("Segoe UI",9),justify="left",
            wraplength=1250,anchor="w",padx=14,pady=12
        ).pack(fill="x")

    # ---------- Monetization ----------
    def _build_monetization(self):
        wrap=tk.Frame(self.tabs["Monetization"],bg=self.bg)
        wrap.pack(fill="both",expand=True,padx=20,pady=(16,28))
        self._title(
            wrap,
            "RetailMetrics monetization — transaction-driven e-commerce revenue",
            [("Build / refresh from replay",lambda:self.run_stage("Replay"),True,False)]
        )

        self.mon_banner=tk.StringVar(
            value=(
                "Monetization follows the dataset's real mechanism: product purchases generate revenue; "
                "COGS determines gross profit; refunds reduce realized revenue."
            )
        )
        self._banner(wrap,self.mon_banner)

        flow=tk.Frame(
            wrap,bg=self.blue_soft,highlightbackground=self.border,
            highlightthickness=1
        )
        flow.pack(fill="x",pady=(0,12))
        tk.Label(
            flow,
            text=(
                "Website session → pageviews → purchase conversion → order revenue → "
                "cost of goods sold (COGS) → gross profit → possible refund → net revenue"
            ),
            bg=self.blue_soft,fg="#4f6478",font=("Segoe UI",10,"bold"),
            wraplength=1250,justify="center",anchor="center",padx=14,pady=14
        ).pack(fill="x")

        cards=tk.Frame(wrap,bg=self.bg); cards.pack(fill="x",pady=(0,12))
        self.mon_revenue=tk.StringVar(value="—")
        self.mon_profit=tk.StringVar(value="—")
        self.mon_refunds=tk.StringVar(value="—")
        self.mon_net=tk.StringVar(value="—")
        for c in (
            self._card(cards,self.mon_revenue,"gross order revenue","#edf6ff"),
            self._card(cards,self.mon_profit,"gross profit","#e8f7f5"),
            self._card(cards,self.mon_refunds,"refund adjustments","#fff7e7",self.orange),
            self._card(cards,self.mon_net,"net revenue after refunds","#eef9f1",self.green),
        ):
            c.pack(side="left",fill="x",expand=True,padx=5)

        cards2=tk.Frame(wrap,bg=self.bg); cards2.pack(fill="x",pady=(0,12))
        self.mon_sessions=tk.StringVar(value="—")
        self.mon_converted=tk.StringVar(value="—")
        self.mon_rate=tk.StringVar(value="—")
        self.mon_cogs=tk.StringVar(value="—")
        for c in (
            self._card(cards2,self.mon_sessions,"website sessions","#edf6ff"),
            self._card(cards2,self.mon_converted,"purchase conversions","#e8f7f5"),
            self._card(cards2,self.mon_rate,"session-to-purchase conversion rate","#fff7e7",self.orange),
            self._card(cards2,self.mon_cogs,"cost of goods sold","#eef9f1",self.green),
        ):
            c.pack(side="left",fill="x",expand=True,padx=5)

        body=tk.Frame(wrap,bg=self.bg); body.pack(fill="both",expand=True)
        left=tk.Frame(body,bg=self.bg); left.pack(side="left",fill="both",expand=True,padx=(0,7))
        right=tk.Frame(body,bg=self.bg); right.pack(side="left",fill="both",expand=True,padx=(7,0))

        tk.Label(
            left,text="Revenue by primary product",
            bg=self.bg,fg=self.text,font=("Segoe UI",11,"bold")
        ).pack(anchor="w",pady=(0,5))
        f,self.mon_product_tree=self._tree(
            left,("product","orders","revenue","profit"),
            ["Product ID","Orders","Revenue","Gross profit"],
            [160,150,210,210],height=6
        )
        f.pack(fill="both",expand=True)

        tk.Label(
            right,text="Revenue by Traffic Source",
            bg=self.bg,fg=self.text,font=("Segoe UI",11,"bold")
        ).pack(anchor="w",pady=(0,5))
        f,self.mon_source_tree=self._tree(
            right,("source","sessions","conversions","rate","revenue"),
            ["UTM source","Sessions","Conversions","Rate","Revenue"],
            [190,130,140,110,190],height=6
        )
        f.pack(fill="both",expand=True)

    # ---------- Console ----------
    def _build_console(self):
        wrap=tk.Frame(self.tabs["Console"],bg=self.bg)
        wrap.pack(fill="both",expand=True,padx=20,pady=16)

        top=tk.Frame(wrap,bg=self.bg)
        top.pack(fill="x")

        tk.Label(
            top,text="Verbatim output of every stage",
            bg=self.bg,fg=self.text,font=("Segoe UI",16,"bold")
        ).pack(side="left")

        self._button(
            top,"Save transcript...",self.save_transcript
        ).pack(side="right",padx=(5,0))

        self._button(
            top,"Clear",lambda:self.console.delete("1.0","end")
        ).pack(side="right")

        panel=tk.Frame(wrap,bg="#111827")
        panel.pack(fill="both",expand=True,pady=(10,0))

        self.console=tk.Text(
            panel,wrap="word",bg="#111827",fg="#e5e7eb",
            insertbackground="white",font=("Consolas",9),
            relief="flat",bd=0,padx=12,pady=12
        )

        sb=ttk.Scrollbar(panel,orient="vertical",command=self.console.yview)
        self.console.configure(yscrollcommand=sb.set)
        self.console.pack(side="left",fill="both",expand=True)
        sb.pack(side="right",fill="y")

    # ---------- Backend ----------
    def _env(self):
        env=os.environ.copy()
        env["RETAILMETRICS_PG_HOST"]=self.pg_host_var.get().strip()
        env["RETAILMETRICS_PG_PORT"]=self.pg_port_var.get().strip()
        env["RETAILMETRICS_PG_DATABASE"]=self.pg_database_var.get().strip()
        env["RETAILMETRICS_PG_USER"]=self.pg_user_var.get().strip()
        env["RETAILMETRICS_PG_PASSWORD"]=self.pg_password_var.get()
        return env

    def test_connection(self):
        try:
            psycopg2 = importlib.import_module("psycopg2")
            conn = psycopg2.connect(
                host=self.pg_host_var.get().strip(),
                port=int(self.pg_port_var.get().strip()),
                dbname=self.pg_database_var.get().strip(),
                user=self.pg_user_var.get().strip(),
                password=self.pg_password_var.get(),
            )

            # Verify the Session 1 migrated source tables exist in PostgreSQL.
            required_tables = [
                "website_sessions",
                "website_pageviews",
                "orders",
                "order_items",
                "order_item_refunds",
                "products",
            ]

            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema='public'
                      AND table_name = ANY(%s)
                    """,
                    (required_tables,),
                )
                found = {row[0] for row in cur.fetchall()}

            conn.close()

            missing = [t for t in required_tables if t not in found]
            if missing:
                self.pg_connected = False
                self.pg_status_var.set("CONNECTED — source tables missing")
                msg = (
                    "Connected to PostgreSQL, but these migrated Session 1 tables "
                    "are missing from database 'retailmetrics':\n\n"
                    + "\n".join(missing)
                )
                self.console.insert("end", f"\nPostgreSQL connection: PARTIAL\n{msg}\n")
                self.console.see("end")
                messagebox.showwarning("RetailMetrics source tables missing", msg)
                return False

            self.pg_connected = True
            self.pg_status_var.set("CONNECTED")
            self.console.insert(
                "end",
                "\nPostgreSQL connection: PASS\n"
                "Database: retailmetrics\n"
                "Session 1 migrated Toy Store source tables: FOUND\n"
            )
            self.console.see("end")

            # Connection testing should not load old Session 2 result files.
            # Previous results are loaded only when the user explicitly clicks
            # "Refresh from results/".
            return True

        except Exception as exc:
            self.pg_connected = False
            self.pg_status_var.set("FAILED")
            self.console.insert(
                "end",
                f"\nPostgreSQL connection: FAIL\n{exc}\n"
            )
            self.console.see("end")
            messagebox.showerror(
                "PostgreSQL connection failed",
                str(exc)
            )
            return False

    def _require_connection(self):
        if self.pg_connected:
            return True
        return bool(self.test_connection())

    def _start_live_status(self,stage):
        self.running_stage=stage
        self.running_dots=0
        self.stage_started_at=time.perf_counter()
        self.live_status_var.set(f"RUNNING: {stage}")
        self.live_elapsed_var.set("elapsed 0.0 s")
        self._animate_live_status()

    def _stop_live_status(self,success=True):
        if self.running_stage:
            elapsed=0.0
            if self.stage_started_at is not None:
                elapsed=time.perf_counter()-self.stage_started_at
            final="COMPLETED" if success else "FAILED"
            self.live_status_var.set(f"{final}: {self.running_stage}")
            self.live_elapsed_var.set(f"elapsed {elapsed:.1f} s")
        self.running_stage=None
        self.stage_started_at=None

    def _animate_live_status(self):
        if not self.running_stage:
            return
        self.running_dots=(self.running_dots+1)%4
        self.live_status_var.set(
            f"RUNNING: {self.running_stage}{'.'*self.running_dots}"
        )
        if self.stage_started_at is not None:
            self.live_elapsed_var.set(
                f"elapsed {time.perf_counter()-self.stage_started_at:.1f} s"
            )
        self.after(500,self._animate_live_status)

    def _default_result(self,stage):
        return {
            "Log self-test":"Verify routing, ordering, non-destructive reads, isolation, replay, durability",
            "Produce":"Replay pageviews plus refunds into one retained commerce topic",
            "Consume":"Run independent session projector, conversion audit, and refund monitor",
            "Reconcile":"Compare streamed session metrics against Session 1",
            "Failure & recovery":"Inject a crash and count at-least-once redelivery",
            "Replay":"Late-joining analytics, deterministic rewind, catch-up, partial replay",
        }[stage]

    def _script_for(self,stage):
        return {
            "Log self-test":"self_test.py",
            "Produce":"produce_events.py",
            "Consume":"consumers.py",
            "Reconcile":"reconcile.py",
            "Failure & recovery":"failure_recovery.py",
            "Replay":"replay_suite.py",
        }[stage]

    def _ensure_streaming_tables(self):
        proc = subprocess.run(
            [sys.executable, str(BASE / "setup_streaming.py")],
            cwd=str(BASE),
            env=self._env(),
            capture_output=True,
            text=True
        )
        if proc.stdout:
            self.log_queue.put(proc.stdout)
        if proc.stderr:
            self.log_queue.put(proc.stderr)
        if proc.returncode != 0:
            raise RuntimeError("Could not initialize Session 2 streaming tables.")

    def produce_reset(self):
        self._run_stage_with_args("Produce", ["--reset"])

    def run_failure_custom(self):
        try:
            n = int(self.fail_after_var.get().strip())
            if n <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror(
                "Invalid failure point",
                "Enter a positive integer for fail after N events."
            )
            return
        self._run_stage_with_args(
            "Failure & recovery",
            ["--fail-after", str(n)]
        )

    def run_replay_custom(self):
        args=[]
        value=self.partial_replay_var.get().strip()
        if value:
            args=["--from-time", value]
        self._run_stage_with_args("Replay", args)

    def _run_stage_with_args(self, stage, args):
        if self.running:
            return
        if not self._require_connection():
            return

        self.running=True
        self._set_stage(stage,"running","Running...")
        self._start_live_status(stage)

        script=self._script_for(stage)

        def worker():
            code=1
            try:
                self._ensure_streaming_tables()
                command=[sys.executable,str(BASE/script),*args]
                self.log_queue.put(
                    f"\n{'='*72}\nRUN: {' '.join(command[1:])}\n{'='*72}\n"
                )
                proc=subprocess.Popen(
                    command,
                    cwd=str(BASE),env=self._env(),
                    stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                    text=True,bufsize=1
                )
                if proc.stdout:
                    for line in proc.stdout:
                        self.log_queue.put(line)
                code=proc.wait()
            except Exception as exc:
                self.log_queue.put(f"\nERROR: {exc}\n")
            self.after(0,lambda:self._stage_finished(stage,code))

        threading.Thread(target=worker,daemon=True).start()

    def refresh_from_results(self):
        for stage in self.stage_state:
            try:
                self._refresh_views(stage)
                headline=self._headline(stage)
                if headline:
                    self._set_stage(stage,"loaded",headline)
            except Exception:
                pass
        self._refresh_artifacts()

    def _refresh_artifacts(self):
        for artifact, writer in getattr(self, "artifacts", []):
            path=RESULTS/artifact
            iid=f"artifact::{artifact}"
            if not self.artifact_tree.exists(iid):
                continue
            if path.exists():
                stat=path.stat()
                size=stat.st_size
                if size >= 1024*1024:
                    size_text=f"{size/(1024*1024):.2f} MB"
                elif size >= 1024:
                    size_text=f"{size/1024:.1f} KB"
                else:
                    size_text=f"{size} B"
                last=time.strftime(
                    "%Y-%m-%d %H:%M:%S",
                    time.localtime(stat.st_mtime)
                )
                self.artifact_tree.item(
                    iid,
                    values=(artifact,writer,"written",size_text,last)
                )
            else:
                self.artifact_tree.item(
                    iid,
                    values=(artifact,writer,"not written","—","—")
                )

    def save_transcript(self):
        path=filedialog.asksaveasfilename(
            title="Save Session 2 transcript",
            defaultextension=".txt",
            filetypes=[("Text files","*.txt"),("All files","*.*")]
        )
        if not path:
            return
        Path(path).write_text(
            self.console.get("1.0","end-1c"),
            encoding="utf-8"
        )

    def run_stage(self,stage):
        self._run_stage_with_args(stage, [])

    def _stage_finished(self,stage,code):
        ok=code==0
        self.running=False
        self._stop_live_status(ok)
        self.stage_state[stage]="passed" if ok else "failed"
        self._set_stage(
            stage,"passed" if ok else "failed",
            self._headline(stage) if ok else "See Console for the error."
        )
        if ok:
            self._refresh_views(stage)
            self._refresh_artifacts()

    def _set_stage(self,stage,status,result):
        if self.pipeline_tree.exists(stage):
            current=list(self.pipeline_tree.item(stage,"values"))
            label=current[0] if current else stage
            self.pipeline_tree.item(
                stage,values=(label,status,result)
            )

    def _headline(self,stage):
        if stage=="Initialize":
            return "Streaming tables are ready in PostgreSQL."
        if stage=="Produce":
            d=read_json(RESULTS/"producer_summary.json")
            return (
                f"{int(d.get('events_after',0)):,} events  •  "
                f"{float(d.get('events_per_sec',0)):,.0f}/s  •  "
                f"skew {float(d.get('skew_ratio',0)):.2f}:1"
            )
        if stage=="Log self-test":
            d=read_json(RESULTS/"log_self_test.json")
            if d.get("phase") == "pre-produce" and d.get("overall_pass"):
                pending=sum(1 for x in d.get("tests",[]) if x.get("status") == "PENDING")
                return f"Pre-produce readiness PASS  •  {pending} event-dependent checks pending until Produce"
            if d.get("phase") == "post-produce" and d.get("overall_pass"):
                return "All durable-log guarantees PASS on retained events."
            return "One or more durable-log checks failed."
        if stage=="Consume":
            d=read_json(RESULTS/"consumer_summary.json")
            return (
                f"{len(d.get('groups',[]))} groups  •  total lag "
                f"{int(d.get('total_lag',0)):,}  •  producer changes needed: 0"
            )
        if stage=="Reconcile":
            d=read_json(RESULTS/"reconciliation_report.json")
            return (
                f"PASSED  •  {int(d.get('stream_groups',0)):,} sessions  •  "
                f"count Δ {int(d.get('count_difference',0)):,}"
                if d.get("passed")
                else "Reconciliation failed."
            )
        if stage=="Failure & recovery":
            d=read_json(RESULTS/"failure_recovery.json")
            return (
                f"producer unaffected  •  backlog "
                f"{int(d.get('backlog_left_in_log',0)):,} retained  •  "
                f"{int(d.get('events_redelivered',0)):,} redelivered"
            )
        if stage=="Replay":
            d=read_json(RESULTS/"replay_suite.json")
            return (
                f"late joiner saw {int(d.get('new_consumer_history',{}).get('events_consumed',0)):,} "
                f"events  •  reprocessing deterministic"
            )
        return ""

    def run_all(self):
        if self.running:
            messagebox.showinfo(
                "RetailMetrics",
                "A Session 2 stage is already running."
            )
            return

        if not self._require_connection():
            return

        # The visible and executable Pipeline order now both begin with the
        # durable-log self-test, matching the documentation/reference flow.
        # The first self-test is intentionally a PRE-PRODUCE readiness check.
        # Event-dependent guarantees are then validated against the actual
        # retained history immediately after Produce completes.
        # Session 1 handover remains a required hidden preflight.
        preflight = subprocess.run(
            [sys.executable, str(BASE / "handover_verify.py")],
            cwd=str(BASE), env=self._env(),
            capture_output=True, text=True
        )
        if preflight.stdout:
            self.console.insert("end", preflight.stdout + "\n")
        if preflight.stderr:
            self.console.insert("end", preflight.stderr + "\n")
        self.console.see("end")
        if preflight.returncode != 0:
            messagebox.showerror(
                "Session 1 handover failed",
                "Session 2 cannot start until the Session 1 dataset and batch output are present. See Console."
            )
            return

        order = [
            ("Log self-test", ["--pre"]),
            ("Produce", ["--reset"]),
            ("Consume", []),
            ("Reconcile", []),
            ("Failure & recovery", []),
            ("Replay", []),
        ]

        self.console.insert(
            "end",
            "\n" + "=" * 72 +
            "\nRUN EVERYTHING — RETAILMETRICS SESSION 2\n" +
            "=" * 72 + "\n"
            "Execution order:\n"
            "  1. Log self-test (pre-produce)\n"
            "  2. Produce (--reset) + post-produce guarantee validation\n"
            "  3. Consume\n"
            "  4. Reconcile\n"
            "  5. Failure & recovery\n"
            "  6. Replay\n\n"
        )
        self.console.see("end")

        def next_stage(index=0):
            if index >= len(order):
                self.running = False
                self._stop_live_status(True)
                self._refresh_artifacts()
                self.refresh_from_results()
                self.live_status_var.set(
                    "COMPLETED: all Session 2 stages passed."
                )
                self.live_elapsed_var.set("")
                self.console.insert(
                    "end",
                    "\n" + "=" * 72 +
                    "\nSESSION 2 PIPELINE COMPLETED SUCCESSFULLY\n" +
                    "=" * 72 + "\n"
                )
                self.console.see("end")
                return

            stage, args = order[index]
            self.running = True
            self._set_stage(stage, "running", "Running...")
            self._start_live_status(
                f"{stage} ({index + 1}/{len(order)})"
            )
            script = self._script_for(stage)

            def worker():
                code = 1
                try:
                    self._ensure_streaming_tables()

                    command = [
                        sys.executable,
                        str(BASE / script),
                        *args
                    ]

                    self.log_queue.put(
                        f"\n{'=' * 72}\n"
                        f"STAGE {index + 1}/{len(order)}: {stage}\n"
                        f"RUN: {' '.join(command[1:])}\n"
                        f"{'=' * 72}\n"
                    )

                    proc = subprocess.Popen(
                        command,
                        cwd=str(BASE),
                        env=self._env(),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1
                    )

                    if proc.stdout:
                        for line in proc.stdout:
                            self.log_queue.put(line)

                    code = proc.wait()

                    # When Produce succeeds, immediately validate the guarantees
                    # that require actual retained events. This keeps Log self-test
                    # first while avoiding false claims from an empty log.
                    if code == 0 and stage == "Produce":
                        post_command = [
                            sys.executable,
                            str(BASE / "self_test.py"),
                            "--post",
                        ]
                        self.log_queue.put(
                            "\nPOST-PRODUCE GUARANTEE VALIDATION\n"
                            f"RUN: {' '.join(post_command[1:])}\n"
                        )
                        post = subprocess.Popen(
                            post_command,
                            cwd=str(BASE),
                            env=self._env(),
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            bufsize=1
                        )
                        if post.stdout:
                            for line in post.stdout:
                                self.log_queue.put(line)
                        code = post.wait()

                except Exception as exc:
                    self.log_queue.put(
                        f"\nERROR while running {stage}: {exc}\n"
                    )

                def done():
                    ok = code == 0
                    self.running = False
                    self._stop_live_status(ok)

                    if ok:
                        self.stage_state[stage] = "passed"
                        self._set_stage(
                            stage,
                            "passed",
                            self._headline(stage)
                        )
                        self._refresh_views(stage)
                        self._refresh_artifacts()

                        if stage == "Produce":
                            final_test = read_json(RESULTS / "log_self_test.json")
                            if final_test.get("phase") == "post-produce" and final_test.get("overall_pass"):
                                self.stage_state["Log self-test"] = "passed"
                                self._set_stage(
                                    "Log self-test",
                                    "passed",
                                    "Pre-check PASS; all event-dependent guarantees PASS after Produce."
                                )
                                self._apply_self_test()

                        # Continue only after this stage has fully finished
                        # and its results have been loaded into the GUI.
                        self.after(
                            250,
                            lambda: next_stage(index + 1)
                        )
                    else:
                        self.stage_state[stage] = "failed"
                        self._set_stage(
                            stage,
                            "failed",
                            "Pipeline stopped. See Console for the error."
                        )
                        self.live_status_var.set(
                            f"FAILED: {stage}. Run everything stopped."
                        )
                        self.live_elapsed_var.set("")
                        self._refresh_artifacts()
                        self.console.insert(
                            "end",
                            f"\nRUN EVERYTHING STOPPED AT: {stage}\n"
                        )
                        self.console.see("end")

                self.after(0, done)

            threading.Thread(
                target=worker,
                daemon=True
            ).start()

        next_stage(0)

    def _refresh_views(self,stage):
        if stage=="Produce":
            self._apply_producer()
        elif stage=="Log self-test":
            self._apply_self_test()
        elif stage=="Consume":
            self._apply_consumers()
        elif stage=="Failure & recovery":
            self._apply_failure()
        elif stage=="Replay":
            self._apply_replay()
        elif stage=="Reconcile":
            self._apply_reconciliation()

    def _apply_producer(self):
        d=read_json(RESULTS/"producer_summary.json")
        if not d:
            return

        n=int(d.get("events_after",0) or 0)
        self.p_events.set(f"{n:,}")

        parts=d.get("partitions",[])
        values=[]
        labels=[]
        for row in parts:
            pid,count=int(row[0]),int(row[1])
            labels.append(f"partition {pid}")
            values.append(count)

        even=float(d.get("even_share",0) or 0)
        self._draw_bars(
            self.partition_chart,labels,values,
            even_share=even if even else None
        )

        for item in self.partition_tree.get_children():
            self.partition_tree.delete(item)

        total=sum(values) or 1
        maxv=max(values) if values else 0
        minv=min(values) if values else 0

        for label,count in zip(labels,values):
            share=count/total*100
            if count==maxv and values:
                observation="heaviest — sets the numerator of the skew"
            elif count==minv and values:
                observation="lightest — sets the denominator of the skew"
            elif count>=even:
                observation="above even share"
            else:
                observation="below even share"
            self.partition_tree.insert(
                "","end",
                values=(label,f"{count:,}",f"{share:.1f}%",observation)
            )

        self.durable_banner.set(
            f"{n:,} events produced in {float(d.get('elapsed_s',0)):.3f} s  •  "
            f"{float(d.get('events_per_sec',0)):,.0f} events/second  •  "
            f"log {float(d.get('log_size_mb',0)):.2f} MB  •  "
            f"skew {float(d.get('skew_ratio',0)):.2f} : 1  "
            f"(no consumer has to run for the events to remain durable)"
        )

        self.durable_explain.set(
            f"{n:,} Toy Store commerce events are mapped onto four logical partitions "
            f"by website_session_id. The measured skew ratio is "
            f"{float(d.get('skew_ratio',0)):.2f}:1. If each partition were assigned "
            f"to one consumer instance, the job would finish at the pace of the busiest partition."
        )

    def _apply_self_test(self):
        d=read_json(RESULTS/"log_self_test.json")
        for item in self.guarantee_tree.get_children():
            self.guarantee_tree.delete(item)
        for t in d.get("tests",[]):
            status=t.get("status")
            if not status:
                status="PASS" if t.get("pass") else "FAIL"
            self.guarantee_tree.insert(
                "","end",values=(t.get("guarantee"),status)
            )
        if d.get("phase") == "pre-produce" and d.get("overall_pass"):
            self.durable_banner.set(
                "Pre-produce self-test PASSED. Event-dependent checks are pending until Produce completes."
            )
        elif d.get("phase") == "post-produce" and d.get("overall_pass"):
            self.durable_banner.set(
                "Durable-log self-test PASSED — validated against actual retained events."
            )
        else:
            self.durable_banner.set("Durable-log self-test FAILED.")

    def _apply_consumers(self):
        d=read_json(RESULTS/"consumer_summary.json")
        if not d:
            return

        groups=d.get("groups",[])
        self.p_groups.set(str(len(groups)))
        self.p_lag.set(f"{int(d.get('total_lag',0) or 0):,}")

        for item in self.consumer_summary_tree.get_children():
            self.consumer_summary_tree.delete(item)

        labels=[]
        eps=[]

        for g in groups:
            short=g.get("group","").replace("-"," ")[:18]
            labels.append(short)
            eps.append(float(g.get("events_per_sec",0) or 0))

            self.consumer_summary_tree.insert(
                "","end",values=(
                    g.get("group"),
                    f"{int(g.get('processed',0)):,}",
                    f"{float(g.get('seconds',0)):.3f}",
                    f"{float(g.get('events_per_sec',0)):,.0f}",
                    f"{int(g.get('duplicates_skipped',0)):,}",
                    f"{int(g.get('final_lag',0)):,}",
                )
            )

        self._draw_bars(self.consumer_chart,labels,eps)

        if groups:
            fastest=max(groups,key=lambda x:float(x.get("events_per_sec",0)))
            slowest=min(groups,key=lambda x:float(x.get("events_per_sec",0)))
            self.consumer_banner.set(
                f"{len(groups)} groups finished  •  total lag "
                f"{int(d.get('total_lag',0)):,}  •  fastest "
                f"{fastest.get('group')} at {float(fastest.get('events_per_sec',0)):,.0f}/s  •  "
                f"slowest {slowest.get('group')} at "
                f"{float(slowest.get('events_per_sec',0)):,.0f}/s"
            )

        for item in self.consumer_offset_tree.get_children():
            self.consumer_offset_tree.delete(item)

        lag_path=RESULTS/"consumer_lag.csv"
        if lag_path.exists():
            with lag_path.open("r",encoding="utf-8",newline="") as f:
                for row in csv.DictReader(f):
                    self.consumer_offset_tree.insert(
                        "","end",values=(
                            row.get("group"),
                            row.get("partition"),
                            f"{int(row.get('end_offset') or 0):,}",
                            f"{int(row.get('committed') or 0):,}",
                            f"{int(row.get('lag') or 0):,}",
                        )
                    )

    def _apply_failure(self):
        d=read_json(RESULTS/"failure_recovery.json")
        if not d:
            return

        handled=int(d.get("failure_after_handled",0))
        backlog=int(d.get("backlog_left_in_log",d.get("lag_at_crash",0)))
        entries=int(d.get("total_records_written_unique", d.get("audit_entries_after_recovery",0)))
        redelivered=int(d.get("events_redelivered",0))

        self.fail_handled.set(f"{handled:,}")
        self.fail_backlog.set(f"{backlog:,}")
        self.fail_entries.set(f"{entries:,}")
        self.fail_redelivered.set(f"{redelivered:,}")

        committed_count=int(d.get("committed_event_count",0))
        recovered=int(d.get("events_processed_during_recovery",0))
        self.failure_banner.set(
            f"Crashed after handling {handled:,} events  •  "
            f"{committed_count:,} committed  •  backlog {backlog:,}  •  "
            f"recovered {recovered:,} events  •  "
            f"redelivered {redelivered:,}  •  final lag {int(d.get('final_lag',0)):,}"
        )

        for item in self.failure_blast_tree.get_children():
            self.failure_blast_tree.delete(item)

        for row in d.get("blast_radius",[]):
            self.failure_blast_tree.insert(
                "","end",values=(
                    row.get("component"),
                    row.get("status"),
                    row.get("evidence"),
                )
            )

    def _apply_replay(self):
        d=read_json(RESULTS/"replay_suite.json")
        if not d:
            return

        for item in self.replay_tree.get_children():
            self.replay_tree.delete(item)

        history=d.get("new_consumer_history",{})
        offline=d.get("offline_catch_up",{})
        partial=d.get("partial_replay",{})
        from_time=partial.get("from_time","")

        rows=(
            (
                "A new consumer reads all history",
                "It did not exist when the events were produced; it read from the retained beginning",
                f"{int(history.get('events_consumed',0)):,} consumed in "
                f"{float(history.get('seconds',0)):.4f} s"
            ),
            (
                "Rewind and reprocess",
                "Two runs over the retained history must produce identical results",
                f"identical = {d.get('deterministic_replay')}"
            ),
            (
                "An offline consumer catches up",
                "Nothing was asked of the producer; the events were waiting in the log",
                f"processed {int(offline.get('events_processed',0)):,}; "
                f"lag {int(offline.get('final_lag',0)):,}"
            ),
            (
                f"Partial replay from {from_time}",
                "Historical time ranges can be reprocessed without rebuilding the source database",
                f"{int(partial.get('events',0)):,} events "
                f"({float(partial.get('share_pct',0)):.1f}%)"
            ),
        )

        for row in rows:
            self.replay_tree.insert("","end",values=row)

        self.partial_replay_var.set(str(from_time))

        money=d.get("monetization",{})

        for item in self.replay_money_tree.get_children():
            self.replay_money_tree.delete(item)

        for source in money.get("traffic_sources",[]):
            sessions=int(source.get("sessions",0))
            conversions=int(source.get("conversions",0))
            rate=(conversions/sessions*100) if sessions else 0
            self.replay_money_tree.insert(
                "","end",values=(
                    source.get("source"),
                    f"{sessions:,}",
                    f"{conversions:,}",
                    f"{rate:.2f}%",
                    f"${float(source.get('revenue_usd',0)):,.2f}",
                )
            )

        self.replay_banner.set(
            f"All four demonstrations ran. Net revenue reconstructed by the late-joining "
            f"consumer: ${float(money.get('net_revenue_usd',0)):,.2f}"
        )

        self._apply_monetization(money)

    def _apply_reconciliation(self):
        d=read_json(RESULTS/"reconciliation_report.json")
        if not d:
            return

        passed=bool(d.get("passed"))
        self.p_pass.set("PASSED" if passed else "FAILED")

        diffs=d.get("max_differences",{})
        max_approx=max(
            float(diffs.get("session_duration_seconds",0) or 0),
            float(diffs.get("order_revenue_usd",0) or 0),
            float(diffs.get("gross_profit_usd",0) or 0),
        )

        self.rec_banner.set(
            (
                f"PASSED — {int(d.get('stream_groups',0)):,} sessions, "
                f"count difference {int(d.get('count_difference',0)):,}, "
                f"maximum approximate difference {max_approx:.3g} "
                f"against a tolerance of {float(d.get('tolerance',1e-6)):.0e}"
            )
            if passed
            else "FAILED — Session 2 does not reproduce Session 1."
        )

        for item in self.rec_tree.get_children():
            self.rec_tree.delete(item)

        rows=(
            (
                "Group sets identical",
                f"{int(d.get('batch_groups',0)):,} sessions",
                f"{int(d.get('stream_groups',0)):,} sessions",
                "identical" if d.get("group_sets_identical") else "different"
            ),
            (
                "Total session groups",
                f"{int(d.get('batch_groups',0)):,}",
                f"{int(d.get('stream_groups',0)):,}",
                f"{int(d.get('count_difference',0)):,} (exact)"
            ),
            (
                "Maximum difference in pageview count",
                "—","—",
                f"{float(diffs.get('pageview_count',0)):.12g}"
            ),
            (
                "Maximum difference in converted flag",
                "—","—",
                f"{float(diffs.get('converted',0)):.12g}"
            ),
            (
                "Maximum difference in numeric fields",
                "—","—",
                f"{max_approx:.12g}"
            ),
            (
                "Tolerance applied",
                "—","—",
                f"{float(d.get('tolerance',1e-6)):.0e}"
            ),
        )

        for row in rows:
            self.rec_tree.insert("","end",values=row)

        held=[
            bool(d.get("group_sets_identical")),
            float(diffs.get("pageview_count",1))==0
                and float(diffs.get("converted",1))==0,
            all(
                float(diffs.get(k,999))<=float(d.get("tolerance",1e-6))
                for k in (
                    "session_duration_seconds",
                    "order_revenue_usd",
                    "gross_profit_usd",
                )
            ),
            all(int(v)==0 for v in d.get("consumer_lag",{}).values())
                and len(d.get("consumer_lag",{}))>=3,
        ]

        for iid,ok in zip(self.ci_tree.get_children(),held):
            vals=list(self.ci_tree.item(iid,"values"))
            vals[2]="yes" if ok else "no"
            self.ci_tree.item(iid,values=vals)

    def _apply_monetization(self,m):
        self.mon_sessions.set(f"{int(m.get('sessions',0)):,}")
        self.mon_converted.set(f"{int(m.get('converted_sessions',0)):,}")
        self.mon_rate.set(f"{float(m.get('conversion_rate_pct',0)):.2f}%")
        self.mon_revenue.set(f"${float(m.get('gross_revenue_usd',0)):,.2f}")
        self.mon_cogs.set(f"${float(m.get('cogs_usd',0)):,.2f}")
        self.mon_profit.set(f"${float(m.get('gross_profit_usd',0)):,.2f}")
        self.mon_refunds.set(f"${float(m.get('refunds_usd',0)):,.2f}")
        self.mon_net.set(f"${float(m.get('net_revenue_usd',0)):,.2f}")

        for t in (self.mon_product_tree,self.mon_source_tree):
            for item in t.get_children():
                t.delete(item)

        for p in m.get("products",[]):
            self.mon_product_tree.insert(
                "","end",values=(
                    p.get("product_id"),
                    f"{int(p.get('orders',0)):,}",
                    f"${float(p.get('revenue_usd',0)):,.2f}",
                    f"${float(p.get('gross_profit_usd',0)):,.2f}",
                )
            )
        for s in m.get("traffic_sources",[]):
            sess=int(s.get("sessions",0))
            conv=int(s.get("conversions",0))
            rate=conv/sess*100 if sess else 0
            self.mon_source_tree.insert(
                "","end",values=(
                    s.get("source"),
                    f"{sess:,}",f"{conv:,}",f"{rate:.2f}%",
                    f"${float(s.get('revenue_usd',0)):,.2f}",
                )
            )

    def _drain(self):
        try:
            while True:
                msg=self.log_queue.get_nowait()
                self.console.insert("end",msg)
                self.console.see("end")
        except queue.Empty:
            pass
        self.after(120,self._drain)

if __name__=="__main__":
    app=RetailMetricsSession2GUI()
    app.mainloop()
