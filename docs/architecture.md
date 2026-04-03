# Architecture

## Overview

cursorpipe sits between your Python code and the Cursor cloud API. It manages the agent process lifecycle and provides a clean async interface.

```
Your Python code
    |
    v
CursorClient (cursorpipe)
    |
    +--> AcpTransport ----stdin/stdout----> agent acp (persistent process)
    |       |                                   |
    |       +--> SessionDispenser               |
    |       |    (pre-created sessions)         |
    |       +--> Notification Router            |
    |            (routes by sessionId)          |
    |                                           |
    +--> SubprocessTransport ---spawn---->  agent --print (per request)
                                                |
                                                v
                                          Cursor API (cloud)
                                                |
                                                v
                                        Claude / GPT / etc.
```

## Transport strategies

### ACP (recommended)

Spawns a persistent `agent acp` process and communicates via stdin/stdout using JSON-RPC 2.0.

**Advantages:**

- ~50ms overhead per request (no process spawn)
- Multi-turn sessions with server-side history
- No prompt length limit (sent via stdin)
- Auto-restarts if the process crashes

**How it works:**

1. `CursorClient` spawns `agent --api-key <key> --trust acp`
2. Sends `initialize` JSON-RPC to negotiate capabilities
3. If no API key is present, sends `authenticate` with the method from the server
4. Creates sessions via `session/new` (pre-created by the session dispenser)
5. Sends prompts via `session/prompt`, receives streaming updates via `session/update` notifications
6. Handles `session/request_permission` for tool approvals

### Subprocess (fallback)

Spawns a fresh `agent --print` process per request. Simpler but slower.

**Advantages:**

- No persistent state to manage
- Works in restricted environments where long-running processes are problematic

**Trade-offs:**

- ~1-3s overhead per request (process startup)
- No session support (stateless)
- Prompts written to temp files

### Auto (default)

Tries ACP first. If ACP fails (crash, timeout, etc.), falls back to subprocess transparently. Best of both worlds.

## Session dispenser

Every ACP session maintains conversation history server-side. To guarantee isolation between requests and users, cursorpipe uses a **session dispenser** instead of a traditional session pool:

```
warmup(pool_size=5)
    |
    v
SessionDispenser
    |
    +-- [sess-1] [sess-2] [sess-3] [sess-4] [sess-5]  (virgin, no history)
    |
generate() --> acquire() --> pops sess-1 --> uses it --> DISCARDED (not returned)
    |
    +-- Background refill creates sess-6 to replace it
    |
create_session() --> acquire() --> pops sess-2 --> held by user --> discard()
```

**Key design decisions:**

- **No release method** — used sessions are discarded, never returned to the queue. This structurally guarantees that no conversation history leaks between requests or users.
- **Background refill** — after each acquire, a background task creates new sessions to keep the queue at its target size.
- **Fallback creation** — if the queue is empty, a session is created on-demand (slower, with a logged warning).

## Notification routing

ACP notifications (`session/update`) carry a `sessionId` field. cursorpipe routes each notification to the queue subscribed for that specific session, preventing response chunks from one request leaking into another:

```
Agent stdout --> _read_loop() --> _dispatch()
                                      |
                    +-----------------+-----------------+
                    |                                   |
              (session/update,           (session/update,
               sessionId=sess-A)          sessionId=sess-B)
                    |                                   |
                    v                                   v
              Queue for request A              Queue for request B
```

This is critical for concurrent requests — without session-scoped routing, chunks from different model responses would interleave.

## Authentication flow

cursorpipe supports two auth paths:

**API key (non-interactive):**
The key is passed as `--api-key <key>` when spawning the agent. The ACP handshake skips the `authenticate` call entirely — the agent is pre-authenticated.

**Login session (interactive):**
Relies on credentials stored by `agent login`. During ACP initialization, the `authenticate` JSON-RPC call confirms the session. If no valid session exists, the agent may open a browser for login.

## Performance optimizations

- **orjson fast-path** — optional Rust-backed JSON parser (~4.6x faster). Install with `pip install cursorpipe[fast]`.
- **Streaming overhaul** — uses `asyncio.wait()` to race chunk arrival against prompt completion, eliminating the 1s poll delay from the previous `wait_for` approach.
- **256KB StreamReader buffer** — prevents backpressure stalls during burst chunk delivery.
- **Profiling mode** — set `CURSORPIPE_ENABLE_PROFILING=true` to log time-to-first-chunk, per-chunk inter-arrival, and total streaming duration.

## File resolution (Windows)

On Windows, cursorpipe searches for the agent binary in this order:

1. `CURSORPIPE_AGENT_BIN` config / env var
2. `CURSOR_AGENT_NODE` + `CURSOR_AGENT_SCRIPT` env vars (direct node.exe + index.js)
3. `agent` / `agent.exe` on PATH
4. `%LOCALAPPDATA%\cursor-agent\versions\<latest>\` (default install location)
