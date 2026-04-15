"""GreenClaw CPU — Memory Consolidation.

Automatic memory consolidation — summaries recent conversations
and integrates them into the soul's persistent memory.

This keeps context windows efficient while preserving
important information across sessions.
"""

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class MemoryConsolidator:
    """
    Handles automatic memory consolidation.

    Consolidation triggers:
    1. After N messages (configurable threshold)
    2. On session end (if requested)

    The summarizer uses the same model that GreenClaw runs on —
    no separate service needed.
    """

    def __init__(
        self,
        memory_instance,
        soul_manager,
        model_provider,
        threshold: int = 50,
    ):
        self.memory = memory_instance
        self.soul_manager = soul_manager
        self.model = model_provider
        self.threshold = threshold
        self._consolidation_count = 0

    def check_and_consolidate(self) -> Optional[str]:
        """
        Check if consolidation is needed, and if so, perform it.

        Returns:
            The generated summary, or None if consolidation wasn't triggered.
        """
        if not self.memory.should_consolidate():
            return None

        return self.consolidate()

    def consolidate(self) -> str:
        """
        Perform memory consolidation.

        1. Get recent conversation
        2. Ask the model to summarize key information
        3. Update the soul's MEMORY.md
        4. Reset message counter

        Returns:
            The consolidation summary.
        """
        logger.info("Starting memory consolidation...")
        self._consolidation_count += 1

        recent = self.memory.get_conversation_history(limit=self.threshold)

        if not recent:
            logger.debug("No messages to consolidate")
            return ""

        # Build summary prompt
        summary_prompt = self._build_summary_prompt(recent)

        # Generate summary using the model
        try:
            import asyncio

            summary = asyncio.get_event_loop().run_until_complete(
                self.model.generate(summary_prompt)
            )
        except Exception as e:
            logger.error(f"Consolidation failed: {e}")
            return f"[Consolidation failed: {e}]"

        # Integrate with existing memory
        existing_memory = self.soul_manager.get_active_soul().memory_md or ""
        timestamp = time.strftime("%Y-%m-%d")

        new_memory_block = f"\n\n---\n[SESSION SUMMARY {timestamp}]---\n{summary.strip()}"

        updated_memory = existing_memory + new_memory_block

        # Update soul memory
        self.soul_manager.update_memory(updated_memory)

        # Also save to persistent memory file
        self.memory.save_persistent_memory(updated_memory)

        logger.info(
            f"Consolidation #{self._consolidation_count} complete. "
            f"Summary: {summary[:100]}..."
        )

        return summary

    def _build_summary_prompt(self, recent: list[dict[str, str]]) -> str:
        """Build the summarization prompt."""
        conv_text = "\n".join(
            f"[{msg['role']}]: {msg['content']}" for msg in recent
        )

        return f"""You are helping consolidate GreenClaw's memory. Analyze this conversation and produce a concise summary covering:

1. Key facts and information discussed
2. Any decisions made or conclusions reached
3. User preferences or requirements mentioned
4. Tasks started or completed
5. Important context for future sessions

CONVERSATION:
{conv_text}

Respond with ONLY the summary, no preamble. Be concise but capture everything important."""

    def consolidate_on_exit(self) -> None:
        """Consolidate remaining memory on session end."""
        if self.memory.get_recent_count() > 5:
            logger.info("Performing exit consolidation...")
            self.consolidate()
        else:
            logger.debug("Skipping exit consolidation (insufficient messages)")
