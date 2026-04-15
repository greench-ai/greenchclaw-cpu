"""GreenClaw CPU — Soul Loading Tests."""

import pytest
import tempfile
import shutil
from pathlib import Path


class TestSoulFiles:
    """Test soul file loading."""

    def test_load_soul_with_files(self):
        """Test loading a soul with all expected files."""
        from src.soul.soul_files import load_soul

        with tempfile.TemporaryDirectory() as tmpdir:
            soul_dir = Path(tmpdir) / "test_soul"
            soul_dir.mkdir()

            # Create soul files
            (soul_dir / "SOUL.md").write_text("# Test Soul\nI am a test soul.")
            (soul_dir / "IDENTITY.md").write_text("# Identity\nI am TestBot.")
            (soul_dir / "MEMORY.md").write_text("# Memory\nRemember this.")
            (soul_dir / "USER.md").write_text("# User\nUser prefers X.")

            soul = load_soul(tmpdir, "test_soul")

            assert soul.soul_name == "test_soul"
            assert "Test Soul" in soul.soul_md
            assert "Identity" in soul.identity_md
            assert "Remember this" in soul.memory_md
            assert "prefers X" in soul.user_md
            assert soul.loaded is True
            assert soul.is_complete() is True

    def test_load_soul_missing_files(self):
        """Test loading a soul with missing files (should not error)."""
        from src.soul.soul_files import load_soul

        with tempfile.TemporaryDirectory() as tmpdir:
            soul_dir = Path(tmpdir) / "empty_soul"
            soul_dir.mkdir()

            # Only SOUL.md
            (soul_dir / "SOUL.md").write_text("Minimal soul.")

            soul = load_soul(tmpdir, "empty_soul")

            assert soul.soul_md == "Minimal soul."
            assert soul.identity_md == ""
            assert soul.loaded is True

    def test_load_nonexistent_soul(self):
        """Test loading a soul that doesn't exist."""
        from src.soul.soul_files import load_soul

        with tempfile.TemporaryDirectory() as tmpdir:
            soul = load_soul(tmpdir, "does_not_exist")
            assert soul.soul_md == ""
            assert soul.loaded is True

    def test_system_prompt_additions(self):
        """Test system prompt assembly."""
        from src.soul.soul_files import SoulFiles

        soul = SoulFiles(soul_name="test")
        soul.identity_md = "I am TestBot."
        soul.soul_md = "I exist to test things."
        soul.rules_md = "Always be testing."

        additions = soul.get_system_prompt_additions()

        assert "IDENTITY" in additions
        assert "SOUL" in additions
        assert "RULES" in additions
        assert "TestBot" in additions
        assert "exist to test" in additions


class TestSoulManager:
    """Test SoulManager functionality."""

    def test_soul_manager_init(self):
        """Test SoulManager initialization."""
        from src.soul.soul_manager import SoulManager

        with tempfile.TemporaryDirectory() as tmpdir:
            soul_dir = Path(tmpdir) / "souls" / "test"
            soul_dir.mkdir(parents=True)

            (soul_dir / "SOUL.md").write_text("# Test")

            manager = SoulManager(soul_dir=tmpdir, active_soul="test")
            assert manager._active_soul_name == "test"
            assert manager._active_soul is not None

    def test_switch_soul(self):
        """Test soul switching."""
        from src.soul.soul_manager import SoulManager

        with tempfile.TemporaryDirectory() as tmpdir:
            soul_dir = Path(tmpdir)

            # Create two souls
            soul1 = soul_dir / "soul1"
            soul2 = soul_dir / "soul2"
            soul1.mkdir()
            soul2.mkdir()
            (soul1 / "SOUL.md").write_text("Soul One")
            (soul2 / "SOUL.md").write_text("Soul Two")

            manager = SoulManager(soul_dir=tmpdir, active_soul="soul1")
            assert "Soul One" in manager.get_active_soul().soul_md

            manager.switch_soul("soul2")
            assert manager._active_soul_name == "soul2"
            assert "Soul Two" in manager.get_active_soul().soul_md

    def test_system_prompt_contains_soul(self):
        """Test that system prompt includes soul content."""
        from src.soul.soul_manager import SoulManager

        with tempfile.TemporaryDirectory() as tmpdir:
            soul_dir = Path(tmpdir) / "mysoul"
            soul_dir.mkdir()
            (soul_dir / "SOUL.md").write_text("Custom soul content here.")

            manager = SoulManager(soul_dir=tmpdir, active_soul="mysoul")
            prompt = manager.get_system_prompt()

            assert "Custom soul content" in prompt
            assert "GreenClaw" in prompt  # Base prompt

    def test_list_available_souls(self):
        """Test listing available souls."""
        from src.soul.soul_manager import SoulManager

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "soul_a").mkdir()
            (Path(tmpdir) / "soul_b").mkdir()

            manager = SoulManager(soul_dir=tmpdir, active_soul="soul_a")
            souls = manager.list_available_souls()

            assert "soul_a" in souls
            assert "soul_b" in souls

    def test_update_memory(self):
        """Test updating soul memory."""
        from src.soul.soul_manager import SoulManager

        with tempfile.TemporaryDirectory() as tmpdir:
            soul_dir = Path(tmpdir) / "mem_test"
            soul_dir.mkdir()
            (soul_dir / "SOUL.md").write_text("Soul")
            (soul_dir / "MEMORY.md").write_text("Old memory")

            manager = SoulManager(soul_dir=tmpdir, active_soul="mem_test")
            manager.update_memory("New memory content")

            assert manager.get_active_soul().memory_md == "New memory content"
            assert (soul_dir / "MEMORY.md").read_text() == "New memory content"
