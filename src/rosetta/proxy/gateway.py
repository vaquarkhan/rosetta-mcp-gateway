"""Request path for Phase 1: classify, pin, plan, forward. No translation."""

from __future__ import annotations

import copy

from rosetta.cache.catalog import Catalog
from rosetta.config import Settings
from rosetta.locking.entity_locker import EntityLocker
from rosetta.proxy.locale import is_english, resolve_locale
from rosetta.proxy.otel import tracer
from rosetta.proxy.plan import TranslationPlan, build_plan
from rosetta.proxy.upstream import Upstream
from rosetta.types import TRANSLATABLE

BYPASS_METHODS = {"ping", "notifications/initialized", "notifications/cancelled"}
LOCALE_REQUIRED = -32602
CATALOG_QUARANTINE = -32001


class Gateway:
    def __init__(self, settings: Settings, upstream: Upstream) -> None:
        self.settings = settings
        self.upstream = upstream
        self.catalog = Catalog(
            entity_locked_fields=set(settings.entity_locked_fields),
            tool_overrides=settings.tool_overrides,
        )
        self.locker = EntityLocker(settings.glossary)
        self.last_plan: TranslationPlan | None = None

    def handle(self, message: dict, headers: dict[str, str] | None = None) -> dict | None:
        headers = headers or {}
        if not isinstance(message, dict):
            return _error(None, -32700, "parse error")
        method = _method(message, headers)
        request_id = message.get("id")
        with tracer().start_as_current_span("mcp.request") as span:
            span.set_attribute("mcp.method", method)
            span.set_attribute("mcp.server", self.settings.upstream_name)
            if method in BYPASS_METHODS or method.startswith("notifications/"):
                span.set_attribute("rosetta.cache", "bypass")
                response, _headers = self.upstream.exchange(message, headers)
                return None if method.startswith("notifications/") else response
            if method == "tools/list":
                return self._tools_list(message, headers, span)
            if method == "tools/call":
                return self._tools_call(message, headers, span, request_id)
            span.set_attribute("rosetta.cache", "bypass")
            response, _headers = self.upstream.exchange(message, headers)
            return response

    def _tools_list(self, message: dict, headers: dict[str, str], span) -> dict | None:
        response, _headers = self.upstream.exchange(message, headers)
        caches: list[str] = []
        tools = (response or {}).get("result", {}).get("tools") if isinstance(response, dict) else None
        if isinstance(tools, list):
            for tool in tools:
                if isinstance(tool, dict):
                    caches.append(self.catalog.observe(tool).cache)
        span.set_attribute("rosetta.cache", "miss" if "miss" in caches else "hit" if caches else "bypass")
        return response

    def _tools_call(self, message: dict, headers: dict[str, str], span, request_id) -> dict | None:
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        name = params.get("name") or _header(headers, "mcp-name") or ""
        name = str(name)
        record = self.catalog.get(name)
        if record is None and name:
            self._bootstrap(headers)
            record = self.catalog.get(name)
        if record is None:
            span.set_attribute("rosetta.cache", "bypass")
            response, _headers = self.upstream.exchange(message, headers)
            return response
        span.set_attribute("mcp.tool", name)
        if record.quarantined:
            span.set_attribute("rosetta.cache", "quarantine")
            return _error(
                request_id,
                CATALOG_QUARANTINE,
                "catalog quarantine",
                {"code": "CATALOG_QUARANTINE", "tool": name},
            )
        if not _needs_translation(record.type_map):
            span.set_attribute("rosetta.cache", "bypass")
            response, _headers = self.upstream.exchange(message, headers)
            return response

        locale = resolve_locale(message, headers)
        if locale is None:
            span.set_attribute("rosetta.cache", "bypass")
            return _error(
                request_id,
                LOCALE_REQUIRED,
                "locale required",
                {"code": "LOCALE_REQUIRED"},
            )

        arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        plan = build_plan(arguments, record.type_map, locale, self.locker)
        self.last_plan = plan
        span.set_attribute("rosetta.locale", locale)
        span.set_attribute("rosetta.plan_items", len(plan.items))
        span.set_attribute("rosetta.cache", "passthrough" if is_english(locale) else "plan")

        forwarded = copy.deepcopy(message)
        forwarded_params = forwarded.setdefault("params", {})
        if isinstance(forwarded_params, dict):
            forwarded_params["arguments"] = plan.reconstructed
        response, _headers = self.upstream.exchange(forwarded, headers)
        return response

    def _bootstrap(self, headers: dict[str, str]) -> None:
        response, _headers = self.upstream.exchange(
            {"jsonrpc": "2.0", "id": "rosetta-bootstrap", "method": "tools/list", "params": {}},
            headers,
        )
        tools = (response or {}).get("result", {}).get("tools") if isinstance(response, dict) else None
        if isinstance(tools, list):
            for tool in tools:
                if isinstance(tool, dict):
                    self.catalog.observe(tool)


def _needs_translation(type_map: dict[str, str]) -> bool:
    return any(kind in TRANSLATABLE for kind in type_map.values())


def _method(message: dict, headers: dict[str, str]) -> str:
    body = message.get("method")
    if isinstance(body, str) and body:
        return body
    return _header(headers, "mcp-method") or ""


def _header(headers: dict[str, str], name: str) -> str:
    for key, value in headers.items():
        if key.lower() == name and isinstance(value, str):
            return value
    return ""


def _error(request_id, code: int, message: str, data: dict | None = None) -> dict:
    error = {"code": code, "message": message}
    if data:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}
