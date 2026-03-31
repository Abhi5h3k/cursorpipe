# cursorpipe

**Async Python client for the Cursor Agent CLI** — pipe prompts to frontier LLMs via [ACP (Agent Client Protocol)](https://cursor.com/docs/cli/acp) with persistent sessions, streaming, and per-call model selection.

## Why cursorpipe?

If you have a [Cursor](https://cursor.com) subscription, you already have access to frontier models (Claude, GPT, etc.) through the Cursor Agent CLI. **cursorpipe** lets you use those models programmatically from Python — no separate API keys needed.

### Highlights

- **Async-first** — built on `asyncio` for non-blocking LLM calls
- **Persistent ACP transport** — keeps a single agent process alive, ~50ms overhead per request instead of 1-3s for process-spawn approaches
- **Multi-turn sessions** — server-side conversation history, no need to resend messages each turn
- **Per-call model selection** — route different tasks to different models in a single client
- **Streaming** — `async for` over response chunks as they arrive
- **No prompt-length limit** — prompts sent over stdin, not CLI args (no Windows 8191-char ceiling)
- **Auto-fallback** — tries ACP first, falls back to subprocess if needed
- **Typed everything** — Pydantic models, custom exceptions, `py.typed` for IDE support


## Prerequisites

Before using cursorpipe, you need:

### 1. Cursor Agent CLI

Install the Cursor CLI agent ([docs](https://cursor.com/docs/cli/installation)):

```bash
# macOS / Linux / WSL
curl https://cursor.com/install -fsS | bash
```

```powershell
# Windows (PowerShell)
irm 'https://cursor.com/install?win32=true' | iex
```

```bash
# Verify installation
agent --version
```

### 2. Authentication

The Cursor agent supports two auth methods. Pick whichever fits your workflow:

**Option A — Interactive login (recommended for local dev)**

```bash
agent login
```

This opens a browser, authenticates with your Cursor account, and stores credentials locally. Once logged in, cursorpipe (and the CLI) will work without any extra env vars or keys.

**Option B — API key (recommended for scripts / CI)**

```bash
# In your .env or shell profile
export CURSOR_API_KEY=your-api-key
```

cursorpipe passes this to the agent as a CLI flag (`--api-key`) and as an env var, so it works reliably with both ACP and subprocess transports.

> **Where do I get an API key?** From your Cursor account settings at [cursor.com](https://cursor.com). If you only use Cursor locally, `agent login` is the simplest path — no keys needed.

### 3. Verify setup

```bash
# Check that the agent binary works and auth is valid
agent status

# List available models (confirms API access)
agent --list-models
```

## Installation

### From GitHub

```bash
pip install git+https://github.com/Abhi5h3k/cursorpipe.git

# Or with uv
uv pip install git+https://github.com/Abhi5h3k/cursorpipe.git
```

### From local clone

```bash
git clone https://github.com/Abhi5h3k/cursorpipe.git
cd cursorpipe
pip install .
```

### For development

```bash
git clone https://github.com/Abhi5h3k/cursorpipe.git
cd cursorpipe
pip install -e ".[dev]"
```

## Quick Start

### Simple completion

```python
from cursorpipe import CursorClient

client = CursorClient()

# Generate a completion
response = await client.generate(
    model="claude-4.5-sonnet-thinking",
    prompt="Explain Python's GIL in one paragraph.",
)
print(response)

await client.close()
```

### Per-call model selection

Use different models for different tasks — pass the model on every call:

```python
# Fast model for classification
intent = await client.generate(
    model="gpt-5.4-mini-medium",
    prompt="Classify this query: 'show top 10 users'",
    system="Reply with one of: SQL_QUERY, SCHEMA_QUESTION, GREETING",
)

# Smart model for complex generation
sql = await client.generate(
    model="claude-4.5-sonnet-thinking",
    prompt="Generate SQL for: top 10 users by revenue in 2026",
    system="You are a PostgreSQL expert.",
)
```

### Streaming

```python
async for chunk in client.stream(
    model="claude-4.5-sonnet-thinking",
    prompt="Write a detailed analysis of...",
):
    print(chunk, end="", flush=True)
```

### Chat with message history

```python
response = await client.chat(
    model="claude-4.5-sonnet-thinking",
    messages=[
        {"role": "system", "content": "You are a SQL expert."},
        {"role": "user", "content": "Show top 10 users"},
        {"role": "assistant", "content": "SELECT * FROM users ORDER BY revenue DESC LIMIT 10;"},
        {"role": "user", "content": "Add a date filter for 2026"},
    ],
)
```

### Multi-turn sessions (ACP-powered)

Sessions maintain conversation history **server-side** — no need to resend messages:

```python
async with client.session("claude-4.5-sonnet-thinking") as session:
    r1 = await session.prompt("Generate SQL for top 10 users by revenue")
    print(r1.text)

    # Cursor remembers the full conversation
    r2 = await session.prompt("Add a WHERE clause for date > 2026-01-01")
    print(r2.text)  # Has full context of r1

    print(f"Turns: {session.turn_count}")
```

### Module-level convenience

For quick scripts, use module-level functions (no explicit client needed):

```python
from cursorpipe import generate, chat, close

result = await generate(
    model="gpt-5.4-mini-medium",
    prompt="What is 2+2?",
)

await close()
```

## Configuration

All settings are loaded from environment variables (prefix `CURSORPIPE_`) or a `.env` file:


| Variable                           | Default | Description                                                       |
| ---------------------------------- | ------- | ----------------------------------------------------------------- |
| `CURSORPIPE_AGENT_BIN`             | `agent` | Path to the agent binary, or `agent` to search PATH               |
| `CURSORPIPE_STRATEGY`              | `auto`  | Transport: `acp` (persistent), `subprocess` (per-request), `auto` |
| `CURSORPIPE_DEFAULT_MODE`          | `ask`   | ACP/CLI mode: `ask` (pure LLM), `agent` (tools), `plan`           |
| `CURSORPIPE_REQUEST_TIMEOUT_S`     | `300`   | Per-request timeout in seconds                                    |
| `CURSORPIPE_ACP_STARTUP_TIMEOUT_S` | `30`    | Max seconds to wait for ACP process startup                       |
| `CURSORPIPE_ACP_MAX_RESTARTS`      | `3`     | Auto-restart attempts for crashed ACP process                     |
| `CURSORPIPE_WORKSPACE`             | `""`    | Working directory for the agent (empty = cwd)                     |
| `CURSORPIPE_API_KEY`               | `""`    | Cursor API key (also reads `CURSOR_API_KEY`). Passed as `--api-key` CLI flag. |


Or pass config programmatically:

```python
from cursorpipe import CursorClient, CursorPipeConfig, Strategy

config = CursorPipeConfig(
    agent_bin="/path/to/agent",
    strategy=Strategy.ACP,
    request_timeout_s=120,
)
client = CursorClient(config)
```

## Transport Strategies

### ACP (default, recommended)

Spawns a persistent `agent acp` process and communicates via stdin/stdout JSON-RPC. Sessions are pooled per model.

- Fastest: ~50ms overhead per request (no process spawn)
- Supports multi-turn sessions with server-side history
- No prompt length limit (sent via stdin)
- Auto-restarts if the process crashes

### Subprocess (fallback)

Spawns a fresh `agent --print` process per request. Simpler but slower.

- ~1-3s overhead per request (process startup)
- No session support (stateless)
- Prompts written to temp files (no Windows cmdline limit)
- Good for one-off scripts or when ACP has issues

### Auto (default)

Tries ACP first; falls back to subprocess if ACP fails. Best of both worlds.

## Testing

Run the test suite to validate your setup:

```bash
# Preflight checks first — tells you what's missing
pytest tests/test_preflight.py -v

# Unit tests (no agent needed, fast)
pytest tests/test_unit.py -v

# Integration tests (needs agent + auth, slow)
pytest tests/test_integration.py -v -m integration

# Everything
pytest -v
```

### Test markers


| Marker        | What it tests                             | Needs agent? |
| ------------- | ----------------------------------------- | ------------ |
| `preflight`   | Prerequisites: binary, auth, connectivity | Yes          |
| `unit`        | Config, models, NDJSON parser, errors     | No           |
| `integration` | End-to-end: generate, stream, sessions    | Yes + auth   |


## API Reference

### `CursorClient`


| Method                                                                   | Description                               |
| ------------------------------------------------------------------------ | ----------------------------------------- |
| `generate(model, prompt, *, system, temperature, max_tokens, timeout_s)` | Single completion, returns `str`          |
| `chat(model, messages, *, temperature, max_tokens, timeout_s)`           | Chat with message history, returns `str`  |
| `stream(model, prompt, *, system, timeout_s)`                            | Streaming completion, yields `str` chunks |
| `session(model)`                                                         | Create a `CursorSession` context manager  |
| `list_models()`                                                          | Discover available models                 |
| `close()`                                                                | Shut down transports                      |


### `CursorSession`


| Method                              | Description                                                   |
| ----------------------------------- | ------------------------------------------------------------- |
| `prompt(text, *, timeout_s)`        | Send a prompt (history preserved), returns `CompletionResult` |
| `stream_prompt(text, *, timeout_s)` | Streaming prompt, yields `str` chunks                         |
| `model`                             | The model for this session                                    |
| `session_id`                        | The ACP session ID                                            |
| `turn_count`                        | Number of prompts sent                                        |


### Exceptions

All exceptions inherit from `CursorPipeError`:


| Exception             | When                              |
| --------------------- | --------------------------------- |
| `AgentNotFoundError`  | Agent binary not found            |
| `AuthenticationError` | Auth failed or missing            |
| `AgentTimeoutError`   | Request exceeded timeout          |
| `RateLimitError`      | Cursor returned 429               |
| `AgentCrashError`     | Agent process exited unexpectedly |
| `SessionError`        | ACP session error                 |


## Drop-in Replacement

If your project already has a module with `generate()` / `chat()` / `close()` functions, cursorpipe ships a compatibility layer that matches that pattern:

```python
# Point your existing import at cursorpipe
from cursorpipe import _compat as llm_client

result = await llm_client.generate(model="...", prompt="...", system="...")
await llm_client.close()
```

No other code changes needed — the signatures are the same.

## Architecture

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

## License

MIT