"""ACP (Agent Client Protocol) transport — persistent agent process.

Spawns ``agent acp`` once and communicates via stdin/stdout JSON-RPC.
Sessions are pooled per model so switching models is cheap.  The process
auto-restarts on crash up to ``acp_max_restarts`` times.

Protocol reference: https://cursor.com/docs/cli/acp
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator
from typing import Any

from cursorpipe._config import CursorPipeConfig
from cursorpipe._errors import (
    AgentCrashError,
    AgentTimeoutError,
    AuthenticationError,
    SessionError,
)
from cursorpipe._models import CompletionResult
from cursorpipe._resolve import resolve_agent_command

logger = logging.getLogger(__name__)

_CLIENT_INFO = {"name": "cursorpipe", "version": "0.1.0"}


class AcpTransport:
    """Manages a persistent ``agent acp`` subprocess and JSON-RPC communication."""

    def __init__(self, config: CursorPipeConfig) -> None:
        self._config = config
        self._process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._next_id: int = 1
        self._pending: dict[int, asyncio.Future[dict]] = {}
        self._notification_handlers: dict[str, list[asyncio.Queue[dict]]] = {}
        self._initialized: bool = False
        self._restart_count: int = 0
        self._lock = asyncio.Lock()
        self._sessions: dict[str, str] = {}  # model -> session_id

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def ensure_started(self) -> None:
        """Start the ACP process if not already running."""
        async with self._lock:
            if self._process is not None and self._process.returncode is None:
                return
            await self._start()

    async def _start(self) -> None:
        cmd = resolve_agent_command(self._config)
        auth_args = self._config.resolve_auth_args()
        args = [*cmd, *auth_args, "acp"]

        env = {**os.environ, **self._config.resolve_auth_env()}

        logger.info("Starting ACP process: %s", " ".join(args))
        self._process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=self._config.workspace or None,
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        self._initialized = False
        self._sessions.clear()

        await self._initialize()

    async def _initialize(self) -> None:
        """Send the ACP initialize + authenticate handshake."""
        try:
            await asyncio.wait_for(
                self._do_initialize(),
                timeout=self._config.acp_startup_timeout_s,
            )
        except TimeoutError:
            await self.close()
            raise AgentTimeoutError(
                self._config.acp_startup_timeout_s,
                "ACP process did not complete initialization handshake.",
            )

    async def _do_initialize(self) -> None:
        result = await self._send(
            "initialize",
            {
                "protocolVersion": 1,
                "clientCapabilities": {
                    "fs": {"readTextFile": False, "writeTextFile": False},
                    "terminal": False,
                },
                "clientInfo": _CLIENT_INFO,
            },
        )
        logger.debug("ACP initialize result: %s", result)

        auth_result = await self._send("authenticate", {"methodId": "cursor_login"})
        if isinstance(auth_result, dict) and auth_result.get("error"):
            raise AuthenticationError(str(auth_result["error"]))
        logger.info("ACP authenticated successfully")
        self._initialized = True

    async def close(self) -> None:
        """Shut down the ACP process gracefully."""
        self._sessions.clear()
        if self._process and self._process.stdin and not self._process.stdin.is_closing():
            self._process.stdin.close()
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        if self._process and self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except TimeoutError:
                self._process.kill()
        self._process = None
        self._initialized = False
        for fut in self._pending.values():
            if not fut.done():
                fut.cancel()
        self._pending.clear()

    # ------------------------------------------------------------------
    # JSON-RPC I/O
    # ------------------------------------------------------------------

    async def _send(self, method: str, params: dict | None = None) -> dict:
        """Send a JSON-RPC request and wait for the response."""
        if self._process is None or self._process.stdin is None:
            raise AgentCrashError(-1, "ACP process is not running")

        msg_id = self._next_id
        self._next_id += 1

        payload = {"jsonrpc": "2.0", "id": msg_id, "method": method}
        if params is not None:
            payload["params"] = params

        line = json.dumps(payload) + "\n"
        self._process.stdin.write(line.encode("utf-8"))
        await self._process.stdin.drain()

        future: asyncio.Future[dict] = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = future
        return await future

    def _respond(self, msg_id: int, result: dict) -> None:
        """Send a JSON-RPC response (for server-initiated requests like permission)."""
        if self._process is None or self._process.stdin is None:
            return
        payload = {"jsonrpc": "2.0", "id": msg_id, "result": result}
        line = json.dumps(payload) + "\n"
        self._process.stdin.write(line.encode("utf-8"))
        # drain is fire-and-forget here since we're in a sync callback context

    async def _read_loop(self) -> None:
        """Continuously read JSON-RPC messages from the agent's stdout."""
        assert self._process is not None and self._process.stdout is not None
        try:
            while True:
                raw = await self._process.stdout.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    logger.debug("Non-JSON from ACP: %s", line[:200])
                    continue
                self._dispatch(msg)
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("ACP read loop error")
        finally:
            # Process exited — cancel all pending futures
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(AgentCrashError(
                        self._process.returncode if self._process else -1,
                    ))
            self._pending.clear()

    def _dispatch(self, msg: dict[str, Any]) -> None:
        """Route an incoming JSON-RPC message."""
        msg_id = msg.get("id")

        # Response to one of our requests
        if msg_id is not None and (msg.get("result") is not None or msg.get("error") is not None):
            fut = self._pending.pop(msg_id, None)
            if fut and not fut.done():
                if msg.get("error"):
                    fut.set_exception(SessionError(str(msg["error"])))
                else:
                    fut.set_result(msg.get("result", {}))
            return

        # Server-initiated request (needs a response from us)
        method = msg.get("method", "")

        if method == "session/request_permission" and msg_id is not None:
            self._respond(msg_id, {
                "outcome": {"outcome": "selected", "optionId": "allow-once"},
            })
            return

        # Notifications (no id, or server-initiated notifications)
        if method in self._notification_handlers:
            for queue in self._notification_handlers[method]:
                try:
                    queue.put_nowait(msg)
                except asyncio.QueueFull:
                    pass
            return

        # Cursor extension methods — log and ignore for now
        if method.startswith("cursor/"):
            logger.debug("Cursor extension: %s", method)
            return

        logger.debug("Unhandled ACP message: %s", method or msg)

    def _subscribe(self, method: str) -> asyncio.Queue[dict]:
        """Subscribe to notifications of a given method.  Returns a queue."""
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=1000)
        self._notification_handlers.setdefault(method, []).append(queue)
        return queue

    def _unsubscribe(self, method: str, queue: asyncio.Queue[dict]) -> None:
        handlers = self._notification_handlers.get(method, [])
        if queue in handlers:
            handlers.remove(queue)

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    async def get_or_create_session(self, model: str) -> str:
        """Return an existing session for this model, or create one."""
        if model in self._sessions:
            return self._sessions[model]

        cwd = self._config.workspace or os.getcwd()
        params: dict[str, Any] = {"cwd": cwd, "mcpServers": []}
        result = await self._send("session/new", params)
        session_id = result.get("sessionId", "")
        if not session_id:
            raise SessionError("session/new returned no sessionId", None)
        self._sessions[model] = session_id
        logger.info("Created ACP session %s for model %s", session_id[:12], model)
        return session_id

    def drop_session(self, model: str) -> None:
        """Forget a cached session (e.g. after an error)."""
        self._sessions.pop(model, None)

    # ------------------------------------------------------------------
    # Prompt execution
    # ------------------------------------------------------------------

    async def prompt(
        self,
        model: str,
        text: str,
        *,
        session_id: str | None = None,
        timeout_s: float | None = None,
    ) -> CompletionResult:
        """Send a prompt and collect the full response."""
        await self.ensure_started()

        sid = session_id or await self.get_or_create_session(model)
        timeout = timeout_s or self._config.request_timeout_s

        update_queue = self._subscribe("session/update")
        try:
            prompt_future = asyncio.ensure_future(
                self._send("session/prompt", {
                    "sessionId": sid,
                    "prompt": [{"type": "text", "text": text}],
                })
            )

            accumulated = ""
            try:
                result = await asyncio.wait_for(prompt_future, timeout=timeout)
            except TimeoutError:
                raise AgentTimeoutError(timeout, f"model={model}")

            # Drain any remaining updates
            while not update_queue.empty():
                update_msg = update_queue.get_nowait()
                chunk_text = self._extract_chunk_text(update_msg)
                if chunk_text:
                    accumulated += chunk_text

            stop_reason = result.get("stopReason", "")
            return CompletionResult(
                text=accumulated or result.get("result", ""),
                model=model,
                session_id=sid,
                stop_reason=stop_reason,
            )
        finally:
            self._unsubscribe("session/update", update_queue)

    async def prompt_stream(
        self,
        model: str,
        text: str,
        *,
        session_id: str | None = None,
        timeout_s: float | None = None,
    ) -> AsyncIterator[str]:
        """Send a prompt and yield text chunks as they arrive."""
        await self.ensure_started()

        sid = session_id or await self.get_or_create_session(model)
        timeout = timeout_s or self._config.request_timeout_s

        update_queue = self._subscribe("session/update")
        try:
            prompt_task = asyncio.ensure_future(
                self._send("session/prompt", {
                    "sessionId": sid,
                    "prompt": [{"type": "text", "text": text}],
                })
            )

            deadline = asyncio.get_event_loop().time() + timeout
            while not prompt_task.done():
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    prompt_task.cancel()
                    raise AgentTimeoutError(timeout, f"model={model}")
                try:
                    msg = await asyncio.wait_for(update_queue.get(), timeout=min(remaining, 1.0))
                    chunk = self._extract_chunk_text(msg)
                    if chunk:
                        yield chunk
                except TimeoutError:
                    continue

            # Drain remaining after prompt completes
            while not update_queue.empty():
                msg = update_queue.get_nowait()
                chunk = self._extract_chunk_text(msg)
                if chunk:
                    yield chunk

            # Check for errors
            result = prompt_task.result()
            if isinstance(result, dict) and result.get("error"):
                raise SessionError(str(result["error"]), sid)
        finally:
            self._unsubscribe("session/update", update_queue)

    @staticmethod
    def _extract_chunk_text(msg: dict[str, Any]) -> str:
        """Extract text from a session/update notification."""
        params = msg.get("params", {})
        update = params.get("update", {})
        if update.get("sessionUpdate") == "agent_message_chunk":
            content = update.get("content", {})
            return content.get("text", "")
        return ""

    # ------------------------------------------------------------------
    # Auto-restart
    # ------------------------------------------------------------------

    async def _ensure_alive_or_restart(self) -> None:
        """Restart the ACP process if it crashed, up to max_restarts."""
        if self._process is not None and self._process.returncode is None:
            return
        if self._restart_count >= self._config.acp_max_restarts:
            rc = self._process.returncode if self._process else -1
            raise AgentCrashError(rc, "Max ACP restarts exceeded")
        self._restart_count += 1
        logger.warning("ACP process died, restarting (attempt %d)", self._restart_count)
        await self._start()
