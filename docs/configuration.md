# Configuration

All cursorpipe settings are loaded from **environment variables** or a **`.env` file** placed in the directory where you run the command.

---

## Setting variables

=== "bash / macOS / Linux / WSL"

    ```bash
    export CURSORPIPE_PORT=9090
    cursorpipe-server
    ```

=== "PowerShell (Windows)"

    ```powershell
    $env:CURSORPIPE_PORT = "9090"
    cursorpipe-server
    ```

=== "CMD (Windows)"

    ```cmd
    set CURSORPIPE_PORT=9090
    cursorpipe-server
    ```

=== ".env file (any platform)"

    ```bash
    CURSORPIPE_PORT=9090
    CURSOR_API_KEY=crsr_your_key_here
    ```

    Place `.env` in the directory where you run `cursorpipe-server`.

---

## Authentication

| Variable | Default | Description |
|----------|---------|-------------|
| `CURSOR_API_KEY` or `CURSORPIPE_API_KEY` | `""` | Cursor API key. Both names are accepted in env vars and `.env` files. See [How to create a Cursor API key](cursor-api-key.md). |
| `CURSOR_AUTH_TOKEN` or `CURSORPIPE_AUTH_TOKEN` | `""` | Cursor auth token (advanced). Passed via env var to the agent subprocess. |

---

## Server settings

Applies to `cursorpipe-server` and Docker only.

| Variable | Default | Description |
|----------|---------|-------------|
| `CURSORPIPE_HOST` | `0.0.0.0` | Bind address for the HTTP server |
| `CURSORPIPE_PORT` | `8080` | Bind port for the HTTP server |
| `CURSORPIPE_POOL_SIZE` | `5` | ACP sessions to pre-create at startup |
| `CURSORPIPE_BEARER_TOKEN` | `""` | When set, all requests (except `/health`) must include `Authorization: Bearer <token>` |

---

## Core library settings

Applies to both the server and direct Python library usage.

| Variable | Default | Description |
|----------|---------|-------------|
| `CURSORPIPE_STRATEGY` | `auto` | Transport: `acp` (persistent process, model auto-selected by Cursor), `subprocess` (per-request spawn, `--model` passed correctly), `auto` (smart routing — see note below) |
| `CURSORPIPE_DEFAULT_MODE` | `ask` | CLI mode: `ask` (pure LLM, no web/file/tool access), `plan` (planning/coding mode). **Do not use `agent`** — it is not a valid CLI mode and will crash the server. |
| `CURSORPIPE_REQUEST_TIMEOUT_S` | `300` | Per-request timeout in seconds |
| `CURSORPIPE_ACP_STARTUP_TIMEOUT_S` | `30` | Max seconds to wait for the ACP process to initialise |
| `CURSORPIPE_ACP_MAX_RESTARTS` | `3` | How many times to auto-restart a crashed ACP process before giving up |
| `CURSORPIPE_WORKSPACE` | `""` | Working directory passed to the agent. Empty = current directory at call time |
| `CURSORPIPE_ENABLE_PROFILING` | `false` | Log timing diagnostics: TTFC, per-chunk inter-arrival, session acquire latency |

!!! warning "CURSORPIPE_DEFAULT_MODE valid values"
    Only `ask` and `plan` are accepted by the Cursor Agent CLI. Setting `CURSORPIPE_DEFAULT_MODE=agent` causes the agent process to exit with code 1 immediately, returning a `500 agent_crash` error on every request.

    - **`ask`** (default) — pure LLM, no tools. Cannot browse URLs, read files, or run commands. Safe for a shared server.
    - **`plan`** — planning/coding mode. Behaviour varies by CLI version.

    If you need web/URL access or tool use, use **v2** instead (SDK-based; no mode restriction).

!!! note "CURSORPIPE_STRATEGY=auto model routing"
    In `auto` mode, the transport is chosen per-request based on the `model` value you pass:

    | model value | transport | effect |
    |-------------|-----------|--------|
    | `"auto"` or empty | ACP | ~50ms overhead; Cursor picks the best available model |
    | specific name (e.g. `"claude-4.5-sonnet-thinking"`) | subprocess | `--model` is passed to the CLI; exact model is honoured |

    **Why?** ACP is started once without `--model` and cannot switch models mid-session. Subprocess spawns `agent --print --model <name>` fresh per call, so it reliably uses the requested model.

    If ACP is forced (`CURSORPIPE_STRATEGY=acp`), the `model` field in requests is ignored — Cursor always auto-selects.

---

## Agent binary settings

Needed only if the Cursor agent CLI is not on your `PATH`, or on Windows where the agent is a Node.js script.

| Variable | Default | Description |
|----------|---------|-------------|
| `CURSORPIPE_AGENT_BIN` | `agent` | Path to the Cursor agent binary, or just `agent` to search `PATH` |
| `CURSORPIPE_AGENT_NODE` / `CURSOR_AGENT_NODE` | `""` | Windows: path to `node.exe` bundled with cursor-agent |
| `CURSORPIPE_AGENT_SCRIPT` / `CURSOR_AGENT_SCRIPT` | `""` | Windows: path to `index.js` bundled with cursor-agent |

---

## Example `.env` file

```bash
# Authentication
CURSOR_API_KEY=crsr_your_key_here

# Server
CURSORPIPE_PORT=9090
CURSORPIPE_POOL_SIZE=3
CURSORPIPE_BEARER_TOKEN=my-secret-token

# Behaviour
CURSORPIPE_STRATEGY=acp
CURSORPIPE_DEFAULT_MODE=ask
CURSORPIPE_REQUEST_TIMEOUT_S=120
```
