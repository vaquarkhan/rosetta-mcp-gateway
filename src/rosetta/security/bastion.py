"""Optional call into MCP-Bastion after arguments are in English.

Rosetta does not vendor Bastion. The package `mcp-bastion-python` is
source-available: non-commercial use has its own citation terms, and
commercial use needs a separate license from that project. Install it
yourself and set security.bastion to true.
"""

from __future__ import annotations


class BastionUnavailable(RuntimeError):
    """security.bastion is on, and mcp-bastion-python is not installed."""


def screen_texts(texts: list[str]) -> str | None:
    """Return a matched injection pattern, or None when the texts are clean."""
    try:
        from mcp_bastion.pillars.injection_heuristics import (
            compile_injection_patterns,
            find_injection_match,
        )
    except ImportError as exc:
        raise BastionUnavailable(
            "Install mcp-bastion-python from https://github.com/vaquarkhan/MCP-Bastion "
            "and comply with its license."
        ) from exc
    patterns = compile_injection_patterns()
    for text in texts:
        if not text or not text.strip():
            continue
        match = find_injection_match(text, patterns)
        if match:
            return match
    return None
