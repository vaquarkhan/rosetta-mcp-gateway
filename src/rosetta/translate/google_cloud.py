"""Google Cloud Translation v3. This is the long-tail engine, not the scrape API."""

from __future__ import annotations

import httpx

from rosetta.translate.base import TranslationError, language_code


class GoogleCloudTranslator:
    def __init__(self, api_key: str, project: str, client: httpx.Client | None = None) -> None:
        self.api_key = api_key
        self.project = project
        self.url = (
            "https://translation.googleapis.com/v3/projects/"
            f"{project}/locations/global:translateText"
        )
        self._client = client or httpx.Client(timeout=10.0)

    def translate(self, texts: list[str], source: str, target: str) -> list[str]:
        pending = [(index, text) for index, text in enumerate(texts) if text.strip()]
        output = list(texts)
        if not pending:
            return output
        response = self._client.post(
            self.url,
            params={"key": self.api_key},
            json={
                "contents": [text for _index, text in pending],
                "sourceLanguageCode": language_code(source),
                "targetLanguageCode": language_code(target),
                "mimeType": "text/plain",
            },
        )
        if response.status_code >= 400:
            raise TranslationError(f"Google Cloud Translation returned {response.status_code}")
        translated = [item.get("translatedText", "") for item in response.json().get("translations", [])]
        if len(translated) != len(pending):
            raise TranslationError("Google Cloud Translation returned the wrong number of strings")
        for (index, original), value in zip(pending, translated, strict=True):
            output[index] = value if isinstance(value, str) and value.strip() else original
        return output
