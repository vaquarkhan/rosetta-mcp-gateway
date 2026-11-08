"""`python -m rosetta serve`."""

from __future__ import annotations

import argparse
import logging
import sys

import uvicorn

from rosetta.config import Settings, load_settings
from rosetta.proxy.gateway import Gateway
from rosetta.proxy.http_app import create_app
from rosetta.proxy.otel import configure_tracing
from rosetta.proxy.stdio import serve_stdio
from rosetta.proxy.upstream import BridgedUpstream, HttpUpstream


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="rosetta")
    parser.add_argument("command", nargs="?", default="serve", choices=["serve"])
    parser.add_argument("--stdio", action="store_true", help="read JSON-RPC from stdin")
    parser.add_argument("--http", action="store_true", help="serve Streamable HTTP on POST /mcp")
    parser.add_argument("--config", default=None, help="path to gateway.yaml (or MCP_GW_CONFIG)")
    args = parser.parse_args(argv)

    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    configure_tracing()
    settings = load_settings(args.config)
    gateway = Gateway(settings, build_upstream(settings))
    if args.http and not args.stdio:
        uvicorn.run(create_app(gateway), host=settings.host, port=settings.port, log_level="info")
        return
    serve_stdio(gateway)


def build_upstream(settings: Settings):
    inner = HttpUpstream(settings.upstream_url)
    if settings.upstream_protocol == "2025-11-25":
        return BridgedUpstream(inner, settings.upstream_protocol)
    return inner


if __name__ == "__main__":
    main()
