"""GreenClaw CPU — Ollama Connection Tests."""

import pytest
import asyncio


@pytest.fixture
def ollama_url():
    return "http://localhost:11434"


@pytest.fixture
def default_model():
    return "llama3.2"


class TestOllamaConnection:
    """Test Ollama connectivity and basic operations."""

    @pytest.mark.asyncio
    async def test_ollama_generate(self, ollama_url, default_model):
        """Test simple generation with Ollama."""
        from src.models.factory import create_provider

        provider = create_provider(
            provider_name="ollama",
            model_name=default_model,
            ollama_url=ollama_url,
        )

        result = await provider.generate("Say 'test' in exactly one word.")
        assert isinstance(result, str)
        assert len(result) > 0
        assert result.lower() in ("test", "test.")

        await provider.close()

    @pytest.mark.asyncio
    async def test_ollama_chat(self, ollama_url, default_model):
        """Test chat-style interaction with Ollama."""
        from src.models.factory import create_provider

        provider = create_provider(
            provider_name="ollama",
            model_name=default_model,
            ollama_url=ollama_url,
        )

        messages = [
            {"role": "user", "content": "What is 2+2? Answer in one number."}
        ]
        result = await provider.chat(messages)
        assert isinstance(result, str)
        assert "4" in result

        await provider.close()

    @pytest.mark.asyncio
    async def test_ollama_health_check(self, ollama_url, default_model):
        """Test health check endpoint."""
        from src.models.factory import create_provider

        provider = create_provider(
            provider_name="ollama",
            model_name=default_model,
            ollama_url=ollama_url,
        )

        healthy = await provider.health_check()
        assert isinstance(healthy, bool)

        await provider.close()

    @pytest.mark.asyncio
    async def test_ollama_streaming(self, ollama_url, default_model):
        """Test streaming response from Ollama."""
        from src.models.factory import create_provider

        provider = create_provider(
            provider_name="ollama",
            model_name=default_model,
            ollama_url=ollama_url,
        )

        chunks = []
        async for chunk in provider.stream_chat(
            [{"role": "user", "content": "Count from 1 to 3: respond with just numbers separated by spaces."}]
        ):
            chunks.append(chunk)

        assert len(chunks) > 0
        full_response = "".join(chunks)
        assert len(full_response) > 0

        await provider.close()


class TestOllamaProviderDirect:
    """Test OllamaProvider class directly."""

    @pytest.mark.asyncio
    async def test_provider_repr(self, ollama_url, default_model):
        """Test string representation of provider."""
        from src.models.ollama import OllamaProvider

        provider = OllamaProvider(model_name=default_model, base_url=f"{ollama_url}/v1")
        repr_str = repr(provider)
        assert "OllamaProvider" in repr_str
        assert default_model in repr_str
        await provider.close()
