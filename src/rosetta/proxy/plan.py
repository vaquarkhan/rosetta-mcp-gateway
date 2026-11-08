"""Translation plan. Phase 1 masks and restores; it does not translate."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from rosetta.locking.entity_locker import EntityLocker
from rosetta.proxy.locale import is_english
from rosetta.types import TRANSLATABLE


@dataclass
class PlanItem:
    path: str
    translation_type: str
    original: str
    masked: str


@dataclass
class TranslationPlan:
    locale: str | None
    items: list[PlanItem] = field(default_factory=list)
    reconstructed: dict = field(default_factory=dict)


def build_plan(
    arguments: object,
    type_map: dict[str, str],
    locale: str | None,
    locker: EntityLocker,
) -> TranslationPlan:
    source = arguments if isinstance(arguments, dict) else {}
    reconstructed = copy.deepcopy(source)
    plan = TranslationPlan(locale=locale, reconstructed=reconstructed)
    if is_english(locale):
        return plan
    _walk(reconstructed, type_map, "", plan.items, locker)
    return plan


def _walk(
    node: object,
    type_map: dict[str, str],
    prefix: str,
    items: list[PlanItem],
    locker: EntityLocker,
) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            _visit(node, key, value, type_map, path, items, locker)
        return
    if isinstance(node, list):
        for index, value in enumerate(node):
            _visit_element(node, index, value, type_map, prefix, items, locker)


def _visit(
    parent: dict,
    key: str,
    value: object,
    type_map: dict[str, str],
    path: str,
    items: list[PlanItem],
    locker: EntityLocker,
) -> None:
    if isinstance(value, dict):
        _walk(value, type_map, path, items, locker)
        return
    if isinstance(value, list):
        _walk(value, type_map, path + "[]", items, locker)
        return
    replaced = _lock_text(value, type_map.get(path), path, items, locker)
    if replaced is not None:
        parent[key] = replaced


def _visit_element(
    parent: list,
    index: int,
    value: object,
    type_map: dict[str, str],
    path: str,
    items: list[PlanItem],
    locker: EntityLocker,
) -> None:
    if isinstance(value, dict):
        _walk(value, type_map, path, items, locker)
        return
    if isinstance(value, list):
        _walk(value, type_map, path, items, locker)
        return
    replaced = _lock_text(value, type_map.get(path), path, items, locker)
    if replaced is not None:
        parent[index] = replaced


def _lock_text(
    value: object,
    kind: str | None,
    path: str,
    items: list[PlanItem],
    locker: EntityLocker,
) -> str | None:
    if kind not in TRANSLATABLE or not isinstance(value, str):
        return None
    masked, originals = locker.mask(value)
    items.append(PlanItem(path=path, translation_type=kind, original=value, masked=masked))
    return locker.restore(masked, originals)
