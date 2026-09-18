from __future__ import annotations

import socket
import threading
import time
from concurrent import futures

import grpc
import uvicorn

from ..config import Settings
from ..service_core import RetailMetricsServiceCore
from .grpc_service import register_services
from .rest_app import create_rest_app


class ServiceHost:
    def __init__(self, cfg: Settings, core: RetailMetricsServiceCore):
        self.cfg = cfg
        self.core = core
        self.grpc_server: grpc.Server | None = None
        self.rest_server: uvicorn.Server | None = None
        self.rest_thread: threading.Thread | None = None

    def start(self, timeout: float = 10.0) -> None:
        if self.grpc_server is not None:
            return
        self.grpc_server = grpc.server(futures.ThreadPoolExecutor(max_workers=12))
        register_services(self.grpc_server, self.core)
        address = f"{self.cfg.grpc_host}:{self.cfg.grpc_port}"
        if self.grpc_server.add_insecure_port(address) == 0:
            raise RuntimeError(f"Could not bind gRPC to {address}")
        self.grpc_server.start()

        app = create_rest_app(self.core)
        config = uvicorn.Config(
            app, host=self.cfg.rest_host, port=self.cfg.rest_port,
            log_level="warning", access_log=False,
        )
        self.rest_server = uvicorn.Server(config)
        self.rest_thread = threading.Thread(target=self.rest_server.run, name="retailmetrics-rest", daemon=True)
        self.rest_thread.start()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                with socket.create_connection((self.cfg.rest_host, self.cfg.rest_port), timeout=0.2):
                    return
            except OSError:
                time.sleep(0.05)
        self.stop()
        raise RuntimeError("REST service did not become ready")

    def stop(self) -> None:
        if self.rest_server is not None:
            self.rest_server.should_exit = True
        if self.rest_thread is not None:
            self.rest_thread.join(timeout=5)
        if self.grpc_server is not None:
            self.grpc_server.stop(grace=1).wait(2)
        self.grpc_server = None
        self.rest_server = None
        self.rest_thread = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.stop()

