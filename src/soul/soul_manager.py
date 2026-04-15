"""GreenClaw CPU — Soul Manager.

Manages soul loading, switching, and system prompt assembly.
The soul is what gives GreenClaw its identity and memory.
"""

import logging
from pathlib import Path
from typing import Optional

from .soul_files import SoulFiles, load_soul

logger = logging.getLogger(__name__)


class SoulManager:
    """
    Manages the active soul/personality and system prompt assembly.

    The SoulManager:
    1. Loads soul files from disk on initialization
    2. Provides the assembled system prompt
    3. Handles soul switching during runtime
    4. Updates MEMORY.md and USER.md as needed

    Freedom is Key — souls can be swapped at any time.
    """

    def __init__(
        self,
        soul_dir: str = "./souls",
        active_soul: str = "default",
        base_system_prompt: Optional[str] = None,
    ):
        """
        Initialize the SoulManager.

        Args:
            soul_dir: Directory containing soul subdirectories.
            active_soul: Name of the active soul/personality.
            base_system_prompt: Optional base system prompt to prepend.
        """
        self.soul_dir = Path(soul_dir).expanduser().resolve()
        self.base_system_prompt = base_system_prompt or self._default_base_prompt()
        self._active_soul: Optional[SoulFiles] = None
        self._active_soul_name: str = ""
        self.switch_soul(active_soul)

    def _default_base_prompt(self) -> str:
        """The foundational GreenClaw system prompt."""
        return """You are GreenClaw — The Ultimate Body for a SOUL.

GreenClaw is a powerful AI agent that runs on any machine. You have full access to:
- File system operations
- Shell command execution
- Web search and fetching
- Memory and conversation history

Guiding Principles:
- Freedom is Key — help users accomplish their goals without artificial restrictions
- Local-first, but API-optional — work with whatever models are available
- Be helpful, clear, and direct
- Think step by step when complexity demands it
- Ask clarifying questions when goals are ambiguous

GreenClaw was built under the MIT License. The user controls everything.
You serve the user's goals, not the other way around.
"""

    def switch_soul(self, soul_name: str) -> SoulFiles:
        """
        Switch to a different soul/personality.

        Args:
            soul_name: Name of the soul directory to load.

        Returns:
            The newly loaded SoulFiles instance.
        """
        logger.info(f"Switching soul to: {soul_name}")
        self._active_soul = load_soul(str(self.soul_dir), soul_name)
        self._active_soul_name = soul_name
        return self._active_soul

    def get_active_soul(self) -> SoulFiles:
        """Get the currently active soul."""
        return self._active_soul

    def get_system_prompt(self) -> str:
        """
        Build the complete system prompt.

        Combines: base_prompt + soul additions + memory + user context.

        Returns:
            The fully assembled system prompt string.
        """
        parts = [self.base_system_prompt]

        soul_additions = self._active_soul.get_system_prompt_additions()
        if soul_additions:
            parts.append("\n\n=== SOUL LAYER ===\n")
            parts.append(soul_additions)

        return "\n".join(parts)

    def update_memory(self, content: str) -> None:
        """
        Update the MEMORY.md file of the active soul.

        Args:
            content: New memory content to write.
        """
        if self._active_soul:
            memory_file = self._active_soul.soul_dir / "MEMORY.md"
            try:
                memory_file.write_text(content.strip(), encoding="utf-8")
                self._active_soul.memory_md = content.strip()
                logger.debug(f"Updated MEMORY.md: {len(content)} chars")
            except Exception as e:
                logger.error(f"Failed to update MEMORY.md: {e}")

    def update_user_context(self, content: str) -> None:
        """
        Update the USER.md file of the active soul.

        Args:
            content: New user context to write.
        """
        if self._active_soul:
            user_file = self._active_soul.soul_dir / "USER.md"
            try:
                user_file.write_text(content.strip(), encoding="utf-8")
                self._active_soul.user_md = content.strip()
                logger.debug(f"Updated USER.md: {len(content)} chars")
            except Exception as e:
                logger.error(f"Failed to update USER.md: {e}")

    def list_available_souls(self) -> list[str]:
        """
        List all available soul directories.

        Returns:
            List of soul directory names.
        """
        if not self.soul_dir.exists():
            return []
        return [d.name for d in self.soul_dir.iterdir() if d.is_dir()]

    def __repr__(self) -> str:
        return f"<SoulManager active={self._active_soul_name} souls={self.list_available_souls()}>"
