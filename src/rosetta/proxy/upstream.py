"""Upstream MCP transports."""

from __future__ import annotations

from typing import Protocol

import httpx


class Upstream(Protocol):
    def exchange(self, message: dict, headers: dict[str, str]) -> tuple[dict | None, dict]:
        """Return the JSON-RPC response and response headers."""


class HttpUpstream:
    def __init__(self, url: str, client: httpx.Client | None = None) -> None:
        self.url = url
        self._client = client or httpx.Client(timeout=30.0)

    def exchange(self, message: dict, headers: dict[str, str]) -> tuple[dict | None, dict]:
        outgoing = {
            "content-type": "application/json",
            "accept": "application/json, text/event-stream",
        }
        for key, value in headers.items():
            if key.lower() in {"content-length", "host"}:
                continue
            outgoing[key] = value
        method = message.get("method")
        if isinstance(method, str) and method:
            outgoing.setdefault("mcp-method", method)
        response = self._client.post(self.url, json=message, headers=outgoing)
        response.raise_for_status()
        response_headers = {key: value for key, value in response.headers.items()}
        if response.status_code == 202 or not response.content:
            return None, response_headers
        body = response.json()
        return (body if isinstance(body, dict) else None), response_headers


class BridgedUpstream:
    """Front a 2025-11-25 server that still requires initialize and a session id."""

    def __init__(self, inner: Upstream, protocol: str) -> None:
        self.inner = inner
        self.protocol = protocol
        self.session_id: str | None = None
        self._ready = protocol != "2025-11-25"

    def exchange(self, message: dict, headers: dict[str, str]) -> tuple[dict | None, dict]:
        forwarded = {key.lower(): value for key, value in headers.items()}
        method = message.get("method")
        if self.protocol == "2025-11-25" and not self._ready and method != "initialize":
            self._handshake(forwarded)
        if self.session_id:
            forwarded["mcp-session-id"] = self.session_id
        response, response_headers = self.inner.exchange(message, forwarded)
        if method == "initialize":
            session = _session_id(response_headers)
            if session:
                self.session_id = session
                self._ready = True
        return response, response_headers

    def _handshake(self, headers: dict[str, str]) -> None:
        initialize = {
            "jsonrpc": "2.0",
            "id": "rosetta-initialize",
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "rosetta", "version": "0.1.0"},
            },
        }
        _response, response_headers = self.inner.exchange(initialize, headers)
        self.session_id = _session_id(response_headers)
        notice_headers = dict(headers)
        if self.session_id:
            notice_headers["mcp-session-id"] = self.session_id
        self.inner.exchange(
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            notice_headers,
        )
        self._ready = True


def _session_id(headers: dict) -> str | None:
    for key, value in headers.items():
        if str(key).lower() == "mcp-session-id" and value:
            return str(value)
    return None
