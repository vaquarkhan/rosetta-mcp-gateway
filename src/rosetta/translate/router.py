"""Pick an engine per language pair.

The order comes from the public comparisons, not from one model being best
at everything:

* DeepL is the quality leader for its European set, and its glossary inflects.
  It does not cover Hindi or Bengali.
* Google Cloud Translation v3 covers the long tail, including Hindi, Arabic,
  and Bengali, and has a glossary.
* CTranslate2 with Opus-MT INT8 and beam size 1 is the commercial local
  engine. A short phrase is about 28 ms and a sentence about 96 ms. NLLB is
  slower and CC-BY-NC, so it stays on the research profile.
* MADLAD-400, SeamlessM4T, and Tower are stronger on hard prose and too
  large for the tool-call budget.
* MyMemory is a translation-memory API. It is the dev fallback when no key
  and no local model are configured. It is not a production engine.
"""

from __future__ import annotations

from rosetta.translate.base import TranslationError, Translator, language_code

# DeepL's quality advantage is on this set. Hindi and Bengali are outside it.
DEEPL_LANGUAGES = {"de", "fr", "es", "pt", "it", "nl", "pl", "ja", "ko", "ru", "zh", "en"}


class RoutedTranslator:
    def __init__(
        self,
        *,
        profile: str = "balanced",
        deepl: Translator | None = None,
        google: Translator | None = None,
        local: Translator | None = None,
        fallback: Translator | None = None,
    ) -> None:
        self.profile = profile
        self.deepl = deepl
        self.google = google
        self.local = local
        self.fallback = fallback

    def translate(self, texts: list[str], source: str, target: str) -> list[str]:
        engines = self.order(source, target)
        if not engines:
            raise TranslationError(f"no translation engine for {source} -> {target}")
        errors: list[str] = []
        for engine in engines:
            try:
                return engine.translate(texts, source, target)
            except TranslationError as exc:
                errors.append(str(exc))
        raise TranslationError("; ".join(errors))

    def order(self, source: str, target: str) -> list[Translator]:
        if self.profile == "dev":
            return [self.fallback] if self.fallback else []
        if self.profile == "airgap":
            return [self.local] if self.local else []
        chosen: list[Translator] = []
        if self.profile in {"balanced", "quality"} and self.deepl and _deepl_pair(source, target):
            chosen.append(self.deepl)
        if self.profile in {"balanced", "quality"} and self.google:
            chosen.append(self.google)
        if self.profile == "balanced" and self.local:
            chosen.append(self.local)
        if self.profile == "balanced" and self.fallback:
            chosen.append(self.fallback)
        return chosen


def _deepl_pair(source: str, target: str) -> bool:
    return language_code(source).lower() in DEEPL_LANGUAGES and language_code(target).lower() in DEEPL_LANGUAGES
