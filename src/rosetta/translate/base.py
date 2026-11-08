"""Translator contract."""

from __future__ import annotations

from typing import Protocol


class TranslationError(RuntimeError):
    """The configured provider could not translate a batch."""


class Translator(Protocol):
    def translate(self, texts: list[str], source: str, target: str) -> list[str]:
        """Translate each string from source locale to target locale, in order."""


def language_code(locale: str) -> str:
    """Reduce `hi-IN` to the provider language code."""
    normalized = locale.strip().replace("_", "-")
    lower = normalized.lower()
    if lower in {"zh", "zh-cn"}:
        return "zh-CN"
    if lower == "zh-tw":
        return "zh-TW"
    return lower.split("-", 1)[0]
