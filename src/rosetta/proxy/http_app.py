"""Streamable HTTP entrypoint."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from rosetta.proxy.gateway import Gateway


def create_app(gateway: Gateway) -> FastAPI:
    app = FastAPI(title="Rosetta MCP Gateway", version="0.1.0")
    app.state.gateway = gateway

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> dict:
        return {"status": "ready"}

    @app.get("/catalog")
    def catalog() -> dict:
        return gateway.catalog.snapshot()

    @app.post("/catalog/accept")
    async def accept(request: Request) -> dict:
        body = await request.json()
        name = body.get("name") if isinstance(body, dict) else None
        if not isinstance(name, str) or not name:
            raise HTTPException(status_code=400, detail="name is required")
        try:
            record = gateway.catalog.accept(name)
        except KeyError:
            raise HTTPException(status_code=404, detail="unknown tool") from None
        return {
            "name": record.name,
            "schema_hash": record.schema_hash,
            "quarantined": record.quarantined,
        }

    @app.post("/mcp")
    async def mcp(request: Request):
        headers = {key.lower(): value for key, value in request.headers.items()}
        try:
            message = await request.json()
        except Exception:
            return JSONResponse(_parse_error(), status_code=400)
        if not isinstance(message, dict):
            return JSONResponse(_parse_error(), status_code=400)
        result = gateway.handle(message, headers)
        if result is None:
            return Response(status_code=202)
        return JSONResponse(result)

    return app


def _parse_error() -> dict:
    return {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
