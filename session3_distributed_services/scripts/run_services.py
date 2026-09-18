from __future__ import annotations

import signal
import sys
import threading
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from retailmetrics_s3.config import settings
from retailmetrics_s3.experiments.pipeline import Session3Runtime


def main() -> int:
    runtime = Session3Runtime(settings()); runtime.start_services(); stopped = threading.Event()
    def stop(*_args): stopped.set()
    signal.signal(signal.SIGINT, stop); signal.signal(signal.SIGTERM, stop)
    print("RetailMetrics Session 3 services are running. Press Ctrl+C to stop.")
    try: stopped.wait()
    finally: runtime.stop()
    return 0


if __name__ == "__main__": raise SystemExit(main())
