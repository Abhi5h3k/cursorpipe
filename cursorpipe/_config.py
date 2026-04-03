"""Configuration for cursorpipe.

Settings are loaded from environment variables prefixed with ``CURSORPIPE_``
(e.g. ``CURSORPIPE_AGENT_BIN``).  Falls back to Cursor-native env vars
(``CURSOR_API_KEY``, ``CURSOR_AUTH_TOKEN``, ``CURSOR_AGENT_NODE``, etc.)
for zero-config when the user already has Cursor set up.
"""

from __future__ import annotations

import os
from enum import StrEnum
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings


class Strategy(StrEnum):
    """Transport strategy for reaching the Cursor agent."""

    ACP = "acp"
    SUBPROCESS = "subprocess"
    AUTO = "auto"


class CursorPipeConfig(BaseSettings):
    """All tunables for cursorpipe, loadable from env vars."""

    model_config = {"env_prefix": "CURSORPIPE_", "env_file": ".env", "extra": "ignore"}

    # -- Agent binary ----------------------------------------------------------
    agent_bin: str = Field(
        default="agent",
        description="Path to the Cursor agent binary, or just 'agent' to search PATH.",
    )
    agent_node: str = Field(
        default="",
        description=(
            "Windows: path to node.exe bundled with cursor-agent. "
            "Overridden by CURSOR_AGENT_NODE env var."
        ),
    )
    agent_script: str = Field(
        default="",
        description=(
            "Windows: path to index.js bundled with cursor-agent. "
            "Overridden by CURSOR_AGENT_SCRIPT env var."
        ),
    )

    # -- Auth ------------------------------------------------------------------
    api_key: str = Field(default="", description="Cursor API key.")
    auth_token: str = Field(default="", description="Cursor auth token.")

    # -- Strategy / behaviour --------------------------------------------------
    strategy: Strategy = Field(
        default=Strategy.AUTO,
        description=(
            "Transport: 'acp' (persistent), 'subprocess' (per-request), "
            "'auto' (try ACP first)."
        ),
    )
    default_mode: Literal["ask", "plan", "agent"] = Field(
        default="ask",
        description="Default ACP/CLI mode. 'ask' = pure LLM, no tool access.",
    )

    # -- Timeouts --------------------------------------------------------------
    request_timeout_s: float = Field(
        default=300.0,
        description="Per-request timeout in seconds.",
    )
    acp_startup_timeout_s: float = Field(
        default=30.0,
        description="Max seconds to wait for the ACP process to initialise.",
    )

    # -- ACP specifics ---------------------------------------------------------
    acp_max_restarts: int = Field(
        default=3,
        description="How many times to auto-restart a crashed ACP process before giving up.",
    )

    # -- Workspace -------------------------------------------------------------
    workspace: str = Field(
        default="",
        description="Working directory passed to the agent.  Empty = cwd at call time.",
    )

    # -- Performance -----------------------------------------------------------
    enable_profiling: bool = Field(
        default=False,
        description=(
            "Log timing diagnostics: time-to-first-chunk (TTFC), per-chunk "
            "inter-arrival, session acquire latency, and streaming duration."
        ),
    )

    def resolve_auth_env(self) -> dict[str, str]:
        """Return env-var overrides for the agent subprocess."""
        env: dict[str, str] = {}
        api_key = self.api_key or os.getenv("CURSOR_API_KEY", "")
        auth_token = self.auth_token or os.getenv("CURSOR_AUTH_TOKEN", "")
        if api_key:
            env["CURSOR_API_KEY"] = api_key
        if auth_token:
            env["CURSOR_AUTH_TOKEN"] = auth_token
        return env

    def resolve_auth_args(self) -> list[str]:
        """Return CLI flags for authentication.

        Only ``--api-key`` is an official CLI flag (per Cursor docs).
        ``auth_token`` is passed via env var only (see ``resolve_auth_env``).
        When neither is set, the agent uses the session from ``agent login``.
        """
        api_key = self.api_key or os.getenv("CURSOR_API_KEY", "")
        if api_key:
            return ["--api-key", api_key]
        return []

    def resolve_node_paths(self) -> tuple[str, str]:
        """Return (node_exe, script_path) for Windows direct-spawn."""
        node = self.agent_node or os.getenv("CURSOR_AGENT_NODE", "")
        script = self.agent_script or os.getenv("CURSOR_AGENT_SCRIPT", "")
        return os.path.expandvars(node), os.path.expandvars(script)
