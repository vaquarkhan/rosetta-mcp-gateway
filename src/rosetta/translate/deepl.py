"""DeepL API v2. Use this for the European language set when a key is set."""

from __future__ import annotations

import httpx

from rosetta.translate.base import TranslationError, language_code


class DeepLTranslator:
    def __init__(self, api_key: str, client: httpx.Client | None = None) -> None:
        self.api_key = api_key
        host = "api-free.deepl.com" if api_key.endswith(":fx") else "api.deepl.com"
        self.url = f"https://{host}/v2/translate"
        self._client = client or httpx.Client(timeout=10.0)

    def translate(self, texts: list[str], source: str, target: str) -> list[str]:
        pending = [(index, text) for index, text in enumerate(texts) if text.strip()]
        output = list(texts)
        if not pending:
            return output
        response = self._client.post(
            self.url,
            headers={"Authorization": f"DeepL-Auth-Key {self.api_key}"},
            json={
                "text": [text for _index, text in pending],
                "source_lang": _deepl_code(source),
                "target_lang": _deepl_code(target),
            },
        )
        if response.status_code >= 400:
            raise TranslationError(f"DeepL returned {response.status_code}")
        payload = response.json()
        translated = [item.get("text", "") for item in payload.get("translations", [])]
        if len(translated) != len(pending):
            raise TranslationError("DeepL returned the wrong number of strings")
        for (index, original), value in zip(pending, translated, strict=True):
            output[index] = value if isinstance(value, str) and value.strip() else original
        return output


def _deepl_code(locale: str) -> str:
    code = language_code(locale).upper()
    if code == "ZH-CN":
        return "ZH"
    return code
