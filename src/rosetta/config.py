"""gateway.yaml plus environment overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import yaml


@dataclass
class Settings:
    schema_translation_mode: str = "none"
    upstream_name: str = "upstream"
    upstream_url: str = "http://127.0.0.1:9100/mcp"
    upstream_protocol: str = "2026-07-28"
    host: str = "127.0.0.1"
    port: int = 8080
    entity_locked_fields: list[str] = field(default_factory=list)
    glossary: list[str] = field(default_factory=list)
    tool_overrides: dict[str, dict[str, str]] = field(default_factory=dict)
    translation_provider: str = ""
    translation_profile: str = "balanced"
    translation_fallback: str = "mymemory"
    translation_target: str = "en"
    translation_model_dir: str = ""
    translation_device: str = "cpu"
    security_bastion: bool = False


def load_settings(path: str | None = None) -> Settings:
    config_path = path or os.environ.get("MCP_GW_CONFIG") or "gateway.yaml"
    raw: dict = {}
    if config_path and os.path.exists(config_path):
        with open(config_path, encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle)
            raw = loaded if isinstance(loaded, dict) else {}

    upstream = raw.get("upstream") if isinstance(raw.get("upstream"), dict) else {}
    server = raw.get("server") if isinstance(raw.get("server"), dict) else {}
    translation = raw.get("translation") if isinstance(raw.get("translation"), dict) else {}
    security = raw.get("security") if isinstance(raw.get("security"), dict) else {}
    settings = Settings(
        schema_translation_mode=str(raw.get("schema_translation_mode") or "none"),
        upstream_name=str(upstream.get("name") or "upstream"),
        upstream_url=str(upstream.get("url") or "http://127.0.0.1:9100/mcp"),
        upstream_protocol=str(upstream.get("protocol") or "2026-07-28"),
        host=str(server.get("host") or "127.0.0.1"),
        port=int(server.get("port") or 8080),
        entity_locked_fields=list(raw.get("entity_locked_fields") or []),
        glossary=list(raw.get("glossary") or []),
        tool_overrides=_tool_overrides(raw.get("tools")),
        translation_provider=str(translation.get("provider") or ""),
        translation_profile=_profile(translation),
        translation_fallback=str(translation.get("fallback") or "mymemory"),
        translation_target=str(translation.get("target") or "en"),
        translation_model_dir=str(translation.get("model_dir") or ""),
        translation_device=str(translation.get("device") or "cpu"),
        security_bastion=_flag(security.get("bastion")),
    )
    _apply_env(settings)
    return settings


def _profile(translation: dict) -> str:
    if translation.get("profile"):
        return str(translation["profile"])
    if translation.get("provider"):
        return "single"
    return "balanced"


def _tool_overrides(tools: object) -> dict[str, dict[str, str]]:
    if not isinstance(tools, dict):
        return {}
    parsed: dict[str, dict[str, str]] = {}
    for name, spec in tools.items():
        fields = spec.get("fields") if isinstance(spec, dict) else None
        if isinstance(fields, dict):
            parsed[str(name)] = {str(path): str(value) for path, value in fields.items()}
    return parsed


def _apply_env(settings: Settings) -> None:
    if os.environ.get("ROSETTA_UPSTREAM_URL"):
        settings.upstream_url = os.environ["ROSETTA_UPSTREAM_URL"]
    if os.environ.get("ROSETTA_UPSTREAM_PROTOCOL"):
        settings.upstream_protocol = os.environ["ROSETTA_UPSTREAM_PROTOCOL"]
    if os.environ.get("ROSETTA_HOST"):
        settings.host = os.environ["ROSETTA_HOST"]
    if os.environ.get("ROSETTA_PORT"):
        settings.port = int(os.environ["ROSETTA_PORT"])
    if os.environ.get("ROSETTA_SCHEMA_TRANSLATION_MODE"):
        settings.schema_translation_mode = os.environ["ROSETTA_SCHEMA_TRANSLATION_MODE"]
    if os.environ.get("ROSETTA_TRANSLATION_PROFILE"):
        settings.translation_profile = os.environ["ROSETTA_TRANSLATION_PROFILE"]
    if os.environ.get("ROSETTA_TRANSLATION_PROVIDER"):
        settings.translation_provider = os.environ["ROSETTA_TRANSLATION_PROVIDER"]
        settings.translation_profile = "single"
    if os.environ.get("ROSETTA_CT2_MODEL"):
        settings.translation_model_dir = os.environ["ROSETTA_CT2_MODEL"]
    if os.environ.get("ROSETTA_BASTION"):
        settings.security_bastion = _flag(os.environ["ROSETTA_BASTION"])


def _flag(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False
