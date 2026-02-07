"""
Centralized Settings Loader

This module provides a single point of access for all runtime configuration.
All backend modules should import settings from here instead of defining their own.

Usage:
    from config.settings_loader import settings, save_settings, reset_settings
    
    # Access settings
    model = settings["models"]["embedding"]
    
    # Update settings (writes to disk)
    settings["rag"]["top_k"] = 5
    save_settings()
    
    # Reset to defaults
    reset_settings()
    
    # Smart reload (only re-reads if file changed on disk)
    fresh = get_fresh_settings()
"""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Paths
CONFIG_DIR = Path(__file__).parent
SETTINGS_FILE = CONFIG_DIR / "settings.json"
DEFAULTS_FILE = CONFIG_DIR / "settings.defaults.json"

# --- Settings Cache with file modification tracking ---
_settings_cache = None
_settings_mtime = 0.0  # Last known modification time of settings file


def load_settings() -> dict:
    """Load settings from file. Uses cache if already loaded."""
    global _settings_cache, _settings_mtime
    if _settings_cache is None:
        if SETTINGS_FILE.exists():
            _settings_cache = json.loads(SETTINGS_FILE.read_text())
            _settings_mtime = os.path.getmtime(SETTINGS_FILE)
        elif DEFAULTS_FILE.exists():
            _settings_cache = json.loads(DEFAULTS_FILE.read_text())
            save_settings()
        else:
            raise FileNotFoundError(f"No settings files found in {CONFIG_DIR}")
    return _settings_cache


def save_settings() -> None:
    """Save current settings to file."""
    global _settings_cache, _settings_mtime
    if _settings_cache is not None:
        SETTINGS_FILE.write_text(json.dumps(_settings_cache, indent=2))
        _settings_mtime = os.path.getmtime(SETTINGS_FILE)


def reset_settings() -> dict:
    """Reset settings to defaults."""
    global _settings_cache
    if DEFAULTS_FILE.exists():
        _settings_cache = json.loads(DEFAULTS_FILE.read_text())
        save_settings()
    return _settings_cache


def reload_settings() -> dict:
    """Force reload settings from disk (useful after external changes)."""
    global _settings_cache, _settings_mtime
    _settings_cache = None
    _settings_mtime = 0.0
    return load_settings()


def get_fresh_settings() -> dict:
    """Get settings, reloading from disk only if the file has been modified.
    
    This avoids the cost of re-reading the file on every agent call 
    (which could be 10+ parallel reads in a DAG) while still picking up
    changes made externally (e.g., via the settings UI).
    """
    global _settings_cache, _settings_mtime
    
    if _settings_cache is None:
        return load_settings()
    
    try:
        current_mtime = os.path.getmtime(SETTINGS_FILE) if SETTINGS_FILE.exists() else 0.0
        if current_mtime > _settings_mtime:
            logger.debug("Settings file changed on disk, reloading...")
            return reload_settings()
    except OSError as e:
        logger.warning(f"Could not check settings file mtime: {e}")
    
    return _settings_cache


# --- Convenience Accessors ---

def get_ollama_url(endpoint: str = "generate") -> str:
    """Get full Ollama URL for a specific endpoint."""
    base = load_settings()["ollama"]["base_url"]
    if endpoint == "base":
        return base
    endpoints = {
        "generate": "/api/generate",
        "chat": "/api/chat",
        "embed": "/api/embed",
        "embeddings": "/api/embeddings"
    }
    return f"{base}{endpoints.get(endpoint, '/api/' + endpoint)}"


def get_model(purpose: str) -> str:
    """Get model name for a specific purpose."""
    return load_settings()["models"].get(purpose, "gemma3:4b")


def get_timeout() -> int:
    """Get Ollama timeout in seconds."""
    return load_settings()["ollama"]["timeout"]


# --- Initialize on import ---
settings = load_settings()
