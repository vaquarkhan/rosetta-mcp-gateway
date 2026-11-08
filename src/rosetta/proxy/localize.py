"""Translate English prose in a tool result back into the caller locale."""

from __future__ import annotations

import copy
import re

from rosetta.proxy.locale import is_english
from rosetta.translate.base import Translator

_ENUM = re.compile(r"^[A-Z][A-Z0-9_]*$")
_SQL = re.compile(r"^\s*(select|insert|update|delete|with)\b", re.IGNORECASE)
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def localize_payload(payload: dict | None, locale: str, translator: Translator) -> dict | None:
    if not isinstance(payload, dict) or is_english(locale):
        return payload
    cloned = copy.deepcopy(payload)
    if "result" in cloned:
        cloned["result"] = _walk(cloned["result"], locale, translator)
    error = cloned.get("error")
    if isinstance(error, dict) and isinstance(error.get("message"), str):
        error["message"] = _prose(error["message"], locale, translator)
    return cloned


def _walk(value, locale: str, translator: Translator):
    if isinstance(value, dict):
        return {key: _walk(item, locale, translator) for key, item in value.items()}
    if isinstance(value, list):
        return [_walk(item, locale, translator) for item in value]
    if isinstance(value, str):
        return _prose(value, locale, translator)
    return value


def _prose(text: str, locale: str, translator: Translator) -> str:
    stripped = text.strip()
    if not stripped or _ENUM.match(stripped) or _SQL.match(stripped) or _UUID.match(stripped):
        return text
    if stripped.startswith(("http://", "https://")):
        return text
    translated = translator.translate([text], "en", locale)
    if len(translated) != 1 or not isinstance(translated[0], str):
        return text
    return translated[0]
