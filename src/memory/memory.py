"""GreenClaw CPU — Memory System.

A simple but powerful conversation memory with automatic consolidation.
Stores conversation history and periodically summarizes it into
the soul's MEMORY.md for persistence across sessions.

Freedom is Key — memory is yours to control.
"""

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """A single message in the conversation history."""
    role: str  # "user", "assistant", "system"
    content: str
    timestamp: float = field(default_factory=time.time)


class Memory:
    """
    Conversation memory with automatic consolidation.

    Keeps a rolling window of recent messages and periodically
    summarizes older messages into persistent memory.

    Attributes:
        max_recent: Maximum recent messages to keep in context.
        consolidation_threshold: Messages before triggering consolidation.
    """

    def __init__(
        self,
        memory_dir: str = "./memory",
        max_recent: int = 100,
        consolidation_threshold: int = 50,
        enabled: bool = True,
    ):
        self.enabled = enabled
        self.memory_dir = Path(memory_dir).expanduser().resolve()
        self.max_recent = max_recent
        self.consolidation_threshold = consolidation_threshold

        self._conversation: deque[Message] = deque(maxlen=max_recent)
        self._message_count: int = 0
        self._last_summary_time: float = time.time()

        if self.enabled:
            self.memory_dir.mkdir(parents=True, exist_ok=True)
            self._load_persistent_memory()

        logger.info(
            f"Memory initialized: enabled={enabled}, "
            f"max_recent={max_recent}, consolidation_threshold={consolidation_threshold}"
        )

    def add(self, role: str, content: str) -> None:
        """
        Add a message to memory.

        Args:
            role: Message role (user, assistant, system).
            content: Message content.
        """
        if not self.enabled:
            return

        msg = Message(role=role, content=content)
        self._conversation.append(msg)
        self._message_count += 1

        logger.debug(f"Memory added [{role}]: {content[:50]}...")

    def get_conversation_history(
        self,
        include_system: bool = False,
        limit: Optional[int] = None,
    ) -> list[dict[str, str]]:
        """
        Get conversation history as message dicts.

        Args:
            include_system: Include system messages.
            limit: Maximum number of recent messages to return.

        Returns:
            List of {"role": ..., "content": ...} dicts.
        """
        messages = []
        for msg in self._conversation:
            if msg.role == "system" and not include_system:
                continue
            messages.append({"role": msg.role, "content": msg.content})

        if limit:
            return messages[-limit:]

        return messages

    def get_recent_count(self) -> int:
        """Get number of messages currently in memory."""
        return len(self._conversation)

    def should_consolidate(self) -> bool:
        """Check if consolidation should be triggered."""
        return (
            self.enabled
            and self._message_count >= self.consolidation_threshold
            and self._message_count % self.consolidation_threshold == 0
        )

    def _load_persistent_memory(self) -> None:
        """Load persistent memory from disk."""
        memory_file = self.memory_dir / "persistent_memory.txt"
        if memory_file.exists():
            try:
                content = memory_file.read_text(encoding="utf-8").strip()
                if content:
                    self._conversation.appendleft(
                        Message(role="system", content=f"[PERSISTENT MEMORY]\n{content}")
                    )
                    logger.info(f"Loaded persistent memory: {len(content)} chars")
            except Exception as e:
                logger.warning(f"Failed to load persistent memory: {e}")

    def save_persistent_memory(self, content: str) -> None:
        """Save content to persistent memory file."""
        if not self.enabled:
            return
        memory_file = self.memory_dir / "persistent_memory.txt"
        try:
            memory_file.write_text(content.strip(), encoding="utf-8")
            logger.info(f"Saved persistent memory: {len(content)} chars")
        except Exception as e:
            logger.error(f"Failed to save persistent memory: {e}")

    def clear(self) -> None:
        """Clear all conversation memory."""
        self._conversation.clear()
        self._message_count = 0
        logger.info("Memory cleared")

    def summarize(self, summarizer) -> str:
        """
        Summarize recent conversation for consolidation.

        Args:
            summarizer: Callable that takes text and returns a summary.

        Returns:
            The generated summary.
        """
        recent_text = "\n".join(
            f"[{msg.role}]: {msg.content}"
            for msg in list(self._conversation)[-self.consolidation_threshold:]
        )

        summary = summarizer(
            f"Summarize the following conversation concisely. "
            f"Preserve key facts, decisions, and user preferences:\n\n{recent_text}"
        )

        self._message_count = 0  # Reset after consolidation
        self._last_summary_time = time.time()

        return summary

    def __repr__(self) -> str:
        return f"<Memory messages={len(self._conversation)} total={self._message_count}>"
