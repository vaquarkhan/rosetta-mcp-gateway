import pytest

from rosetta.locking import EntityLocker
from rosetta.proxy.plan import build_plan
from rosetta.translate.base import TranslationError
from rosetta.translate.router import RoutedTranslator


class Named:
    def __init__(self, name: str) -> None:
        self.name = name

    def translate(self, texts: list[str], source: str, target: str) -> list[str]:
        return [self.name for _text in texts]


class Boom:
    def translate(self, texts: list[str], source: str, target: str) -> list[str]:
        raise TranslationError("down")


def test_french_uses_deepl_ahead_of_google():
    google = Named("google")
    router = RoutedTranslator(profile="balanced", deepl=Named("deepl"), google=google, fallback=Named("mymemory"))
    assert router.translate(["factures"], "fr-FR", "en") == ["deepl"]


def test_hindi_skips_deepl_and_uses_google_cloud():
    deepl = Named("deepl")
    router = RoutedTranslator(profile="balanced", deepl=deepl, google=Named("google"), fallback=Named("mymemory"))
    assert router.translate(["बकाया चालान"], "hi-IN", "en") == ["google"]


def test_deepl_failure_falls_through_to_google():
    router = RoutedTranslator(profile="balanced", deepl=Boom(), google=Named("google"), fallback=Named("mymemory"))
    assert router.translate(["Rechnung"], "de", "en") == ["google"]


def test_airgap_uses_only_the_local_model():
    router = RoutedTranslator(
        profile="airgap",
        deepl=Named("deepl"),
        google=Named("google"),
        local=Named("opus"),
        fallback=Named("mymemory"),
    )
    assert router.translate(["factures"], "fr", "en") == ["opus"]


def test_quality_profile_does_not_use_the_dev_fallback():
    router = RoutedTranslator(profile="quality", fallback=Named("mymemory"))
    with pytest.raises(TranslationError):
        router.translate(["बकाया चालान"], "hi", "en")


def test_a_broken_mask_keeps_the_original_field():
    class Corrupt:
        def translate(self, texts: list[str], source: str, target: str) -> list[str]:
            return ["«L:99:»" for _text in texts]

    plan = build_plan(
        {"query": "बकाया चालान https://erp.example/a"},
        {"query": "TYPE_FREE_TEXT"},
        "hi-IN",
        EntityLocker(),
        translator=Corrupt(),
    )
    assert plan.reconstructed["query"] == "बकाया चालान https://erp.example/a"
