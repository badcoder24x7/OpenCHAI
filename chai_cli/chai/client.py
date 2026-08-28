"""
CHAI CLI — API client
──────────────────────
Thin wrapper around `requests` that talks to the OpenCHAI GUI FastAPI
backend. Every CLI command goes through this client so auth headers,
error handling, and base-URL resolution live in exactly one place.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Union

import requests

JsonType = Union[Dict[str, Any], List[Any], None]


class ChaiError(Exception):
    """Base class for all CLI/API failures."""


class ChaiConnectionError(ChaiError):
    """Raised when the backend could not be reached at all (network/DNS/refused)."""

    def __init__(self, base_url: str, original: Exception):
        self.base_url = base_url
        self.original = original
        super().__init__(f"Could not reach OpenCHAI backend at {base_url}: {original}")


class ChaiAPIError(ChaiError):
    """Raised when the backend responded with a non-2xx status code."""

    def __init__(self, status_code: int, detail: Any, method: str, path: str):
        self.status_code = status_code
        self.detail = detail
        self.method = method
        self.path = path
        msg = detail if isinstance(detail, str) else json.dumps(detail, default=str)
        super().__init__(f"{method} {path} -> HTTP {status_code}: {msg}")


class ChaiClient:
    """Small synchronous HTTP client for the OpenCHAI GUI backend."""

    def __init__(
        self,
        base_url: str,
        token: Optional[str] = None,
        verify_ssl: bool = True,
        timeout: int = 30,
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.session = requests.Session()

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_body: JsonType = None,
        timeout: Optional[int] = None,
    ) -> JsonType:
        url = f"{self.base_url}{path}"
        # Drop None-valued query params so callers can pass optional filters directly.
        clean_params = None
        if params is not None:
            clean_params = {k: v for k, v in params.items() if v is not None}

        try:
            resp = self.session.request(
                method=method.upper(),
                url=url,
                headers=self._headers(),
                params=clean_params,
                json=json_body,
                timeout=timeout or self.timeout,
                verify=self.verify_ssl,
            )
        except requests.exceptions.RequestException as exc:
            raise ChaiConnectionError(self.base_url, exc) from exc

        if resp.status_code == 204 or not resp.content:
            body: JsonType = None
        else:
            try:
                body = resp.json()
            except ValueError:
                body = resp.text  # type: ignore[assignment]

        if not resp.ok:
            detail: Any
            if isinstance(body, dict) and "detail" in body:
                detail = body["detail"]
            elif body:
                detail = body
            else:
                detail = resp.reason
            raise ChaiAPIError(resp.status_code, detail, method.upper(), path)

        return body

    def get(self, path: str, params: Optional[Dict[str, Any]] = None, timeout: Optional[int] = None) -> JsonType:
        return self.request("GET", path, params=params, timeout=timeout)

    def post(
        self,
        path: str,
        json_body: JsonType = None,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None,
    ) -> JsonType:
        return self.request("POST", path, json_body=json_body, params=params, timeout=timeout)

    def put(
        self,
        path: str,
        json_body: JsonType = None,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None,
    ) -> JsonType:
        return self.request("PUT", path, json_body=json_body, params=params, timeout=timeout)

    def delete(
        self,
        path: str,
        json_body: JsonType = None,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None,
    ) -> JsonType:
        return self.request("DELETE", path, json_body=json_body, params=params, timeout=timeout)
