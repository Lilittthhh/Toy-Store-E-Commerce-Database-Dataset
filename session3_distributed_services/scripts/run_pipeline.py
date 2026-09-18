from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from retailmetrics_s3.artifacts import write_text
from retailmetrics_s3.config import RESULTS
from retailmetrics_s3.config import settings
from retailmetrics_s3.experiments.pipeline import Session3Runtime


def main() -> int:
    transcript: list[str] = []

    def emit(message: str) -> None:
        transcript.append(message)
        print(message)

    runtime = Session3Runtime(settings(), emit=emit)
    try:
        results = runtime.run_all()
        summary = json.dumps(
            {
                "stages": list(results),
                "passed": results["reconciliation"]["passed"]
                and results["safety"]["unchanged"],
            },
            indent=2,
        )
        emit(summary)
        return 0
    except Exception as exc:
        emit(f"PIPELINE FAILED: {type(exc).__name__}: {exc}")
        raise
    finally:
        write_text(RESULTS / "pipeline_transcript.txt", "\n".join(transcript) + "\n")


if __name__ == "__main__": raise SystemExit(main())
