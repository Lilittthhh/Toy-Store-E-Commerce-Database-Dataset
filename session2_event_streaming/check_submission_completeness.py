from __future__ import annotations

import json
from pathlib import Path

import config as cfg

RESULTS = cfg.RESULTS


def load(name):
    path = RESULTS / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def exists(rel):
    return (Path(__file__).resolve().parent / rel).exists()


def main():
    checks = []

    def add(part, label, ok, evidence=""):
        checks.append((part, label, bool(ok), evidence))

    hand = load("handover_verification.json")
    enr = load("enrichment_report.json")
    prod = load("producer_summary.json")
    st = load("log_self_test.json")
    cons = load("consumer_summary.json")
    recov = load("failure_recovery.json")
    replay = load("replay_suite.json")
    recon = load("reconciliation_report.json")

    add(2, "Session 1 handover result exists", hand is not None, "results/handover_verification.json")
    add(2, "Session 1 handover passed", bool(hand and hand.get("passed")), "handover_verification.json")

    add(3, "Producer summary exists", prod is not None, "results/producer_summary.json")
    add(3, "Enrichment report exists", enr is not None, "results/enrichment_report.json")

    statuses = [x.get("status") for x in (st or {}).get("tests", [])]
    add(4, "Durable-log self-test exists", st is not None, "results/log_self_test.json")
    add(4, "All retained-event guarantees pass", bool(statuses) and all(s == "PASS" for s in statuses), "log_self_test.json")

    add(5, "Producer inserted events", bool(prod and int(prod.get("events_after", prod.get("events_inserted", 0))) > 0), "producer_summary.json")

    add(6, "Consumer summary exists", cons is not None, "results/consumer_summary.json")
    add(6, "Consumer lag report exists", (RESULTS / "consumer_lag.csv").exists(), "results/consumer_lag.csv")

    add(7, "At-least-once failure evidence exists", bool(recov and recov.get("delivery_semantic") == "at-least-once"), "failure_recovery.json")
    add(7, "Redelivery is non-zero", bool(recov and int(recov.get("events_redelivered", 0)) > 0), "failure_recovery.json")

    add(8, "Producer throughput recorded", bool(prod and prod.get("events_per_sec") is not None), "producer_summary.json")
    add(8, "Consumer final lag evidence recorded", cons is not None, "consumer_summary.json / consumer_lag.csv")

    add(9, "Failure isolation result exists", recov is not None, "results/failure_recovery.json")
    add(9, "No events lost", bool(recov and int(recov.get("events_lost", -1)) == 0), "failure_recovery.json")

    add(10, "Recovery reached final lag 0", bool(recov and int(recov.get("final_lag", -1)) == 0), "failure_recovery.json")
    add(10, "Unique records equal retained events", bool(recov and recov.get("total_records_written_unique") == recov.get("events_in_log")), "failure_recovery.json")

    add(11, "Replay suite exists", replay is not None, "results/replay_suite.json")
    add(11, "Deterministic replay passed", bool(replay and replay.get("deterministic_replay") is True), "replay_suite.json")
    add(11, "Partial replay recorded", bool(replay and (replay.get("partial_replay") or {}).get("events") is not None), "replay_suite.json")

    add(12, "Reconciliation report exists", recon is not None, "results/reconciliation_report.json")
    add(12, "Reconciliation PASSED", bool(recon and recon.get("passed") is True), "reconciliation_report.json")
    add(12, "Group sets identical", bool(recon and recon.get("group_sets_identical") is True), "reconciliation_report.json")
    add(12, "Group-count difference is zero", bool(recon and int(recon.get("count_difference", -1)) == 0), "reconciliation_report.json")

    add(13, "Architecture diagram exists", exists("architecture/architecture-session2.png") or exists("architecture_diagram.png"), "architecture/")
    add(15, "README exists", exists("README.md") or exists("README.txt"), "README")
    add(15, "End-to-end pipeline runner exists", exists("run_pipeline.py"), "run_pipeline.py")
    add(15, "Stream projection exists", (RESULTS / "stream_session_metrics.csv").exists(), "results/stream_session_metrics.csv")

    by_part = {}
    for part, label, ok, evidence in checks:
        by_part.setdefault(part, []).append(ok)

    print("SESSION 2 SUBMISSION COMPLETENESS CHECK")
    print("=" * 72)
    for part in sorted(by_part):
        ok = all(by_part[part])
        print(f"PART {part:<2}  {'PASS' if ok else 'CHECK'}")

    print("\nDETAILED CHECKS")
    print("-" * 72)
    failed = 0
    for part, label, ok, evidence in checks:
        if not ok:
            failed += 1
        print(f"[{'PASS' if ok else 'CHECK'}] Part {part}: {label}")
        if evidence:
            print(f"       evidence: {evidence}")

    manual = [
        "Part 1 personal/submission/repository fields",
        "Part 3 exact payload-schema table",
        "Part 5 written explanation of skew/event-time significance",
        "Part 7 line/function location for offset commits",
        "Part 8 fastest/slowest explanation",
        "Part 13 final repository paths + Session 3 handoff wording",
        "Part 14 personalized continuity plan",
        "Part 16 all 14 guide questions",
        "Part 17 Y/N checklist and evidence locations",
        "Part 18 AI-use disclosure, references, certification/signature/date",
    ]

    print("\nMANUAL FIELDS STILL REQUIRED")
    print("-" * 72)
    for item in manual:
        print(f"[MANUAL] {item}")

    print("\n" + "=" * 72)
    if failed == 0:
        print("AUTOMATED EVIDENCE CHECK: PASS")
        print("The measured/code evidence is present. Finish the manual fields before submission.")
    else:
        print(f"AUTOMATED EVIDENCE CHECK: {failed} ITEM(S) NEED ATTENTION")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
