"""Remember repeated argument strings so a second call skips the provider."""

from __future__ import annotations

from rosetta.translate.base import Translator


class CachingTranslator:
    def __init__(self, inner: Translator) -> None:
        self.inner = inner
        self._cache: dict[tuple[str, str, str], str] = {}
        self.hits = 0
        self.misses = 0

    def translate(self, texts: list[str], source: str, target: str) -> list[str]:
        output: list[str | None] = [None] * len(texts)
        missing: list[int] = []
        for index, text in enumerate(texts):
            key = (source, target, text)
            cached = self._cache.get(key)
            if cached is None:
                self.misses += 1
                missing.append(index)
            else:
                self.hits += 1
                output[index] = cached
        if missing:
            translated = self.inner.translate([texts[index] for index in missing], source, target)
            for index, value in zip(missing, translated, strict=True):
                self._cache[(source, target, texts[index])] = value
                output[index] = value
        return [value if value is not None else "" for value in output]
