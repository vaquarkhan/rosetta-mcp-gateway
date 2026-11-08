"""Classify, pin, translate free text into English, and forward."""

from __future__ import annotations

import copy

from rosetta.cache.catalog import Catalog
from rosetta.config import Settings
from rosetta.locking.entity_locker import EntityLocker
from rosetta.proxy.locale import is_english, resolve_locale
from rosetta.proxy.localize import localize_payload
from rosetta.proxy.otel import tracer
from rosetta.proxy.plan import TranslationPlan, build_plan
from rosetta.proxy.upstream import Upstream
from rosetta.security.bastion import BastionUnavailable, screen_texts
from rosetta.translate.base import TranslationError, Translator
from rosetta.types import TRANSLATABLE

BYPASS_METHODS = {"ping", "notifications/initialized", "notifications/cancelled"}
LOCALE_REQUIRED = -32602
CATALOG_QUARANTINE = -32001
TRANSLATION_FAILED = -32002
BASTION_DENIED = -32003
BASTION_UNAVAILABLE = -32004


class Gateway:
    def __init__(self, settings: Settings, upstream: Upstream, translator: Translator | None = None) -> None:
        self.settings = settings
        self.upstream = upstream
        self.catalog = Catalog(
            entity_locked_fields=set(settings.entity_locked_fields),
            tool_overrides=settings.tool_overrides,
        )
        self.locker = EntityLocker(settings.glossary)
        self.translator = translator
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
        try:
            plan = build_plan(
                arguments,
                record.type_map,
                locale,
                self.locker,
                translator=self.translator,
                target=self.settings.translation_target,
            )
        except TranslationError as exc:
            span.set_attribute("rosetta.cache", "translation_failed")
            return _error(
                request_id,
                TRANSLATION_FAILED,
                "translation failed",
                {"code": "TRANSLATION_FAILED", "detail": str(exc)},
            )
        self.last_plan = plan
        if self.settings.security_bastion:
            denied = _bastion_error(request_id, plan)
            if denied is not None:
                span.set_attribute("rosetta.cache", denied["error"]["data"]["code"].lower())
                return denied
        span.set_attribute("rosetta.locale", locale)
        span.set_attribute("rosetta.plan_items", len(plan.items))
        span.set_attribute("rosetta.translated", self.translator is not None and not is_english(locale))
        span.set_attribute("rosetta.cache", "passthrough" if is_english(locale) else "plan")

        forwarded = copy.deepcopy(message)
        forwarded_params = forwarded.setdefault("params", {})
        if isinstance(forwarded_params, dict):
            forwarded_params["arguments"] = plan.reconstructed
        response, _headers = self.upstream.exchange(forwarded, headers)
        if self.translator is not None and isinstance(response, dict) and not is_english(locale):
            try:
                response = localize_payload(response, locale, self.translator)
            except TranslationError as exc:
                return _error(
                    request_id,
                    TRANSLATION_FAILED,
                    "translation failed",
                    {"code": "TRANSLATION_FAILED", "detail": str(exc)},
                )
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


def _bastion_error(request_id, plan: TranslationPlan) -> dict | None:
    try:
        match = screen_texts(_screen_inputs(plan))
    except BastionUnavailable as exc:
        return _error(
            request_id,
            BASTION_UNAVAILABLE,
            "bastion unavailable",
            {"code": "BASTION_UNAVAILABLE", "detail": str(exc)},
        )
    if match:
        return _error(request_id, BASTION_DENIED, "request denied", {"code": "BASTION_DENIED"})
    return None


def _screen_inputs(plan: TranslationPlan) -> list[str]:
    texts: list[str] = []
    for item in plan.items:
        if item.original:
            texts.append(item.original)
        if item.translated and item.translated != item.original:
            texts.append(item.translated)
    if not texts:
        texts.extend(_strings(plan.reconstructed))
    return texts


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        found: list[str] = []
        for item in value.values():
            found.extend(_strings(item))
        return found
    if isinstance(value, list):
        found = []
        for item in value:
            found.extend(_strings(item))
        return found
    return []


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
