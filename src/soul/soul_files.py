"""GreenClaw CPU — Soul File Definitions.

SOUL.md, IDENTITY.md, MEMORY.md, USER.md are loaded and injected
into the system prompt. This is what makes GreenClaw... GreenClaw.

Freedom is Key — customize your soul freely.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class SoulFiles:
    """
    Represents a loaded soul/personality.

    Soul files are markdown files in a soul directory:
      - SOUL.md      : Core purpose, values, and behavior guidelines
      - IDENTITY.md : Who GreenClaw is — name, personality, voice
      - MEMORY.md   : Persistent memory and context
      - USER.md     : User preferences and known info
      - RULES.md    : Optional operational rules
    """

    soul_name: str = "default"
    soul_dir: Path = field(default_factory=lambda: Path("./souls/default"))

    soul_md: str = ""
    identity_md: str = ""
    memory_md: str = ""
    user_md: str = ""
    rules_md: str = ""

    loaded: bool = False

    def is_complete(self) -> bool:
        """Check if the soul has its core files."""
        return bool(self.soul_md or self.identity_md)

    def get_system_prompt_additions(self) -> str:
        """
        Build the soul addition for the system prompt.

        Returns formatted markdown that gets prepended to the
        system prompt. Freedom is Key — no artificial limits.
        """
        parts = []

        if self.identity_md:
            parts.append(f"## 🤖 IDENTITY\n{self.identity_md}")

        if self.soul_md:
            parts.append(f"## 🧬 SOUL\n{self.soul_md}")

        if self.rules_md:
            parts.append(f"## 📋 RULES\n{self.rules_md}")

        if self.memory_md:
            parts.append(f"## 🧠 MEMORY\n{self.memory_md}")

        if self.user_md:
            parts.append(f"## 👤 USER CONTEXT\n{self.user_md}")

        if not parts:
            return ""

        return "\n\n".join(parts)

    def __repr__(self) -> str:
        status = "✓ loaded" if self.loaded else "✗ empty"
        return f"<SoulFiles name={self.soul_name} [{status}]>"


def load_soul_file(soul_dir: Path, filename: str) -> str:
    """Load a single soul file, return empty string if missing."""
    file_path = soul_dir / filename
    if file_path.exists() and file_path.is_file():
        try:
            content = file_path.read_text(encoding="utf-8").strip()
            logger.debug(f"Loaded soul file: {file_path}")
            return content
        except Exception as e:
            logger.warning(f"Failed to read soul file {file_path}: {e}")
            return ""
    return ""


def load_soul(soul_dir: str, soul_name: str) -> SoulFiles:
    """
    Load all soul files for a given soul/personality.

    Args:
        soul_dir: Base directory containing soul subdirectories.
        soul_name: Name of the soul subdirectory to load.

    Returns:
        A SoulFiles dataclass with all loaded content.
    """
    soul_path = Path(soul_dir).expanduser().resolve() / soul_name

    if not soul_path.exists():
        logger.warning(f"Soul directory not found: {soul_path}")
        # Try loading from the soul_dir itself (flat structure)
        soul_path = Path(soul_dir).expanduser().resolve()

    soul = SoulFiles(soul_name=soul_name, soul_dir=soul_path)

    soul.soul_md = load_soul_file(soul_path, "SOUL.md")
    soul.identity_md = load_soul_file(soul_path, "IDENTITY.md")
    soul.memory_md = load_soul_file(soul_path, "MEMORY.md")
    soul.user_md = load_soul_file(soul_path, "USER.md")
    soul.rules_md = load_soul_file(soul_path, "RULES.md")

    soul.loaded = True
    logger.info(f"Loaded soul '{soul_name}' from {soul_path}")
    return soul
