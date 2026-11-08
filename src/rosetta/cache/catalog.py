"""SHA-256 tool pin. A repeated schema hash reuses the cached type map."""

from __future__ import annotations

from dataclasses import dataclass, field

from rosetta.classifier.schema import canonical_schema_hash, classify_tool


@dataclass
class ToolRecord:
    name: str
    schema_hash: str
    type_map: dict[str, str]
    quarantined: bool = False
    pending_hash: str | None = None
    pending_type_map: dict[str, str] | None = None


@dataclass
class Observation:
    record: ToolRecord
    cache: str


@dataclass
class Catalog:
    entity_locked_fields: set[str] = field(default_factory=set)
    tool_overrides: dict[str, dict[str, str]] = field(default_factory=dict)
    hits: int = 0
    misses: int = 0
    _maps: dict[str, dict[str, str]] = field(default_factory=dict)
    _by_name: dict[str, ToolRecord] = field(default_factory=dict)

    def observe(self, tool: dict) -> Observation:
        name = str(tool.get("name") or "")
        digest = canonical_schema_hash(tool)
        cached = self._maps.get(digest)
        if cached is None:
            self.misses += 1
            cached = classify_tool(
                tool,
                field_overrides=self.tool_overrides.get(name, {}),
                entity_locked_fields=self.entity_locked_fields,
            )
            self._maps[digest] = cached
            cache = "miss"
        else:
            self.hits += 1
            cache = "hit"

        current = self._by_name.get(name)
        if current is None:
            current = ToolRecord(name=name, schema_hash=digest, type_map=cached)
            self._by_name[name] = current
        elif current.schema_hash != digest:
            current.quarantined = True
            current.pending_hash = digest
            current.pending_type_map = cached
        return Observation(current, cache)

    def get(self, name: str) -> ToolRecord | None:
        return self._by_name.get(name)

    def accept(self, name: str) -> ToolRecord:
        record = self._by_name.get(name)
        if record is None:
            raise KeyError(name)
        if record.pending_hash and record.pending_type_map is not None:
            record.schema_hash = record.pending_hash
            record.type_map = record.pending_type_map
            record.pending_hash = None
            record.pending_type_map = None
        record.quarantined = False
        return record

    def snapshot(self) -> dict:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "tools": [
                {
                    "name": record.name,
                    "schema_hash": record.schema_hash,
                    "quarantined": record.quarantined,
                    "pending_hash": record.pending_hash,
                    "type_map": record.type_map,
                }
                for record in self._by_name.values()
            ],
        }
