"""Stdio transport. stdout is JSON-RPC only."""

from __future__ import annotations

import json
import sys

from rosetta.proxy.gateway import Gateway


def serve_stdio(gateway: Gateway, stdin=None, stdout=None) -> None:
    incoming = stdin if stdin is not None else sys.stdin
    outgoing = stdout if stdout is not None else sys.stdout
    for line in incoming:
        text = line.strip()
        if not text:
            continue
        try:
            message = json.loads(text)
        except json.JSONDecodeError:
            outgoing.write(json.dumps(_parse_error()) + "\n")
            outgoing.flush()
            continue
        result = gateway.handle(message, {})
        if result is None:
            continue
        outgoing.write(json.dumps(result, ensure_ascii=False) + "\n")
        outgoing.flush()


def _parse_error() -> dict:
    return {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
