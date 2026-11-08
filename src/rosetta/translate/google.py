"""Online translation through deep-translator's Google backend.

This is the provider that works without a local model download. Air-gapped
deployments use the CTranslate2 provider instead.
"""

from __future__ import annotations

from rosetta.translate.base import TranslationError, language_code


class GoogleTranslateProvider:
    def translate(self, texts: list[str], source: str, target: str) -> list[str]:
        pending = [(index, text) for index, text in enumerate(texts) if text.strip()]
        output = list(texts)
        if not pending:
            return output
        try:
            from deep_translator import GoogleTranslator
        except ImportError as exc:
            raise TranslationError("deep-translator is not installed") from exc
        translator = GoogleTranslator(source=language_code(source), target=language_code(target))
        batch = [text for _index, text in pending]
        try:
            translated = translator.translate_batch(batch)
        except Exception as exc:
            raise TranslationError(str(exc)) from exc
        if not isinstance(translated, list) or len(translated) != len(batch):
            raise TranslationError("translation provider returned the wrong number of strings")
        for (index, _text), value in zip(pending, translated, strict=True):
            output[index] = value if isinstance(value, str) and value else texts[index]
        return output
