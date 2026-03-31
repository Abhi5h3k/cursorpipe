"""Preflight checks — validate that prerequisites are met before running.

These tests are designed to be run FIRST.  They tell you exactly what's
missing (agent binary, auth, connectivity) instead of failing with cryptic
errors deeper in the test suite.

Run with:  pytest tests/test_preflight.py -v
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from cursorpipe._config import CursorPipeConfig
from cursorpipe._errors import AgentNotFoundError
from cursorpipe._resolve import resolve_agent_command


@pytest.mark.preflight
class TestAgentBinary:
    """Check that the Cursor agent binary is installed and reachable."""

    def test_agent_on_path_or_configured(self) -> None:
        """The agent binary must be discoverable."""
        config = CursorPipeConfig()
        try:
            cmd = resolve_agent_command(config)
            assert len(cmd) >= 1, "resolve_agent_command returned an empty list"
        except AgentNotFoundError as exc:
            pytest.fail(
                f"PREREQUISITE FAILED: Cursor agent binary not found.\n"
                f"Searched: {exc.searched_paths}\n\n"
                f"FIX: Install the Cursor CLI:\n"
                f"  curl https://cursor.com/install -fsS | bash\n"
                f"Or set CURSORPIPE_AGENT_BIN to its full path.\n"
                f"Windows users: set CURSOR_AGENT_NODE and CURSOR_AGENT_SCRIPT."
            )

    def test_agent_is_executable(self) -> None:
        """The resolved binary must actually be executable."""
        config = CursorPipeConfig()
        try:
            cmd = resolve_agent_command(config)
        except AgentNotFoundError:
            pytest.skip("Agent binary not found (see test_agent_on_path_or_configured)")

        binary = cmd[0]
        if sys.platform == "win32":
            assert os.path.isfile(binary), f"Binary not a file: {binary}"
        else:
            assert os.access(binary, os.X_OK), f"Binary not executable: {binary}"

    def test_agent_version_runs(self) -> None:
        """``agent --version`` (or equivalent) must exit cleanly."""
        config = CursorPipeConfig()
        try:
            cmd = resolve_agent_command(config)
        except AgentNotFoundError:
            pytest.skip("Agent binary not found")

        result = subprocess.run(
            [*cmd, "--version"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0, (
            f"agent --version failed (exit {result.returncode}).\n"
            f"stdout: {result.stdout[:500]}\n"
            f"stderr: {result.stderr[:500]}"
        )


@pytest.mark.preflight
class TestAuthentication:
    """Check that Cursor authentication is configured."""

    def test_auth_env_or_login(self) -> None:
        """At least one auth method must be available."""
        has_api_key = bool(os.getenv("CURSOR_API_KEY") or os.getenv("CURSORPIPE_API_KEY"))
        has_auth_token = bool(os.getenv("CURSOR_AUTH_TOKEN") or os.getenv("CURSORPIPE_AUTH_TOKEN"))

        has_login_session = False
        config = CursorPipeConfig()
        try:
            cmd = resolve_agent_command(config)
            result = subprocess.run(
                [*cmd, "status"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            has_login_session = result.returncode == 0
        except (AgentNotFoundError, subprocess.TimeoutExpired, FileNotFoundError):
            pass

        assert has_api_key or has_auth_token or has_login_session, (
            "PREREQUISITE FAILED: No Cursor authentication found.\n\n"
            "FIX (pick one):\n"
            "  1. Run: agent login\n"
            "  2. Set env var: CURSOR_API_KEY=your-key\n"
            "  3. Set env var: CURSOR_AUTH_TOKEN=your-token"
        )


@pytest.mark.preflight
class TestConnectivity:
    """Check that the agent can reach Cursor's API."""

    def test_agent_responds(self) -> None:
        """A minimal prompt should return a response."""
        config = CursorPipeConfig()
        try:
            cmd = resolve_agent_command(config)
        except AgentNotFoundError:
            pytest.skip("Agent binary not found")

        env = {**os.environ, **config.resolve_auth_env()}
        result = subprocess.run(
            [*cmd, "--trust", "--print", "--mode", "ask", "--output-format", "text",
             "Reply with exactly: CURSORPIPE_OK"],
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
        assert result.returncode == 0, (
            f"PREREQUISITE FAILED: Agent could not complete a test prompt.\n"
            f"exit code: {result.returncode}\n"
            f"stderr: {result.stderr[:500]}\n\n"
            f"This usually means auth is invalid or Cursor's API is unreachable."
        )
        assert len(result.stdout.strip()) > 0, (
            "Agent returned empty output.  Check auth and connectivity."
        )


@pytest.mark.preflight
class TestModelDiscovery:
    """Check that models can be listed."""

    def test_list_models(self) -> None:
        """``agent --list-models`` should return at least one model."""
        config = CursorPipeConfig()
        try:
            cmd = resolve_agent_command(config)
        except AgentNotFoundError:
            pytest.skip("Agent binary not found")

        env = {**os.environ, **config.resolve_auth_env()}
        result = subprocess.run(
            [*cmd, "--list-models"],
            capture_output=True,
            text=True,
            timeout=15,
            env=env,
        )
        if result.returncode != 0:
            pytest.skip(f"--list-models not supported (exit {result.returncode})")

        models = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        assert len(models) > 0, (
            "No models returned by `agent --list-models`.  "
            "Check your Cursor subscription and auth."
        )
