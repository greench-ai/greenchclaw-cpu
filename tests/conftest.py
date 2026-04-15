"""GreenClaw CPU — Pytest Configuration."""

import pytest


def pytest_configure(config):
    """Configure pytest."""
    config.addinivalue_line("markers", "asyncio: mark test as async")


# Enable asyncio mode for all async tests
pytest_plugins = []
