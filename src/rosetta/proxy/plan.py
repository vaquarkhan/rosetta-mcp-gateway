"""Build a translation plan and rewrite only free-text leaves."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field

from rosetta.locking.entity_locker import EntityLocker
from rosetta.proxy.locale import is_english
from rosetta.translate.base import TranslationError, Translator
from rosetta.types import TRANSLATABLE, TranslationType

_LOCK = re.compile(r"«L:\d+:»")


@dataclass
class PlanItem:
    path: str
    translation_type: str
    original: str
    masked: str
    translated: str


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
    translator: Translator | None = None,
    target: str = "en",
) -> TranslationPlan:
    source = arguments if isinstance(arguments, dict) else {}
    reconstructed = copy.deepcopy(source)
    plan = TranslationPlan(locale=locale, reconstructed=reconstructed)
    if is_english(locale):
        return plan
    _walk(reconstructed, "", plan.items, type_map, locker, translator, locale or "", target)
    return plan


def _walk(
    node: object,
    prefix: str,
    items: list[PlanItem],
    type_map: dict[str, str],
    locker: EntityLocker,
    translator: Translator | None,
    locale: str,
    target: str,
) -> None:
    if isinstance(node, dict):
        for key, value in list(node.items()):
            path = f"{prefix}.{key}" if prefix else str(key)
            replaced = _convert(value, path, items, type_map, locker, translator, locale, target)
            if replaced is not _UNCHANGED:
                node[key] = replaced
        return
    if isinstance(node, list):
        for index, value in enumerate(node):
            replaced = _convert(value, prefix, items, type_map, locker, translator, locale, target)
            if replaced is not _UNCHANGED:
                node[index] = replaced


_UNCHANGED = object()


def _convert(
    value: object,
    path: str,
    items: list[PlanItem],
    type_map: dict[str, str],
    locker: EntityLocker,
    translator: Translator | None,
    locale: str,
    target: str,
):
    if isinstance(value, dict):
        _walk(value, path, items, type_map, locker, translator, locale, target)
        return _UNCHANGED
    if isinstance(value, list):
        _walk(value, path + "[]", items, type_map, locker, translator, locale, target)
        return _UNCHANGED
    kind = type_map.get(path)
    if kind not in TRANSLATABLE or not isinstance(value, str):
        return _UNCHANGED
    masked, originals = locker.mask(value)
    if kind == TranslationType.FREE_TEXT.value and translator is not None:
        translated = _translate_locked(masked, originals, locker, translator, locale, target)
    else:
        translated = locker.restore(masked, originals)
    items.append(
        PlanItem(
            path=path,
            translation_type=kind,
            original=value,
            masked=masked,
            translated=translated,
        )
    )
    return translated


def _translate_locked(
    masked: str,
    originals: list[str],
    locker: EntityLocker,
    translator: Translator,
    locale: str,
    target: str,
) -> str:
    pieces = _LOCK.split(masked)
    tokens = _LOCK.findall(masked)
    indexes = [index for index, piece in enumerate(pieces) if piece.strip()]
    batch = [pieces[index] for index in indexes]
    translated = translator.translate(batch, locale, target) if batch else []
    if len(translated) != len(batch):
        raise TranslationError("translator returned the wrong number of strings")
    produced = dict(zip(indexes, translated, strict=True))
    rendered: list[str] = []
    for index, piece in enumerate(pieces):
        rendered.append(produced.get(index, piece))
        if index < len(tokens):
            rendered.append(tokens[index])
    stitched = "".join(rendered)
    if _LOCK.findall(stitched) != tokens:
        return locker.restore(masked, originals)
    return locker.restore(stitched, originals)
