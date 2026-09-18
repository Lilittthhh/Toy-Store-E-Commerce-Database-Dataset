# RetailMetrics Session 3 — Distributed Services

This session compares three call paths over one immutable RetailMetrics service core: an in-process adapter, REST with compact JSON, and gRPC with real Protocol Buffers. All PostgreSQL connections are transaction-level read-only. Mutable business data is read through the `canonical_*` views; no Session 3 code writes to PostgreSQL, the original CSV files, or Sessions 1 and 2.

## Isolated setup

From `session3_distributed_services`:

```powershell
C:\Users\ureha\AppData\Local\Programs\Python\Python311\python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set only the local PostgreSQL values in `.env`. Keep the REST and gRPC hosts at `127.0.0.1`. Never commit `.env`.

## Contract build

`GENERATE_PROTO.bat` is the development/build action that regenerates committed Python modules from `retailmetrics.proto`. To verify without rewriting source files:

```powershell
.\.venv\Scripts\python.exe scripts\generate_proto.py --check
```

The GUI deliberately offers only contract validation and generated-module verification; it cannot regenerate stubs at runtime.

## Run order

```powershell
RUN_TESTS.bat
RUN_PIPELINE.bat
RUN_GUI.bat
```

Alternatively, run `.\.venv\Scripts\python.exe gui.py`. `RUN_SERVICES.bat` starts only the loopback REST (`127.0.0.1:8100`) and gRPC (`127.0.0.1:50051`) endpoints for inspection. Stop it with Ctrl+C.

The pipeline writes measured evidence only to `results/`. Benchmark values vary by machine and run. The reports do not assert that gRPC is always faster: payload size, local latency, round-trip count, total completion time, and streaming time to first usable result are separate observations.

## GUI tabs

The Tkinter console has eight tabs: Pipeline, Contract, Payload size, Latency, Round trips & streaming, Adapter swap, Reconciliation, and Console. Every benchmark begins as **Not run** and is populated only after a real experiment. The Console tab can save an additional timestamped transcript.

## Safety and reconciliation

- PostgreSQL must remain localhost-only.
- Repository connections use `READ ONLY` and `REPEATABLE READ`; a SQL guard rejects non-read statements before execution.
- `database_safety.json` compares protected table and canonical-view counts before and after the pipeline.
- Session 1 and Session 2 artifacts are loaded as files only; their executable modules are never imported.
- `reconciliation_report.json` compares all 472,871 per-session records plus the Session 2 refund total.

If the GUI reports an `init.tcl` error, repair/reinstall the local Python Tcl/Tk optional component. This is an interpreter installation issue; the service pipeline and tests remain command-line runnable.
