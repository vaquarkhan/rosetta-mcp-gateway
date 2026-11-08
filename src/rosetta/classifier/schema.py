"""Deterministic translation-type assignment for MCP tool schemas."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator

from rosetta.types import TranslationType

IMMUTABLE_TYPES = {"boolean", "integer", "number", "null"}
IMMUTABLE_FORMATS = {"uuid", "date", "date-time", "uri", "iri", "email"}
IMMUTABLE_KEYS = {"id", "uuid", "url", "uri", "path", "href"}
CODE_KEYS = {"sql", "graphql", "jsonpath", "bash", "shell", "script"}
CODE_FORMATS = {"sql", "graphql", "jsonpath"}


def canonical_schema_hash(tool: dict) -> str:
    """SHA-256 of the tool definition. Any silent change is a new pin."""
    blob = json.dumps(tool, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def classify_tool(
    tool: dict,
    *,
    field_overrides: dict[str, str] | None = None,
    entity_locked_fields: set[str] | None = None,
) -> dict[str, str]:
    """Return dotted path to translation type for every inputSchema leaf."""
    overrides = field_overrides or {}
    locked_keys = entity_locked_fields or set()
    schema = tool.get("inputSchema") if isinstance(tool.get("inputSchema"), dict) else {}
    type_map: dict[str, str] = {}
    for path, key, node in _leaves(schema):
        type_map[path] = _classify_leaf(path, key, node, overrides, locked_keys).value
    return type_map


def _leaves(schema: dict, prefix: str = "") -> Iterator[tuple[str, str, dict]]:
    properties = schema.get("properties") if isinstance(schema, dict) else None
    if not isinstance(properties, dict):
        return
    for key, node in properties.items():
        if not isinstance(node, dict):
            continue
        path = f"{prefix}.{key}" if prefix else key
        yield from _walk(str(key), node, path)


def _walk(key: str, node: dict, path: str) -> Iterator[tuple[str, str, dict]]:
    if _is_object(node):
        yield from _leaves(node, path)
        return
    if _is_array(node):
        items = node.get("items") if isinstance(node.get("items"), dict) else {}
        item_path = path + "[]"
        if _is_object(items):
            yield from _leaves(items, item_path)
        else:
            yield item_path, key, items
        return
    yield path, key, node


def _is_object(node: dict) -> bool:
    return node.get("type") == "object" or isinstance(node.get("properties"), dict)


def _is_array(node: dict) -> bool:
    return node.get("type") == "array" or "items" in node


def _classify_leaf(
    path: str,
    key: str,
    node: dict,
    overrides: dict[str, str],
    locked_keys: set[str],
) -> TranslationType:
    if path in overrides:
        return TranslationType(overrides[path])
    if "enum" in node:
        return TranslationType.IMMUTABLE
    declared = _single_type(node.get("type"))
    if declared in IMMUTABLE_TYPES:
        return TranslationType.IMMUTABLE
    if node.get("format") in IMMUTABLE_FORMATS:
        return TranslationType.IMMUTABLE
    if key in IMMUTABLE_KEYS or key.endswith("_id") or (len(key) > 2 and key.endswith("Id")):
        return TranslationType.IMMUTABLE
    if _is_code(key, node):
        return TranslationType.CODE_SYNTAX
    if node.get("x-rosetta-type") == "entity" or key in locked_keys:
        return TranslationType.ENTITY_LOCKED
    if node.get("x-rosetta-type") == "immutable":
        return TranslationType.IMMUTABLE
    if declared in (None, "string") or node.get("x-rosetta-type") == "free_text":
        return TranslationType.FREE_TEXT
    return TranslationType.IMMUTABLE


def _single_type(declared: object) -> str | None:
    if isinstance(declared, str):
        return declared
    if isinstance(declared, list):
        non_null = [item for item in declared if item != "null"]
        if len(non_null) == 1 and isinstance(non_null[0], str):
            return non_null[0]
    return None


def _is_code(key: str, node: dict) -> bool:
    if node.get("x-rosetta-type") == "code":
        return True
    if node.get("format") in CODE_FORMATS:
        return True
    media = str(node.get("contentMediaType") or "")
    if "sql" in media or "graphql" in media:
        return True
    return key in CODE_KEYS or key.endswith(("_sql", "_graphql", "_jsonpath"))
