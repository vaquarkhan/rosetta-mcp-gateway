"""Mask non-translatable spans and restore them after a future translation."""

from __future__ import annotations

import re

# Order matters: a date must be taken whole before the number pattern, and a
# URL must be taken whole before anything inside it.
_SPAN = re.compile(
    r"```[\s\S]*?```"
    r"|https?://[^\s]+"
    r"|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
    r"|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    r"|\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})?)?"
    r"|\$\{[A-Za-z_][A-Za-z0-9_]*\}"
    r"|\{\{[^{}]+\}\}"
    r"|%s"
    r"|\$\d+"
    r"|\d+(?:\.\d+)?"
)


class EntityLocker:
    def __init__(self, glossary: list[str] | None = None) -> None:
        self.glossary = sorted((term for term in (glossary or []) if term), key=len, reverse=True)

    def mask(self, text: str) -> tuple[str, list[str]]:
        spans = self._spans(text)
        originals: list[str] = []
        pieces: list[str] = []
        cursor = 0
        for start, end in spans:
            pieces.append(text[cursor:start])
            originals.append(text[start:end])
            pieces.append(f"«L:{len(originals) - 1}:»")
            cursor = end
        pieces.append(text[cursor:])
        return "".join(pieces), originals

    def restore(self, text: str, originals: list[str]) -> str:
        restored = text
        for index in range(len(originals) - 1, -1, -1):
            restored = restored.replace(f"«L:{index}:»", originals[index])
        return restored

    def round_trip(self, text: str) -> str:
        masked, originals = self.mask(text)
        return self.restore(masked, originals)

    def _spans(self, text: str) -> list[tuple[int, int]]:
        occupied: list[tuple[int, int]] = []
        for term in self.glossary:
            start = 0
            while True:
                found = text.find(term, start)
                if found < 0:
                    break
                end = found + len(term)
                if not _overlaps(found, end, occupied):
                    occupied.append((found, end))
                start = end
        for match in _SPAN.finditer(text):
            if not _overlaps(match.start(), match.end(), occupied):
                occupied.append((match.start(), match.end()))
        occupied.sort()
        return occupied


def _overlaps(start: int, end: int, occupied: list[tuple[int, int]]) -> bool:
    return any(not (end <= left or start >= right) for left, right in occupied)
