"""In-process CTranslate2 translation for an NLLB-200 model directory.

Point `translation.model_dir` at a converted model (tokenizer files included).
NLLB-200 weights are CC-BY-NC, so commercial deployments should use an
Opus-MT directory with the same layout or the Google provider.
"""

from __future__ import annotations

import os

from rosetta.translate.base import TranslationError, language_code

# Flores-200 codes used by NLLB. The gateway locale is mapped before the call.
NLLB_CODES = {
    "en": "eng_Latn",
    "hi": "hin_Deva",
    "es": "spa_Latn",
    "ar": "arb_Arab",
    "fr": "fra_Latn",
    "zh-CN": "zho_Hans",
    "zh": "zho_Hans",
    "pt": "por_Latn",
    "de": "deu_Latn",
    "ja": "jpn_Jpan",
    "ru": "rus_Cyrl",
    "bn": "ben_Beng",
    "ko": "kor_Hang",
}


class CTranslate2Translator:
    def __init__(self, model_dir: str, device: str = "cpu") -> None:
        if not model_dir or not os.path.isdir(model_dir):
            raise TranslationError(
                "CTranslate2 model_dir is missing. Set translation.model_dir or ROSETTA_CT2_MODEL."
            )
        self.model_dir = model_dir
        self.device = device
        self._translator = None
        self._tokenizer = None

    def translate(self, texts: list[str], source: str, target: str) -> list[str]:
        translator, tokenizer = self._load()
        source_code = _nllb(source)
        target_code = _nllb(target)
        output = list(texts)
        pending = [(index, text) for index, text in enumerate(texts) if text.strip()]
        if not pending:
            return output
        tokenizer.src_lang = source_code
        batch_tokens = []
        for _index, text in pending:
            encoded = tokenizer.encode(text)
            batch_tokens.append(tokenizer.convert_ids_to_tokens(encoded))
        try:
            results = translator.translate_batch(
                batch_tokens,
                target_prefix=[[target_code]] * len(batch_tokens),
                beam_size=1,
            )
        except Exception as exc:
            raise TranslationError(str(exc)) from exc
        if len(results) != len(pending):
            raise TranslationError("CTranslate2 returned the wrong number of strings")
        for (index, original), result in zip(pending, results, strict=True):
            hypothesis = list(result.hypotheses[0]) if result.hypotheses else []
            if hypothesis and hypothesis[0] == target_code:
                hypothesis = hypothesis[1:]
            decoded = tokenizer.decode(tokenizer.convert_tokens_to_ids(hypothesis)).strip()
            output[index] = decoded or original
        return output

    def _load(self):
        if self._translator is not None and self._tokenizer is not None:
            return self._translator, self._tokenizer
        try:
            import ctranslate2
            from transformers import AutoTokenizer
        except ImportError as exc:
            raise TranslationError(
                "Install the local extra: python -m pip install -e \".[local]\""
            ) from exc
        self._translator = ctranslate2.Translator(self.model_dir, device=self.device)
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_dir)
        return self._translator, self._tokenizer


def _nllb(locale: str) -> str:
    code = language_code(locale)
    resolved = NLLB_CODES.get(code) or NLLB_CODES.get(locale)
    if resolved is None:
        raise TranslationError(f"no NLLB language code for {locale}")
    return resolved
