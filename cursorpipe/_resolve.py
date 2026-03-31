"""Resolve the Cursor agent binary across platforms.

Resolution order:
1. CURSORPIPE_AGENT_BIN env var / config (explicit path)
2. Windows direct-spawn: CURSOR_AGENT_NODE + CURSOR_AGENT_SCRIPT
3. ``agent`` / ``agent.exe`` on PATH
4. Platform-specific default install locations
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from cursorpipe._config import CursorPipeConfig
from cursorpipe._errors import AgentNotFoundError


def _win_default_locations() -> list[Path]:
    """Common install paths on Windows."""
    locations: list[Path] = []
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        agent_dir = Path(local) / "cursor-agent"
        if agent_dir.exists():
            for version_dir in sorted(agent_dir.glob("versions/*"), reverse=True):
                node = version_dir / "node.exe"
                script = version_dir / "index.js"
                if node.exists() and script.exists():
                    locations.append(node)
                    break
        programs = Path(local) / "Programs" / "cursor" / "resources" / "app" / "agent"
        if programs.exists():
            locations.append(programs / "agent.exe")
    home_bin = Path.home() / ".local" / "bin" / "agent.exe"
    locations.append(home_bin)
    return locations


def _unix_default_locations() -> list[Path]:
    """Common install paths on macOS/Linux."""
    return [
        Path.home() / ".local" / "bin" / "agent",
        Path("/usr/local/bin/agent"),
    ]


def resolve_agent_command(config: CursorPipeConfig) -> list[str]:
    """Return the command list to spawn the Cursor agent.

    On Windows, if ``CURSOR_AGENT_NODE`` and ``CURSOR_AGENT_SCRIPT`` are set,
    returns ``[node.exe, index.js, ...]`` to bypass the 8191-char cmd.exe limit.
    Otherwise returns ``[agent_binary_path]``.

    Raises ``AgentNotFoundError`` if no usable binary is found.
    """
    searched: list[str] = []

    # 1. Explicit config / env var
    if config.agent_bin and config.agent_bin != "agent":
        expanded = os.path.expandvars(config.agent_bin)
        if Path(expanded).exists():
            return [expanded]
        searched.append(expanded)

    # 2. Windows: direct node+script (bypasses cmd.exe char limit)
    if sys.platform == "win32":
        node, script = config.resolve_node_paths()
        if node and script and Path(node).exists() and Path(script).exists():
            return [node, script]
        if node or script:
            searched.append(f"node={node}, script={script}")

    # 3. PATH lookup
    on_path = shutil.which("agent")
    if on_path:
        return [on_path]
    searched.append("PATH (agent)")

    # 4. Platform defaults
    defaults = _win_default_locations() if sys.platform == "win32" else _unix_default_locations()
    for loc in defaults:
        if loc.exists():
            if sys.platform == "win32" and loc.name == "node.exe":
                script_path = loc.parent / "index.js"
                if script_path.exists():
                    return [str(loc), str(script_path)]
            return [str(loc)]
        searched.append(str(loc))

    raise AgentNotFoundError(searched)


def check_agent_available(config: CursorPipeConfig) -> list[str]:
    """Like ``resolve_agent_command`` but returns the command or raises with helpful detail."""
    return resolve_agent_command(config)
