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

Spawns a persistent `agent acp` process and communicates via stdin/stdout using JSON-RPC 2.0. Sessions are pooled per model.

**Advantages:**

- ~50ms overhead per request (no process spawn)
- Multi-turn sessions with server-side history
- No prompt length limit (sent via stdin)
- Auto-restarts if the process crashes

**How it works:**

1. `CursorClient` spawns `agent --api-key <key> --trust acp`
2. Sends `initialize` JSON-RPC to negotiate capabilities
3. If no API key is present, sends `authenticate` with the method from the server
4. Creates sessions via `session/new`
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

## Authentication flow

cursorpipe supports two auth paths:

**API key (non-interactive):**
The key is passed as `--api-key <key>` when spawning the agent. The ACP handshake skips the `authenticate` call entirely — the agent is pre-authenticated.

**Login session (interactive):**
Relies on credentials stored by `agent login`. During ACP initialization, the `authenticate` JSON-RPC call confirms the session. If no valid session exists, the agent may open a browser for login.

## File resolution (Windows)

On Windows, cursorpipe searches for the agent binary in this order:

1. `CURSORPIPE_AGENT_BIN` config / env var
2. `CURSOR_AGENT_NODE` + `CURSOR_AGENT_SCRIPT` env vars (direct node.exe + index.js)
3. `agent` / `agent.exe` on PATH
4. `%LOCALAPPDATA%\cursor-agent\versions\<latest>\` (default install location)
