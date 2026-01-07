#!/usr/bin/env python3
"""
ZapretDeck Utilities Module

Handles configuration management, path resolution, and script utilities.
"""
import os
import shutil
import subprocess
from typing import Optional, List, Dict, Tuple


# === PATH RESOLUTION ===
def get_base_dir() -> str:
    """Determine the base directory for ZapretDeck."""
    if os.path.exists("/opt/zapretdeck") and os.path.isfile("/opt/zapretdeck/zapret_gui.py"):
        return "/opt/zapretdeck"
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = get_base_dir()
CUSTOM_STRATEGIES_DIR = os.path.join(BASE_DIR, "custom-strategies")
LATEST_STRATEGIES_DIR = os.path.join(BASE_DIR, "zapret-latest")
CONF_FILE = os.path.join(BASE_DIR, "conf.env")
MAIN_SCRIPT = os.path.join(BASE_DIR, "main_script.sh")
STOP_SCRIPT = os.path.join(BASE_DIR, "stop_and_clean_nft.sh")
RENAME_SCRIPT = os.path.join(BASE_DIR, "rename_bat.sh")
SERVICE_SCRIPT = os.path.join(BASE_DIR, "service.sh")
ICON_PATH = os.path.join(BASE_DIR, "zapretdeck.png")

HIDDEN_STRATEGIES = {
    "check_updates.bat",
    "service_install.bat",
    "service_remove.bat",
    "service_status.bat"
}


# === CONFIGURATION MANAGEMENT ===
class ConfigManager:
    """Manages application configuration."""
    
    def __init__(self, config_file: str = CONF_FILE):
        self.config_file = config_file
        self._config: Dict[str, str] = {}
        self._load()
    
    def _load(self) -> None:
        """Load configuration from file."""
        if os.path.exists(self.config_file):
            with open(self.config_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        self._config[key.strip()] = value.strip()
    
    def get(self, key: str, default: str = "") -> str:
        """Get configuration value."""
        return self._config.get(key, default)
    
    def set(self, key: str, value: str) -> None:
        """Set configuration value."""
        self._config[key] = value
    
    def save(self) -> None:
        """Save configuration to file."""
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                f.write("interface=any\n")
                f.write(f"strategy={self._config.get('strategy', '')}\n")
                f.write(f"gamefilter={self._config.get('gamefilter', 'false')}\n")
                f.write(f"auto_update=false\n")
        except Exception as e:
            raise IOError(f"Failed to save config: {e}")
    
    def load_strategy(self) -> str:
        """Get saved strategy from config."""
        return self.get("strategy", "")
    
    def save_strategy(self, strategy: str) -> None:
        """Save strategy to config."""
        # Convert "Автоподбор" to "auto_found.bat"
        if strategy == "Автоподбор" or strategy == "Auto-discovery":
            strategy = "auto_found.bat"
        self.set("strategy", strategy)
        self.save()
    
    def load_game_filter(self) -> bool:
        """Get game filter state from config."""
        val = self.get("gamefilter", "false").lower()
        return val in ("true", "1", "yes", "on", "enabled")
    
    def save_game_filter(self, enabled: bool) -> None:
        """Save game filter state to config."""
        self.set("gamefilter", "true" if enabled else "false")
        self.save()


# === DEPENDENCY CHECKING ===
def check_dependencies() -> Tuple[bool, List[str]]:
    """
    Check if all required dependencies are available.
    
    Returns:
        Tuple of (all_present, missing_deps)
    """
    deps = ['ip', 'nft', 'systemctl', 'pgrep', 'pkill', 'bash', 'nmcli', 'curl']
    missing = [d for d in deps if not shutil.which(d)]
    return len(missing) == 0, missing


# === STRATEGY MANAGEMENT ===
def load_strategies() -> List[str]:
    """
    Load available strategies from custom and latest directories.
    
    Returns:
        List of strategy filenames
    """
    strategies: List[str] = []
    
    # Load from custom-strategies
    if os.path.exists(CUSTOM_STRATEGIES_DIR):
        try:
            custom_strategies = [
                f for f in os.listdir(CUSTOM_STRATEGIES_DIR)
                if f.endswith(".bat") and f not in HIDDEN_STRATEGIES
            ]
            strategies.extend(custom_strategies)
        except Exception:
            pass
    
    # Load from zapret-latest
    if os.path.exists(LATEST_STRATEGIES_DIR):
        try:
            latest_strategies = [
                f for f in os.listdir(LATEST_STRATEGIES_DIR)
                if f.endswith(".bat") and f not in HIDDEN_STRATEGIES
            ]
            strategies.extend(latest_strategies)
        except Exception:
            pass
    
    # Apply rename script if needed
    if os.path.exists(CUSTOM_STRATEGIES_DIR):
        custom_bat_files = [
            f for f in os.listdir(CUSTOM_STRATEGIES_DIR)
            if f.endswith(".bat")
        ]
        if custom_bat_files and os.path.exists(RENAME_SCRIPT):
            try:
                subprocess.run(
                    ["bash", RENAME_SCRIPT],
                    cwd=BASE_DIR,
                    capture_output=True,
                    check=False
                )
            except Exception:
                pass
    
    return sorted(set(strategies))


# === SERVICE MANAGEMENT ===
def is_service_running() -> bool:
    """Check if zapretdeck.service is enabled and active."""
    try:
        enabled = subprocess.run(
            ["systemctl", "is-enabled", "--quiet", "zapretdeck.service"],
            check=False,
            capture_output=True
        ).returncode == 0
        
        active = subprocess.run(
            ["systemctl", "is-active", "--quiet", "zapretdeck.service"],
            check=False,
            capture_output=True
        ).returncode == 0
        
        return enabled and active
    except Exception:
        return False


def is_session_running() -> bool:
    """Check if nfqws process is running."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "nfqws"],
            capture_output=True,
            check=False
        )
        return result.returncode == 0
    except Exception:
        return False

