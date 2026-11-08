"""Online translation through the MyMemory API.

Google's unofficial endpoint rate-limits many hosts. MyMemory is the default
online provider so a fresh install can translate without a local model.
"""

from __future__ import annotations

from rosetta.translate.base import TranslationError, language_code

# MyMemory expects regional codes, not bare ISO 639-1 tags.
_CODES = {
    "en": "en-GB",
    "hi": "hi-IN",
    "es": "es-ES",
    "ar": "ar-SA",
    "fr": "fr-FR",
    "zh-CN": "zh-CN",
    "zh-TW": "zh-TW",
    "pt": "pt-BR",
    "de": "de-DE",
    "ja": "ja-JP",
    "ru": "ru-RU",
    "bn": "bn-IN",
    "ko": "ko-KR",
}


class MyMemoryTranslateProvider:
    def translate(self, texts: list[str], source: str, target: str) -> list[str]:
        pending = [(index, text) for index, text in enumerate(texts) if text.strip()]
        output = list(texts)
        if not pending:
            return output
        try:
            from deep_translator import MyMemoryTranslator
        except ImportError as exc:
            raise TranslationError("deep-translator is not installed") from exc
        translator = MyMemoryTranslator(source=_code(source), target=_code(target))
        translated: list[str] = []
        try:
            for _index, text in pending:
                translated.append(translator.translate(text))
        except Exception as exc:
            raise TranslationError(str(exc)) from exc
        if len(translated) != len(pending):
            raise TranslationError("translation provider returned the wrong number of strings")
        for (index, original), value in zip(pending, translated, strict=True):
            output[index] = value if isinstance(value, str) and value.strip() else original
        return output


def _code(locale: str) -> str:
    code = language_code(locale)
    return _CODES.get(code, code)
