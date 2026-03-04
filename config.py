#!/usr/bin/env python3
"""
ZapretDeck Config Adapter

Provides a simple interface used by CLI code, backed by the shared
ConfigManager implementation from utils.py.
"""

from utils import ConfigManager


class Config:
    """Thin wrapper around ConfigManager for CLI compatibility."""

    def __init__(self) -> None:
        self._manager = ConfigManager()

    def get_strategy(self) -> str:
        """Return the currently saved strategy name."""
        return self._manager.load_strategy()

    def get_game_filter(self) -> bool:
        """Return whether the game filter is enabled."""
        return self._manager.load_game_filter()

    def set_game_filter(self, enabled: bool) -> None:
        """Set whether the game filter is enabled."""
        self._manager.save_game_filter(enabled)

    def get_show_info(self) -> bool:
        """Return whether the info screen should be shown."""
        return self._manager.load_show_info()
    
    def set_show_info(self, enabled: bool) -> None:
        """Set whether the info screen should be shown."""
        self._manager.save_show_info(enabled)

