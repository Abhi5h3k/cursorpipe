# v1 vs v2 — Which should I use?

cursorpipe has two versions with different backends:

- **v1** — uses the **Cursor Agent CLI** (`agent --print`, ACP). Works with your existing Cursor IDE login or an API key.
- **v2** — uses the **official `cursor-sdk`**. Requires a `CURSOR_API_KEY`. Smaller model list, but richer capabilities.

---

## Feature comparison

The table below reflects real-world observed behaviour, not just design intent.

| Capability | v1 (CLI-based) | v2 (SDK-based) |
|---|---|---|
| **Available models** | Large list — every model your Cursor CLI can access | Smaller curated list — only models exposed by the Cursor SDK/API |
| **Web / URL access** | Not possible — CLI modes `ask` and `plan` have no browser tool | Works — the SDK backend has tool access; models like Claude and GPT can browse live URLs |
| **Mode control** | `ask` (default, pure LLM) or `plan`. `agent` is **not** a valid mode and crashes the server | No mode concept — the SDK manages tool access internally per model |
| **Model selection per request** | Via `--model` flag through subprocess transport; ACP always auto-selects | Per-request via SDK model parameter; every call can use a different model |
| **Multi-turn sessions** | ACP persistent sessions (server-side history, session dispenser) | Stateful sessions via `X-Cursor-Session-ID` header |
| **Thinking / reasoning** | Not supported | `CURSORPIPE_THINKING_LEVEL=low\|high` exposes chain-of-thought |
| **Authentication** | `agent login` (Cursor IDE session) **or** `CURSOR_API_KEY` | `CURSOR_API_KEY` required — no login-session fallback |
| **Transport overhead** | ~50ms per request (ACP warm session) or ~1–3s (subprocess spawn) | SDK HTTP call — no local process overhead |
| **CORS support** | No | Yes — configurable via `CURSORPIPE_CORS_ORIGINS` |
| **Stateless requests** | Yes (subprocess) or session-pooled (ACP) | Always stateless unless `X-Cursor-Session-ID` is passed |
| **Install requirement** | Cursor Agent CLI must be installed locally | No CLI needed — `pip install cursorpipe-v2` only |

---

## Known limitations discovered in testing

### v1 — CLI mode restrictions

The Cursor Agent CLI only accepts `--mode ask` and `--mode plan`. The `agent` value is **rejected by the CLI**:

```
error: option '--mode <mode>' argument 'agent' is invalid. Allowed choices are plan, ask.
```

This means v1 cannot browse URLs, fetch live data, or use any agentic tools regardless of the model you choose.

### v1 — ACP does not pass `--model`

The ACP transport starts one persistent process without `--model`. It always uses Cursor's auto-selected model. Only the subprocess transport honours a specific model name (via `--model <name>`). With the default `auto` strategy, cursorpipe routes requests with a specific model to subprocess automatically — see [Architecture](architecture.md) for details.

### v2 — Smaller model list

`GET /v1/models` in v2 returns only the models the Cursor SDK exposes via its API. Models available in the CLI but not in the SDK API do not appear. If you need a specific model that only shows up in v1's model list, use v1 with the subprocess strategy.

---

## Decision guide

**Use v1 if:**

- You don't have a `CURSOR_API_KEY` and want to use your existing Cursor IDE login session (`agent login`)
- You need access to the widest possible model selection
- You're comfortable without web access or tool use
- You want the lowest-footprint install (just the CLI, no SDK)

**Use v2 if:**

- You need models to browse live URLs or evaluate web content
- You want thinking/reasoning support (`CURSORPIPE_THINKING_LEVEL`)
- You need CORS headers for a browser-based client
- You want a fully API-key-driven, stateless setup
- You don't want to depend on the Cursor Agent CLI being installed

---

## Running both simultaneously

v1 and v2 use the same default port (`8080`). To run both at once, start one on a different port:

=== "bash / macOS / Linux / WSL"

    ```bash
    # Terminal 1: v1 on port 8080 (default)
    cursorpipe-server

    # Terminal 2: v2 on port 8081
    CURSORPIPE_PORT=8081 cursorpipe-server --config v2
    ```

=== "PowerShell (Windows)"

    ```powershell
    # Terminal 1: v1 on port 8080 (default)
    cursorpipe-server

    # Terminal 2: v2 on port 8081
    $env:CURSORPIPE_PORT = "8081"
    cd v2; cursorpipe-server
    ```

See [Getting Started](getting-started.md) for full setup instructions for each version.
