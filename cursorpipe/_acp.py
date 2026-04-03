"""ACP (Agent Client Protocol) transport — persistent agent process.

Spawns ``agent acp`` once and communicates via stdin/stdout JSON-RPC.
Sessions are dispensed (one per request) for isolation.  The process
auto-restarts on crash up to ``acp_max_restarts`` times.

Protocol reference: https://cursor.com/docs/cli/acp
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import AsyncIterator
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from cursorpipe._config import CursorPipeConfig
from cursorpipe._json import dumps as _dumps
from cursorpipe._json import loads as _loads
from cursorpipe._errors import (
    AgentCrashError,
    AgentTimeoutError,
    AuthenticationError,
    SessionError,
)
from cursorpipe._models import CompletionResult
from cursorpipe._pool import SessionDispenser
from cursorpipe._resolve import resolve_agent_command

logger = logging.getLogger(__name__)

try:
    _PKG_VERSION = version("cursorpipe")
except PackageNotFoundError:
    _PKG_VERSION = "0.0.0"

_CLIENT_INFO = {"name": "cursorpipe", "version": _PKG_VERSION}


class AcpTransport:
    """Manages a persistent ``agent acp`` subprocess and JSON-RPC communication."""

    def __init__(self, config: CursorPipeConfig) -> None:
        self._config = config
        self._process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._next_id: int = 1
        self._pending: dict[int, asyncio.Future[dict]] = {}
        self._notification_handlers: dict[
            tuple[str, str], list[asyncio.Queue[dict]]
        ] = {}
        self._initialized: bool = False
        self._restart_count: int = 0
        self._lock = asyncio.Lock()
        self.dispenser = SessionDispenser(self)

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
        args = [*cmd, *auth_args, "--trust", "acp"]

        env = {**os.environ, **self._config.resolve_auth_env()}

        logger.info("Starting ACP process: %s", " ".join(args))
        self._process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=256 * 1024,
            env=env,
            cwd=self._config.workspace or None,
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        self._initialized = False
        self.dispenser.close()
        self.dispenser = SessionDispenser(self)

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

        has_api_key = bool(
            self._config.api_key or os.getenv("CURSOR_API_KEY", "")
        )

        if has_api_key:
            # Pre-authenticated via --api-key CLI flag passed to `agent acp`.
            # Skip the authenticate handshake to avoid triggering browser login.
            logger.info("ACP pre-authenticated via API key; skipping authenticate call")
        else:
            auth_methods: list[dict] = result.get("authMethods", [])
            if not auth_methods:
                logger.info("ACP no authMethods advertised; assuming pre-authenticated via login")
            else:
                method_id = auth_methods[0].get("id", "cursor_login")
                logger.info("ACP authenticating with method: %s", method_id)
                auth_result = await self._send("authenticate", {"methodId": method_id})
                if isinstance(auth_result, dict) and auth_result.get("error"):
                    raise AuthenticationError(str(auth_result["error"]))
                logger.info("ACP authenticated successfully via %s", method_id)

        self._initialized = True

    async def close(self) -> None:
        """Shut down the ACP process gracefully."""
        self.dispenser.close()
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

        line = _dumps(payload) + "\n"
        self._process.stdin.write(line.encode("utf-8"))
        await self._process.stdin.drain()

        future: asyncio.Future[dict] = asyncio.get_running_loop().create_future()
        self._pending[msg_id] = future
        return await future

    def _respond(self, msg_id: int, result: dict) -> None:
        """Send a JSON-RPC response (for server-initiated requests like permission)."""
        if self._process is None or self._process.stdin is None:
            return
        payload = {"jsonrpc": "2.0", "id": msg_id, "result": result}
        line = _dumps(payload) + "\n"
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
                    msg = _loads(line)
                except (ValueError, TypeError):
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

        # Notifications — route by (method, sessionId) for isolation
        session_id = msg.get("params", {}).get("sessionId", "")
        key = (method, session_id)
        if key in self._notification_handlers:
            for queue in self._notification_handlers[key]:
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

    def _subscribe(self, method: str, session_id: str) -> asyncio.Queue[dict]:
        """Subscribe to notifications for a specific (method, sessionId) pair."""
        key = (method, session_id)
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=1000)
        self._notification_handlers.setdefault(key, []).append(queue)
        return queue

    def _unsubscribe(self, method: str, session_id: str, queue: asyncio.Queue[dict]) -> None:
        key = (method, session_id)
        handlers = self._notification_handlers.get(key, [])
        if queue in handlers:
            handlers.remove(queue)
            if not handlers:
                self._notification_handlers.pop(key, None)

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    async def create_session_raw(self) -> str:
        """Create a new ACP session and return its ID.

        This is the low-level primitive used by :class:`SessionDispenser`.
        Each call sends a ``session/new`` RPC to the agent.
        """
        cwd = self._config.workspace or os.getcwd()
        params: dict[str, Any] = {"cwd": cwd, "mcpServers": []}
        result = await self._send("session/new", params)
        session_id = result.get("sessionId", "")
        if not session_id:
            raise SessionError("session/new returned no sessionId", None)
        logger.info("Created ACP session %s", session_id[:12])
        return session_id

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

        sid = session_id or await self.dispenser.acquire()
        timeout = timeout_s or self._config.request_timeout_s

        update_queue = self._subscribe("session/update", sid)
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
            self._unsubscribe("session/update", sid, update_queue)

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

        profiling = self._config.enable_profiling
        t_start = time.monotonic() if profiling else 0.0

        sid = session_id or await self.dispenser.acquire()

        if profiling:
            logger.info(
                "[profile] session acquire: %.1fms",
                (time.monotonic() - t_start) * 1000,
            )

        timeout = timeout_s or self._config.request_timeout_s

        update_queue = self._subscribe("session/update", sid)
        try:
            done_event = asyncio.Event()

            prompt_task = asyncio.ensure_future(
                self._send("session/prompt", {
                    "sessionId": sid,
                    "prompt": [{"type": "text", "text": text}],
                })
            )
            prompt_task.add_done_callback(lambda _: done_event.set())

            loop = asyncio.get_running_loop()
            deadline = loop.time() + timeout

            chunk_count = 0
            t_first_chunk = 0.0
            t_last_chunk = t_start
            chunk_gaps: list[float] = [] if profiling else []

            while not done_event.is_set():
                remaining = deadline - loop.time()
                if remaining <= 0:
                    prompt_task.cancel()
                    raise AgentTimeoutError(timeout, f"model={model}")

                get_task = asyncio.ensure_future(update_queue.get())
                done_waiter = asyncio.ensure_future(done_event.wait())

                finished, pending = await asyncio.wait(
                    {get_task, done_waiter},
                    timeout=remaining,
                    return_when=asyncio.FIRST_COMPLETED,
                )

                for p in pending:
                    p.cancel()

                if get_task in finished:
                    chunk = self._extract_chunk_text(get_task.result())
                    if chunk:
                        if profiling:
                            now = time.monotonic()
                            if chunk_count == 0:
                                t_first_chunk = now
                            else:
                                chunk_gaps.append(now - t_last_chunk)
                            t_last_chunk = now
                        chunk_count += 1
                        yield chunk

            # Drain remaining after prompt completes
            while not update_queue.empty():
                msg = update_queue.get_nowait()
                chunk = self._extract_chunk_text(msg)
                if chunk:
                    chunk_count += 1
                    yield chunk

            # Check for errors
            result = prompt_task.result()
            if isinstance(result, dict) and result.get("error"):
                raise SessionError(str(result["error"]), sid)

            if profiling and chunk_count > 0:
                total_ms = (time.monotonic() - t_start) * 1000
                ttfc_ms = (t_first_chunk - t_start) * 1000 if t_first_chunk else 0
                avg_gap = (sum(chunk_gaps) / len(chunk_gaps) * 1000) if chunk_gaps else 0
                min_gap = min(chunk_gaps) * 1000 if chunk_gaps else 0
                max_gap = max(chunk_gaps) * 1000 if chunk_gaps else 0
                logger.info(
                    "[profile] stream done: %d chunks, %.0fms total, "
                    "TTFC=%.0fms, gap min/avg/max=%.1f/%.1f/%.1fms",
                    chunk_count, total_ms, ttfc_ms, min_gap, avg_gap, max_gap,
                )
        finally:
            self._unsubscribe("session/update", sid, update_queue)

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
