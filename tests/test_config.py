"""GreenClaw CPU — Configuration Tests."""

import pytest
import tempfile
import os
from pathlib import Path


class TestConfig:
    """Test configuration loading."""

    def test_load_default_config(self):
        """Test loading with default values."""
        from src.config import Config

        config = Config.load()
        assert config.model.provider == "ollama"
        assert config.model.name == "llama3.2"
        assert config.soul.soul_dir == "./souls"

    def test_load_config_from_yaml(self):
        """Test loading config from YAML file."""
        from src.config import Config

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("""
model_provider: openai
model_name: gpt-4o
model_api_key: test-key-123
ollama_url: http://localhost:11434
soul_dir: ./my_souls
active_soul: developer
log_level: DEBUG
""")
            f.flush()

            config = Config.load(f.name)
            assert config.model.provider == "openai"
            assert config.model.name == "gpt-4o"
            assert config.model.api_key == "test-key-123"
            assert config.soul.soul_dir == "./my_souls"

            os.unlink(f.name)

    def test_env_overrides_yaml(self):
        """Test that environment variables override YAML config."""
        from src.config import Config

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("model_provider: openai\nmodel_name: gpt-4o\n")
            f.flush()
            config_path = f.name

        os.environ["GREENCLAW_PROVIDER"] = "anthropic"
        os.environ["GREENCLAW_MODEL"] = "claude-3"

        try:
            config = Config.load(config_path)
            assert config.model.provider == "anthropic"
            assert config.model.name == "claude-3"
        finally:
            os.unlink(config_path)
            del os.environ["GREENCLAW_PROVIDER"]
            del os.environ["GREENCLAW_MODEL"]

    def test_get_config_singleton(self):
        """Test that get_config returns the same instance."""
        from src.config import get_config, reload_config

        # Reset
        reload_config()

        cfg1 = get_config()
        cfg2 = get_config()
        assert cfg1 is cfg2  # Same instance


class TestModelFactory:
    """Test model factory."""

    def test_create_ollama_provider(self):
        """Test creating Ollama provider."""
        from src.models.factory import create_provider

        provider = create_provider(
            provider_name="ollama",
            model_name="llama3.2",
            ollama_url="http://localhost:11434",
        )

        assert provider.model_name == "llama3.2"
        assert "Ollama" in type(provider).__name__

    def test_create_openai_provider(self):
        """Test creating OpenAI provider."""
        from src.models.factory import create_provider

        provider = create_provider(
            provider_name="openai",
            model_name="gpt-4o",
            api_key="test-key",
        )

        assert provider.model_name == "gpt-4o"
        assert "OpenAI" in type(provider).__name__

    def test_unknown_provider_raises(self):
        """Test that unknown provider raises ValueError."""
        from src.models.factory import create_provider

        with pytest.raises(ValueError) as exc_info:
            create_provider(provider_name="unknown_provider", model_name="test")

        assert "Unknown provider" in str(exc_info.value)
        assert "Freedom is Key" in str(exc_info.value)

    def test_register_new_provider(self):
        """Test registering a custom provider."""
        from src.models.factory import create_provider, register_provider
        from src.models.base import ModelProvider

        class DummyProvider(ModelProvider):
            def __init__(self, model_name, **kwargs):
                self.model_name = model_name

            def _setup(self, **kwargs) -> None:
                pass

            async def generate(self, prompt, **kwargs):
                return "dummy"

            async def chat(self, messages, **kwargs):
                return "dummy"

            async def health_check(self):
                return True

        register_provider("dummy", DummyProvider)

        provider = create_provider(provider_name="dummy", model_name="test")
        assert "Dummy" in type(provider).__name__
