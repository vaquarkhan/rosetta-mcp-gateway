"""Locale negotiation. Language identification arrives in Phase 2."""

from __future__ import annotations


def resolve_locale(message: dict, headers: dict[str, str]) -> str | None:
    """Prefer `_meta.locale`, then `X-MCP-Locale`, then `Accept-Language`."""
    meta = _meta(message)
    locale = meta.get("locale")
    if isinstance(locale, str) and locale.strip():
        return locale.strip()
    header_locale = _header(headers, "x-mcp-locale")
    if header_locale:
        return header_locale
    accept = _header(headers, "accept-language")
    if accept:
        first = accept.split(",")[0].split(";")[0].strip()
        return first or None
    return None


def is_english(locale: str | None) -> bool:
    if not locale:
        return False
    normalized = locale.strip().lower().replace("_", "-")
    return normalized == "en" or normalized.startswith("en-")


def _meta(message: dict) -> dict:
    merged: dict = {}
    top = message.get("_meta")
    if isinstance(top, dict):
        merged.update(top)
    params = message.get("params")
    if isinstance(params, dict) and isinstance(params.get("_meta"), dict):
        merged.update(params["_meta"])
    return merged


def _header(headers: dict[str, str], name: str) -> str | None:
    for key, value in headers.items():
        if key.lower() == name and isinstance(value, str) and value.strip():
            return value.strip()
    return None
