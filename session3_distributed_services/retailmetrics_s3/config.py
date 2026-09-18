from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
RESULTS = ROOT / "results"
SESSION1_RESULTS = PROJECT_ROOT / "session1_parallel_compute" / "results"
SESSION2_RESULTS = PROJECT_ROOT / "session2_event_streaming" / "results"

load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    pg_host: str = os.getenv("RETAILMETRICS_PG_HOST", "localhost")
    pg_port: int = int(os.getenv("RETAILMETRICS_PG_PORT", "5432"))
    pg_database: str = os.getenv("RETAILMETRICS_PG_DATABASE", "retailmetrics")
    pg_user: str = os.getenv("RETAILMETRICS_PG_USER", "postgres")
    pg_password: str = os.getenv("RETAILMETRICS_PG_PASSWORD", "")
    rest_host: str = os.getenv("SESSION3_REST_HOST", "127.0.0.1")
    rest_port: int = int(os.getenv("SESSION3_REST_PORT", "8100"))
    grpc_host: str = os.getenv("SESSION3_GRPC_HOST", "127.0.0.1")
    grpc_port: int = int(os.getenv("SESSION3_GRPC_PORT", "50051"))
    warmups: int = int(os.getenv("SESSION3_BENCHMARK_WARMUPS", "15"))
    calls: int = int(os.getenv("SESSION3_BENCHMARK_CALLS", "100"))
    batch_rows: int = int(os.getenv("SESSION3_BATCH_ROWS", "50"))
    stream_rows: int = int(os.getenv("SESSION3_STREAM_ROWS", "5000"))

    def validate(self) -> None:
        if self.rest_host != "127.0.0.1" or self.grpc_host != "127.0.0.1":
            raise ValueError("Session 3 REST and gRPC must bind to 127.0.0.1 only.")
        if self.pg_host not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Session 3 PostgreSQL access must remain localhost-only.")
        for name in ("warmups", "calls", "batch_rows", "stream_rows"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")


def settings() -> Settings:
    value = Settings()
    value.validate()
    RESULTS.mkdir(exist_ok=True)
    return value

