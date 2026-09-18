from __future__ import annotations

import argparse
import filecmp
import importlib.resources
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROTO = ROOT / "retailmetrics_s3" / "proto" / "retailmetrics.proto"
GENERATED_NAMES = (
    "retailmetrics_pb2.py",
    "retailmetrics_pb2.pyi",
    "retailmetrics_pb2_grpc.py",
)


def generate(output_root: Path) -> None:
    grpc_include = importlib.resources.files("grpc_tools") / "_proto"
    command = [
        sys.executable,
        "-m",
        "grpc_tools.protoc",
        f"-I{ROOT}",
        f"-I{grpc_include}",
        f"--python_out={output_root}",
        f"--pyi_out={output_root}",
        f"--grpc_python_out={output_root}",
        PROTO.relative_to(ROOT).as_posix(),
    ]
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())


def verify() -> bool:
    with tempfile.TemporaryDirectory(prefix="retailmetrics-proto-") as folder:
        temporary = Path(folder)
        generate(temporary)
        expected_dir = ROOT / "retailmetrics_s3" / "proto"
        generated_dir = temporary / "retailmetrics_s3" / "proto"
        return all(
            (expected_dir / name).exists()
            and filecmp.cmp(expected_dir / name, generated_dir / name, shallow=False)
            for name in GENERATED_NAMES
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate or verify Session 3 protobuf stubs.")
    parser.add_argument("--check", action="store_true", help="Verify committed stubs without rewriting them.")
    args = parser.parse_args()
    if args.check:
        if not verify():
            print("Generated modules are missing or out of date.", file=sys.stderr)
            return 1
        print("Generated protobuf modules match retailmetrics.proto.")
        return 0
    generate(ROOT)
    print("Generated protobuf modules from retailmetrics.proto.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
