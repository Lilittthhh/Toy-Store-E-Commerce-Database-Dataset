from __future__ import annotations

import os
from typing import Any

import httpx
from dotenv import load_dotenv

from core.config import APP_ROOT


load_dotenv(APP_ROOT / ".env", override=False)


class APIError(RuntimeError):
    def __init__(self, status_code: int, message: str, details: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.details = details


def _error_message(payload: Any, fallback: str) -> tuple[str, Any]:
    if not isinstance(payload, dict) or "detail" not in payload:
        return fallback, payload
    detail = payload["detail"]
    if isinstance(detail, str):
        return detail, detail
    if isinstance(detail, list):
        messages = []
        for item in detail:
            if isinstance(item, dict):
                location = ".".join(str(part) for part in item.get("loc", [])[1:])
                text = item.get("msg", "Invalid value")
                messages.append(f"{location}: {text}" if location else text)
        return "; ".join(messages) or fallback, detail
    return str(detail), detail


class APIClient:
    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        configured_url = base_url or os.getenv("API_BASE_URL") or "http://localhost:8000"
        if "HOST_IP" in configured_url:
            raise RuntimeError(
                "API_BASE_URL still contains HOST_IP. Start with RUN_WEB.bat or set it "
                "to http://<this-computer's-LAN-IPv4>:8000."
            )
        self.base_url = configured_url.rstrip("/")
        self.token = token
        self.transport = transport

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            with httpx.Client(
                base_url=self.base_url,
                headers=headers,
                timeout=10,
                transport=self.transport,
            ) as client:
                response = client.request(method, path, params=params, json=json)
        except httpx.RequestError as exc:
            raise APIError(0, "Cannot reach the RetailMetrics service. Confirm the application is running.") from exc

        if response.is_error:
            try:
                payload = response.json()
            except ValueError:
                payload = None
            message, details = _error_message(payload, f"API request failed with HTTP {response.status_code}.")
            raise APIError(response.status_code, message, details)
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self.request("GET", path, params=params)

    def post(self, path: str, payload: dict[str, Any] | None = None) -> Any:
        return self.request("POST", path, json=payload)

    def put(self, path: str, payload: dict[str, Any]) -> Any:
        return self.request("PUT", path, json=payload)

    def delete(self, path: str, params: dict[str, Any]) -> Any:
        return self.request("DELETE", path, params=params)
