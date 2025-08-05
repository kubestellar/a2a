"""Configuration management for LLM providers."""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from dotenv import load_dotenv


class ConfigManager:
    """Manages configuration and API keys for LLM providers."""

    def __init__(self, config_dir: Optional[Path] = None):
        """Initialize config manager."""
        # Load environment variables
        load_dotenv()

        if config_dir is None:
            # Use XDG config directory or fallback to home
            xdg_config = os.environ.get("XDG_CONFIG_HOME")
            if xdg_config:
                config_dir = Path(xdg_config) / "kubestellar"
            else:
                config_dir = Path.home() / ".config" / "kubestellar"

        self.config_dir = Path(config_dir)
        self.config_file = self.config_dir / "config.yaml"
        self.keys_file = self.config_dir / "api_keys.json"

        # Create config directory if it doesn't exist
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # Set restrictive permissions on keys file
        if self.keys_file.exists():
            self.keys_file.chmod(0o600)

    def load_config(self) -> Dict[str, Any]:
        """Load configuration from file."""
        if not self.config_file.exists():
            return self._get_default_config()

        try:
            with open(self.config_file, "r") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Warning: Could not load config: {e}")
            return self._get_default_config()

    def save_config(self, config: Dict[str, Any]) -> None:
        """Save configuration to file."""
        with open(self.config_file, "w") as f:
            yaml.dump(config, f, default_flow_style=False)

    def get_api_key(self, provider: str) -> Optional[str]:
        """Get API key for a provider."""
        # First check environment variables
        env_var = f"{provider.upper()}_API_KEY"
        if env_var in os.environ:
            return os.environ[env_var]

        # Then check stored keys
        keys = self._load_api_keys()
        return keys.get(provider)

    def set_api_key(self, provider: str, api_key: str) -> None:
        """Store API key for a provider."""
        keys = self._load_api_keys()
        keys[provider] = api_key
        self._save_api_keys(keys)
        print(f"✓ API key for {provider} saved successfully")

    def remove_api_key(self, provider: str) -> None:
        """Remove stored API key for a provider."""
        keys = self._load_api_keys()
        if provider in keys:
            del keys[provider]
            self._save_api_keys(keys)
            print(f"✓ API key for {provider} removed")
        else:
            print(f"No API key found for {provider}")

    def list_api_keys(self) -> Dict[str, bool]:
        """List providers with stored API keys (without revealing keys)."""
        keys = self._load_api_keys()
        env_keys = {}

        # Check environment variables
        for provider in ["gemini", "claude", "openai", "anthropic"]:
            env_var = f"{provider.upper()}_API_KEY"
            if env_var in os.environ:
                env_keys[provider] = True

        # Combine stored and env keys
        result = {}
        for provider in set(list(keys.keys()) + list(env_keys.keys())):
            result[provider] = provider in keys or provider in env_keys

        return result

    def get_default_provider(self) -> Optional[str]:
        """Get default LLM provider."""
        # First check environment variable
        default = os.environ.get("DEFAULT_LLM_PROVIDER")
        if default:
            return default

        # Then check config file
        config = self.load_config()
        return config.get("default_provider")

    def set_default_provider(self, provider: str) -> None:
        """Set default LLM provider."""
        config = self.load_config()
        config["default_provider"] = provider
        self.save_config(config)
        print(f"✓ Default provider set to: {provider}")

    def _load_api_keys(self) -> Dict[str, str]:
        """Load API keys from secure storage."""
        if not self.keys_file.exists():
            return {}

        try:
            with open(self.keys_file, "r") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_api_keys(self, keys: Dict[str, str]) -> None:
        """Save API keys to secure storage."""
        # Write to temp file first
        temp_file = self.keys_file.with_suffix(".tmp")
        with open(temp_file, "w") as f:
            json.dump(keys, f, indent=2)

        # Set restrictive permissions
        temp_file.chmod(0o600)

        # Atomic rename
        temp_file.replace(self.keys_file)

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration."""
        # Load defaults from environment variables
        return {
            "default_provider": os.environ.get("DEFAULT_LLM_PROVIDER", "gemini"),
            "providers": {
                "gemini": {
                    "model": os.environ.get("GEMINI_MODEL", "gemini-1.5-flash"),
                    "temperature": float(os.environ.get("LLM_TEMPERATURE", "0.7")),
                },
                "claude": {
                    "model": os.environ.get("CLAUDE_MODEL", "claude-3-sonnet-20240229"),
                    "temperature": float(os.environ.get("LLM_TEMPERATURE", "0.7")),
                },
                "openai": {
                    "model": os.environ.get("OPENAI_MODEL", "gpt-4"),
                    "temperature": float(os.environ.get("LLM_TEMPERATURE", "0.7")),
                },
            },
            "ui": {
                "show_thinking": os.environ.get("SHOW_THINKING", "true").lower()
                == "true",
                "show_token_usage": os.environ.get("SHOW_TOKEN_USAGE", "true").lower()
                == "true",
                "color_output": os.environ.get("COLOR_OUTPUT", "true").lower()
                == "true",
            },
        }


# Global config manager instance
_config_manager = None


def get_config_manager() -> ConfigManager:
    """Get global config manager instance."""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager
