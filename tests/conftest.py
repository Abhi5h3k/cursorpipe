"""Shared fixtures for cursorpipe tests."""

from __future__ import annotations

import pytest

from cursorpipe import CursorClient, CursorPipeConfig


@pytest.fixture
def default_config() -> CursorPipeConfig:
    """Config loaded from env with defaults."""
    return CursorPipeConfig()


@pytest.fixture
def client(default_config: CursorPipeConfig) -> CursorClient:
    """A CursorClient instance using default config."""
    return CursorClient(default_config)
