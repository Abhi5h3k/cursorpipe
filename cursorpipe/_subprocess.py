"""Subprocess transport — spawns a fresh ``agent`` process per request.

Fallback for environments where ACP doesn't work.  Prompts are written to
a temporary file and passed as the last CLI argument to avoid the Windows
8191-char command-line limit.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

from cursorpipe._config import CursorPipeConfig
from cursorpipe._errors import AgentCrashError, AgentTimeoutError, NetworkError, RateLimitError
from cursorpipe._models import CompletionResult
from cursorpipe._ndjson import StreamAccumulator, iter_ndjson_lines
from cursorpipe._resolve import resolve_agent_command

logger = logging.getLogger(__name__)

# Strict word-boundary pattern — avoids false positives on words like
# "generate", "separate", "accurate", "iterate" that contain "rate" as a substring.
_RATE_LIMIT_RE = re.compile(
    r"\b429\b|\brate[\s_-]?limit|\btoo\s+many\s+requests\b",
    re.IGNORECASE,
)

_NETWORK_ERROR_PATTERNS = (
    "unable to get local issuer certificate",
    "could not resolve host",
    "connection refused",
    "check that your proxy",
    "failed to reach the cursor api",
    "econnrefused",
    "enotfound",
    "etimedout",
    "certificate verify failed",
    "ssl",
)


def _is_rate_limited(stderr: str) -> bool:
    return bool(_RATE_LIMIT_RE.search(stderr))


def _is_network_error(stderr: str) -> bool:
    lower = stderr.lower()
    return any(p in lower for p in _NETWORK_ERROR_PATTERNS)


def _last_meaningful_line(stderr: str) -> str:
    """Return the last non-empty line of stderr, or the whole string if short."""
    lines = [ln.strip() for ln in stderr.splitlines() if ln.strip()]
    return lines[-1] if lines else stderr.strip()


def _build_args(
    config: CursorPipeConfig,
    model: str,
    *,
    stream: bool = False,
) -> list[str]:
    """Build CLI arguments (without the prompt — that comes separately)."""
    auth_args = config.resolve_auth_args()
    args = [*auth_args, "--trust", "--print", "--mode", config.default_mode]
    args.extend(["--model", model])
    if config.workspace:
        args.extend(["--workspace", config.workspace])
    if stream:
        args.extend(["--stream-partial-output", "--output-format", "stream-json"])
    else:
        args.extend(["--output-format", "json"])
    return args


class SubprocessTransport:
    """Spawns ``agent --print`` per request.  Stateless — no session reuse."""

    def __init__(self, config: CursorPipeConfig) -> None:
        self._config = config

    async def generate(
        self,
        model: str,
        prompt: str,
        *,
        timeout_s: float | None = None,
    ) -> CompletionResult:
        """Run a single non-streaming completion."""
        cmd = resolve_agent_command(self._config)
        args = _build_args(self._config, model, stream=False)

        # Write prompt to a temp file to avoid Windows cmdline limit
        tmp = self._write_prompt_file(prompt)
        try:
            full_cmd = [*cmd, *args, f"@{tmp}"]
            env = {**os.environ, **self._config.resolve_auth_env()}
            timeout = timeout_s or self._config.request_timeout_s

            logger.debug("Subprocess: %s", " ".join(full_cmd))
            proc = await asyncio.create_subprocess_exec(
                *full_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=self._config.workspace or None,
            )
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except TimeoutError:
                proc.kill()
                raise AgentTimeoutError(timeout, f"model={model}")

            stderr_text = stderr_bytes.decode("utf-8", errors="replace")
            if _is_rate_limited(stderr_text):
                raise RateLimitError(detail=stderr_text)
            if proc.returncode != 0:
                if _is_network_error(stderr_text):
                    raise NetworkError(_last_meaningful_line(stderr_text))
                raise AgentCrashError(proc.returncode or -1, stderr_text)

            stdout_text = stdout_bytes.decode("utf-8", errors="replace").strip()
            return self._parse_json_result(stdout_text, model)
        finally:
            Path(tmp).unlink(missing_ok=True)

    async def generate_stream(
        self,
        model: str,
        prompt: str,
        *,
        timeout_s: float | None = None,
    ) -> AsyncIterator[str]:
        """Run a streaming completion, yielding text chunks."""
        cmd = resolve_agent_command(self._config)
        args = _build_args(self._config, model, stream=True)

        tmp = self._write_prompt_file(prompt)
        try:
            full_cmd = [*cmd, *args, f"@{tmp}"]
            env = {**os.environ, **self._config.resolve_auth_env()}
            timeout = timeout_s or self._config.request_timeout_s

            proc = await asyncio.create_subprocess_exec(
                *full_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=self._config.workspace or None,
            )

            assert proc.stdout is not None
            accumulator = StreamAccumulator()

            deadline = asyncio.get_event_loop().time() + timeout
            async for event in iter_ndjson_lines(proc.stdout):
                if asyncio.get_event_loop().time() > deadline:
                    proc.kill()
                    raise AgentTimeoutError(timeout, f"model={model}")

                delta = accumulator.feed(event)
                if delta:
                    yield delta
                if accumulator.done:
                    break

            await proc.wait()

            if proc.returncode and proc.returncode != 0:
                stderr_bytes = await proc.stderr.read() if proc.stderr else b""
                stderr_text = stderr_bytes.decode("utf-8", errors="replace")
                if _is_rate_limited(stderr_text):
                    raise RateLimitError(detail=stderr_text)
                if _is_network_error(stderr_text):
                    raise NetworkError(_last_meaningful_line(stderr_text))
                raise AgentCrashError(proc.returncode, stderr_text)
        finally:
            Path(tmp).unlink(missing_ok=True)

    @staticmethod
    def _write_prompt_file(prompt: str) -> str:
        """Write the prompt to a temp file and return its path."""
        fd, path = tempfile.mkstemp(suffix=".txt", prefix="cursorpipe_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(prompt)
        return path

    @staticmethod
    def _parse_json_result(stdout: str, model: str) -> CompletionResult:
        """Parse the JSON output from ``--output-format json``."""
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return CompletionResult(text=stdout, model=model)

        return CompletionResult(
            text=data.get("result", stdout),
            model=model,
            session_id=data.get("session_id", ""),
            duration_ms=data.get("duration_ms", 0),
            stop_reason="stop" if data.get("subtype") == "success" else "",
        )
