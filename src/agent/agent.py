"""GreenClaw CPU — Core Agent.

The brain of GreenClaw. Orchestrates models, souls, and memory
into a coherent AI agent that runs on any machine.

Freedom is Key — no artificial restrictions.
"""

import asyncio
import logging
import sys
from typing import Optional

from ..models.base import ModelProvider
from ..soul.soul_manager import SoulManager
from ..memory.memory import Memory
from ..memory.consolidation import MemoryConsolidator

logger = logging.getLogger(__name__)


class Agent:
    """
    GreenClaw's core agent.

    The Agent orchestrates:
    - ModelProvider: The AI model (Ollama, OpenAI, Anthropic, etc.)
    - SoulManager: Personality and identity (SOUL.md, IDENTITY.md, etc.)
    - Memory: Conversation history and persistent memory
    - MemoryConsolidator: Automatic memory summarization

    Example:
        agent = Agent(model_provider=provider, soul_manager=soul_manager)
        response = await agent.run("Hello, who are you?")
    """

    def __init__(
        self,
        model_provider: ModelProvider,
        soul_manager: SoulManager,
        memory: Optional[Memory] = None,
        auto_consolidate: bool = True,
        stream: bool = True,
    ):
        self.model = model_provider
        self.soul = soul_manager
        self.memory = memory or Memory(enabled=False)
        self.auto_consolidate = auto_consolidate
        self.stream = stream

        self._consolidator: Optional[MemoryConsolidator] = None
        if self.auto_consolidate and self.memory.enabled:
            self._consolidator = MemoryConsolidator(
                memory_instance=self.memory,
                soul_manager=self.soul,
                model_provider=self.model,
                threshold=self.memory.consolidation_threshold,
            )

        logger.info(f"Agent initialized: model={model_provider}, stream={stream}")

    async def run(self, user_input: str, stream: Optional[bool] = None) -> str:
        """
        Process a user message and return the agent's response.

        Args:
            user_input: The user's message.
            stream: Override streaming setting for this call.

        Returns:
            The agent's text response.
        """
        use_stream = stream if stream is not None else self.stream

        # Add user message to memory
        self.memory.add("user", user_input)

        # Build messages with system prompt
        messages = self._build_messages(user_input)

        # Check for consolidation
        if self._consolidator:
            summary = self._consolidator.check_and_consolidate()
            if summary:
                logger.debug(f"Auto-consolidated: {summary[:50]}...")

        # Generate response
        if use_stream and self.model.supportsstreaming():
            response_text = ""
            print("\n🟢 GreenClaw: ", end="", flush=True)
            try:
                async for chunk in self.model.stream_chat(messages):
                    print(chunk, end="", flush=True)
                    response_text += chunk
                print()  # newline after streaming
            except Exception as e:
                logger.error(f"Streaming failed, falling back: {e}")
                response_text = await self.model.chat(messages)
        else:
            response_text = await self.model.chat(messages)

        # Add assistant response to memory
        self.memory.add("assistant", response_text)

        return response_text

    def _build_messages(self, user_input: str) -> list[dict[str, str]]:
        """Build the message list with system prompt and history."""
        messages = []

        # System prompt with soul
        system_prompt = self.soul.get_system_prompt()
        messages.append({"role": "system", "content": system_prompt})

        # Conversation history (recent messages)
        history = self.memory.get_conversation_history(limit=50)
        messages.extend(history)

        # Current user input
        messages.append({"role": "user", "content": user_input})

        return messages

    async def health_check(self) -> dict[str, bool]:
        """
        Check the health of all agent components.

        Returns:
            Dict with status of model, soul, and memory.
        """
        status = {}

        # Check model
        try:
            status["model"] = await self.model.health_check()
        except Exception as e:
            logger.error(f"Model health check failed: {e}")
            status["model"] = False

        # Check soul
        status["soul"] = self.soul.get_active_soul() is not None

        # Check memory
        status["memory"] = self.memory.enabled

        return status

    def switch_soul(self, soul_name: str) -> None:
        """Switch to a different soul/personality."""
        self.soul.switch_soul(soul_name)
        logger.info(f"Switched to soul: {soul_name}")

    def list_souls(self) -> list[str]:
        """List available souls."""
        return self.soul.list_available_souls()

    def exit_consolidation(self) -> None:
        """Perform final memory consolidation before exit."""
        if self._consolidator:
            self._consolidator.consolidate_on_exit()

    async def close(self) -> None:
        """Clean up resources."""
        self.exit_consolidation()
        if hasattr(self.model, "close"):
            await self.model.close()
        logger.info("Agent closed")

    def __repr__(self) -> str:
        return f"<Agent model={self.model} soul={self.soul._active_soul_name}>"
