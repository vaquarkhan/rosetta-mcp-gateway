"""Optional security hooks. MCP-Bastion stays an external package."""

from rosetta.security.bastion import BastionUnavailable, screen_texts

__all__ = ["BastionUnavailable", "screen_texts"]
