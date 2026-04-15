"""GreenClaw CPU — Configuration Management."""

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field
from dotenv import load_dotenv

load_dotenv()

# ─── Flat Pydantic models (mirrors config.yaml structure) ──────────────────────

class ModelConfig(BaseModel):
    """Model provider configuration (flat, matches config.yaml)."""
    model_config = ConfigDict(populate_by_name=True)

    provider: str = "ollama"
    name: str = "llama3.2"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    ollama_url: str = "http://localhost:11434"
    localai_url: str = "http://localhost:8080"
    max_retries: int = 3
    timeout: int = 120
    stream: bool = True


class SoulConfig(BaseModel):
    """Soul/personality configuration."""
    soul_dir: str = "./souls"
    active_soul: str = "default"


class MemoryConfig(BaseModel):
    """Memory system configuration."""
    enabled: bool = True
    memory_dir: str = "./memory"
    consolidation_threshold: int = 50


class LoggingConfig(BaseModel):
    """Logging configuration."""
    level: str = "INFO"
    log_file: str = "./logs/greenchclaw.log"


class ServerConfig(BaseModel):
    """Server configuration — allows multiple GreenClaw instances to run simultaneously."""
    port: int = 51234          # Default port for GreenClaw CPU
    host: str = "0.0.0.0"     # Bind address (0.0.0.0 = all interfaces)
    mode: str = "cli"         # "cli" (interactive) or "api" (HTTP server)


class Config(BaseModel):
    """Root configuration for GreenClaw CPU."""
    model: ModelConfig = Field(default_factory=ModelConfig)
    soul: SoulConfig = Field(default_factory=SoulConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)

    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "Config":
        """
        Load configuration from YAML file and environment variables.

        YAML can be either flat (matching config.yaml) or nested.
        Environment variables always override YAML values.
        """
        if config_path is None:
            config_path = os.environ.get("GREENCLAW_CONFIG", "config.yaml")

        config_file = Path(config_path)
        raw_data = {}

        if config_file.exists():
            with open(config_file, "r") as f:
                raw_data = yaml.safe_load(f) or {}

        # Convert flat or nested YAML to structured data
        structured = cls._normalize(raw_data)

        # Apply environment variable overrides
        env_overrides = cls._get_env_overrides()
        structured = cls._apply_overrides(structured, env_overrides)

        return cls(**structured)

    @classmethod
    def _normalize(cls, data: dict) -> dict:
        """
        Normalize YAML data to nested Pydantic structure.

        Handles both flat keys (model_provider: x) and nested (model: {provider: x}).
        """
        normalized: dict = {
            "model": {},
            "soul": {},
            "memory": {},
            "logging": {},
            "server": {},
        }

        # Mapping: top-level YAML keys -> (section, field_in_section)
        section_map = {
            # Model section
            "model_provider": ("model", "provider"),
            "model_name": ("model", "name"),
            "model_api_key": ("model", "api_key"),
            "model_base_url": ("model", "base_url"),
            "model_ollama_url": ("model", "ollama_url"),
            "model_localai_url": ("model", "localai_url"),
            "model_max_retries": ("model", "max_retries"),
            "model_timeout": ("model", "timeout"),
            "model_stream": ("model", "stream"),
            # Aliases without prefix (flat config.yaml style)
            "provider": ("model", "provider"),
            "name": ("model", "name"),
            "api_key": ("model", "api_key"),
            "base_url": ("model", "base_url"),
            "ollama_url": ("model", "ollama_url"),
            "localai_url": ("model", "localai_url"),
            # Soul section
            "soul_dir": ("soul", "soul_dir"),
            "active_soul": ("soul", "active_soul"),
            # Memory section
            "memory_enabled": ("memory", "enabled"),
            "memory_dir": ("memory", "memory_dir"),
            "consolidation_threshold": ("memory", "consolidation_threshold"),
            # Logging section
            "log_level": ("logging", "level"),
            "log_file": ("logging", "log_file"),
            # Server section
            "server_port": ("server", "port"),
            "server_host": ("server", "host"),
            "server_mode": ("server", "mode"),
        }

        for key, value in data.items():
            if key in section_map:
                section, field = section_map[key]
                normalized[section][field] = value
            elif isinstance(value, dict):
                # Handle nested YAML: model: {provider: x}
                section_name = key
                if section_name in normalized and isinstance(value, dict):
                    for sub_key, sub_val in value.items():
                        if sub_key in section_map:
                            s, f = section_map[sub_key]
                            normalized[s][f] = sub_val
                        elif f := cls._find_field_in_section(section_name, sub_key):
                            normalized[section_name][f] = sub_val

        # Ensure all sections have at least defaults
        for section in normalized:
            if not normalized[section]:
                normalized[section] = {}

        return normalized

    @staticmethod
    def _find_field_in_section(section: str, field: str) -> Optional[str]:
        """Check if field exists in a section model."""
        section_models = {
            "model": ModelConfig,
            "soul": SoulConfig,
            "memory": MemoryConfig,
            "logging": LoggingConfig,
        }
        model = section_models.get(section)
        if model:
            fields = model.model_fields
            if field in fields:
                return field
            # Check aliases
            for f_name, f_info in fields.items():
                if hasattr(f_info, "alias") and f_info.alias == field:
                    return f_name
        return None

    @classmethod
    def _apply_overrides(cls, structured: dict, overrides: dict) -> dict:
        """Apply flat overrides to nested structured data."""
        override_map = {
            "model_provider": ("model", "provider"),
            "model_name": ("model", "name"),
            "model_api_key": ("model", "api_key"),
            "model_base_url": ("model", "base_url"),
            "model_ollama_url": ("model", "ollama_url"),
            "soul_soul_dir": ("soul", "soul_dir"),
            "soul_active_soul": ("soul", "active_soul"),
            "logging_level": ("logging", "level"),
            "logging_log_file": ("logging", "log_file"),
            "memory_enabled": ("memory", "enabled"),
            "memory_memory_dir": ("memory", "memory_dir"),
            "memory_consolidation_threshold": ("memory", "consolidation_threshold"),
            "server_port": ("server", "port"),
            "server_host": ("server", "host"),
            "server_mode": ("server", "mode"),
        }

        for flat_key, value in overrides.items():
            if flat_key in override_map:
                section, field = override_map[flat_key]
                if section not in structured:
                    structured[section] = {}
                structured[section][field] = value
            elif flat_key.startswith("model_"):
                field = flat_key[6:]
                structured.setdefault("model", {})[field] = value

        return structured

    @staticmethod
    def _get_env_overrides() -> dict:
        """Get configuration overrides from environment variables."""
        overrides = {}

        env_mappings = {
            "GREENCLAW_PROVIDER": "model_provider",
            "GREENCLAW_MODEL": "model_name",
            "GREENCLAW_API_KEY": "model_api_key",
            "GREENCLAW_BASE_URL": "model_base_url",
            "GREENCLAW_OLLAMA_URL": "model_ollama_url",
            "GREENCLAW_SOUL_DIR": "soul_soul_dir",
            "GREENCLAW_ACTIVE_SOUL": "soul_active_soul",
            "GREENCLAW_LOG_LEVEL": "logging_level",
            "GREENCLAW_PORT": "server_port",
            "GREENCLAW_HOST": "server_host",
            "GREENCLAW_MODE": "server_mode",
        }

        for env_var, config_key in env_mappings.items():
            value = os.environ.get(env_var)
            if value is not None:
                overrides[config_key] = value

        # Direct API key overrides
        if openai_key := os.environ.get("OPENAI_API_KEY"):
            overrides["model_api_key"] = openai_key
        if anthropic_key := os.environ.get("ANTHROPIC_API_KEY"):
            overrides["model_api_key"] = anthropic_key

        return overrides


# ─── Global config singleton ───────────────────────────────────────────────────

_config: Optional[Config] = None


def get_config(config_path: Optional[str] = None) -> Config:
    """Get the global config instance."""
    global _config
    if _config is None:
        _config = Config.load(config_path)
    return _config


def reload_config(config_path: Optional[str] = None) -> Config:
    """Reload configuration."""
    global _config
    _config = Config.load(config_path)
    return _config
