"""Build the routed translator described by the research profile."""

from __future__ import annotations

import os

from rosetta.config import Settings
from rosetta.translate.base import TranslationError, Translator
from rosetta.translate.cache import CachingTranslator
from rosetta.translate.router import RoutedTranslator


def build_translator(settings: Settings) -> Translator | None:
    profile = (settings.translation_profile or "balanced").lower()
    if profile == "single":
        return _single(settings)
    router = RoutedTranslator(
        profile=profile,
        deepl=_deepl(profile),
        google=_google_cloud(profile),
        local=_local(settings, profile),
        fallback=_fallback(settings, profile),
    )
    if not router.order("es", "en") and not router.order("hi", "en"):
        return None
    return CachingTranslator(router)


def _single(settings: Settings) -> Translator | None:
    provider = (settings.translation_provider or "none").lower()
    if provider in {"", "none"}:
        return None
    if provider == "google":
        from rosetta.translate.google import GoogleTranslateProvider

        return CachingTranslator(GoogleTranslateProvider())
    if provider == "mymemory":
        from rosetta.translate.mymemory import MyMemoryTranslateProvider

        return CachingTranslator(MyMemoryTranslateProvider())
    if provider == "deepl":
        key = os.environ.get("DEEPL_API_KEY", "")
        if not key:
            raise TranslationError("DEEPL_API_KEY is not set")
        from rosetta.translate.deepl import DeepLTranslator

        return CachingTranslator(DeepLTranslator(key))
    if provider == "google-cloud":
        cloud = _google_cloud("quality")
        if cloud is None:
            raise TranslationError("GOOGLE_TRANSLATE_API_KEY and GOOGLE_CLOUD_PROJECT are required")
        return CachingTranslator(cloud)
    if provider == "ctranslate2":
        local = _local(settings, "airgap")
        if local is None:
            raise TranslationError("translation.model_dir or ROSETTA_CT2_MODEL is required")
        return CachingTranslator(local)
    raise TranslationError(f"unknown translation provider {provider}")


def _deepl(profile: str):
    if profile not in {"balanced", "quality"}:
        return None
    key = os.environ.get("DEEPL_API_KEY", "")
    if not key:
        return None
    from rosetta.translate.deepl import DeepLTranslator

    return DeepLTranslator(key)


def _google_cloud(profile: str):
    if profile not in {"balanced", "quality"}:
        return None
    key = os.environ.get("GOOGLE_TRANSLATE_API_KEY", "")
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    if not key or not project:
        return None
    from rosetta.translate.google_cloud import GoogleCloudTranslator

    return GoogleCloudTranslator(key, project)


def _local(settings: Settings, profile: str):
    if profile not in {"balanced", "airgap", "research"}:
        return None
    if not settings.translation_model_dir:
        return None
    from rosetta.translate.ctranslate2_engine import CTranslate2Translator

    return CTranslate2Translator(settings.translation_model_dir, device=settings.translation_device)


def _fallback(settings: Settings, profile: str):
    if profile in {"airgap", "quality"}:
        return None
    if (settings.translation_fallback or "").lower() != "mymemory":
        return None
    from rosetta.translate.mymemory import MyMemoryTranslateProvider

    return MyMemoryTranslateProvider()
