"""Typed exceptions for cursorpipe.

Every error inherits from CursorPipeError so callers can catch broadly
or narrowly.  Each subclass carries structured context (not just a string)
so automated retry/reporting logic can inspect it.
"""

from __future__ import annotations


class CursorPipeError(Exception):
    """Base for all cursorpipe errors."""


class AgentNotFoundError(CursorPipeError):
    """The ``agent`` binary could not be located."""

    def __init__(self, searched_paths: list[str]) -> None:
        self.searched_paths = searched_paths
        paths = ", ".join(searched_paths) or "(none)"
        super().__init__(
            f"Cursor agent binary not found. Searched: {paths}. "
            "Install it: https://cursor.com/docs/cli/installation "
            "or set CURSORPIPE_AGENT_BIN."
        )


class AuthenticationError(CursorPipeError):
    """Authentication with Cursor failed or is missing."""

    def __init__(self, detail: str = "") -> None:
        self.detail = detail
        msg = "Cursor authentication failed."
        if detail:
            msg += f" {detail}"
        msg += " Run `agent login` or set CURSOR_API_KEY."
        super().__init__(msg)


class AgentTimeoutError(CursorPipeError):
    """A request to the Cursor agent exceeded the configured timeout."""

    def __init__(self, timeout_s: float, context: str = "") -> None:
        self.timeout_s = timeout_s
        self.context = context
        super().__init__(f"Agent request timed out after {timeout_s}s. {context}".strip())


class RateLimitError(CursorPipeError):
    """Cursor returned a 429 / rate-limit response."""

    def __init__(self, retry_after_s: float | None = None) -> None:
        self.retry_after_s = retry_after_s
        msg = "Rate-limited by Cursor."
        if retry_after_s is not None:
            msg += f" Retry after {retry_after_s}s."
        super().__init__(msg)


class AgentCrashError(CursorPipeError):
    """The agent process exited unexpectedly."""

    def __init__(self, exit_code: int, stderr: str = "") -> None:
        self.exit_code = exit_code
        self.stderr = stderr
        msg = f"Agent process crashed (exit code {exit_code})."
        if stderr:
            msg += f"\nstderr: {stderr[:500]}"
        super().__init__(msg)


class SessionError(CursorPipeError):
    """Error managing an ACP session (create / load / prompt)."""

    def __init__(self, detail: str, session_id: str | None = None) -> None:
        self.detail = detail
        self.session_id = session_id
        prefix = f"[session {session_id}] " if session_id else ""
        super().__init__(f"{prefix}{detail}")
