from __future__ import annotations
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent

STAGES = [
    ("Session 1 handover verification", ["handover_verify.py"]),
    ("Initialize durable log", ["setup_streaming.py"]),
    ("Durable-log self-test (pre-produce)", ["self_test.py", "--pre"]),
    ("Produce durable events", ["produce_events.py", "--reset"]),
    ("Durable-log self-test (post-produce validation)", ["self_test.py", "--post"]),
    ("Consumer groups", ["consumers.py"]),
    ("Reconciliation", ["reconcile.py"]),
    ("Failure and recovery", ["failure_recovery.py"]),
    ("Replay", ["replay_suite.py"]),
]


def main():
    print("RETAILMETRICS SESSION 2 END-TO-END PIPELINE")
    print("=" * 72)
    for i, (label, args) in enumerate(STAGES, start=1):
        print(f"\n[{i}/{len(STAGES)}] {label}")
        print("-" * 72)
        proc = subprocess.run(
            [sys.executable, *[str(BASE / args[0])], *args[1:]],
            cwd=str(BASE),
        )
        if proc.returncode != 0:
            print(f"\nPIPELINE FAILED AT: {label}")
            raise SystemExit(proc.returncode)
    print("\n" + "=" * 72)
    print("SESSION 2 PIPELINE COMPLETED SUCCESSFULLY")

if __name__ == "__main__":
    main()
