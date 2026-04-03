# cursorpipe

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Cursor CLI](https://img.shields.io/badge/cursor%20cli-v2026.03.25-purple.svg)](https://cursor.com/docs/cli/installation)

**Async Python client for the Cursor Agent CLI** — pipe prompts to frontier LLMs via [ACP (Agent Client Protocol)](https://cursor.com/docs/cli/acp) with persistent sessions, streaming, and per-call model selection.

> **[Read the full documentation](https://abhi5h3k.github.io/cursorpipe/)**

---

## Why cursorpipe?

If you have a [Cursor](https://cursor.com) subscription, you already have access to frontier models (Claude, GPT, etc.) through the Cursor Agent CLI. **cursorpipe** lets you use those models programmatically from Python — no separate API keys needed.

### Highlights

- **Async-first** — built on `asyncio` for non-blocking LLM calls
- **Persistent ACP transport** — keeps a single agent process alive, ~50ms overhead per request instead of 1-3s for process-spawn approaches
- **Multi-turn sessions** — server-side conversation history, no need to resend messages each turn
- **Session isolation** — every request gets a fresh session; no history leaks between users or calls
- **Warmup support** — pre-start the process and pre-create sessions to eliminate cold-start latency
- **Framework-ready** — explicit session lifecycle (`create_session` / `discard`) for Chainlit, FastAPI, etc.
- **Per-call model selection** — route different tasks to different models in a single client
- **Streaming** — `async for` over response chunks as they arrive
- **No prompt-length limit** — prompts sent over stdin, not CLI args (no Windows 8191-char ceiling)
- **Auto-fallback** — tries ACP first, falls back to subprocess if needed
- **Typed everything** — Pydantic models, custom exceptions, `py.typed` for IDE support
- **Fast JSON** — optional `orjson` support for ~4.6x faster JSON parsing

---

## Quick Start

### 1. Install the Cursor Agent CLI

```bash
# macOS / Linux / WSL
curl https://cursor.com/install -fsS | bash
```

```powershell
# Windows (PowerShell)
irm 'https://cursor.com/install?win32=true' | iex
```

See the [official installation docs](https://cursor.com/docs/cli/installation) for more options.

### 2. Authenticate

```bash
agent login
```

Or set an API key (get one at [cursor.com/dashboard/cloud-agents](https://cursor.com/dashboard/cloud-agents)):

```bash
export CURSORPIPE_API_KEY=crsr_your_key_here
```

> **`.env` files** — use `CURSORPIPE_API_KEY` (pydantic-settings prefix).
> **OS environment variables** — both `CURSORPIPE_API_KEY` and `CURSOR_API_KEY` work.

### 3. Install cursorpipe

```bash
pip install git+https://github.com/Abhi5h3k/cursorpipe.git

# With faster JSON parsing (recommended)
pip install "cursorpipe[fast] @ git+https://github.com/Abhi5h3k/cursorpipe.git"

# Or with uv
uv pip install git+https://github.com/Abhi5h3k/cursorpipe.git
```

### 4. Run your first prompt

```python
import asyncio
from cursorpipe import CursorClient

async def main():
    client = CursorClient()
    await client.warmup(pool_size=3)  # optional: eliminate cold-start

    response = await client.generate(
        model="claude-4.5-sonnet-thinking",
        prompt="Explain what an API is in two sentences.",
    )
    print(response)

    await client.close()

asyncio.run(main())
```

---

## Examples

The [`examples/`](examples/) folder has runnable scripts for every feature:

| Example | What it shows |
|---------|---------------|
| [`basic.py`](examples/basic.py) | Simplest prompt-response flow |
| [`warmup.py`](examples/warmup.py) | Pre-warming for zero cold-start latency |
| [`streaming.py`](examples/streaming.py) | Stream chunks to terminal in real time |
| [`multi_turn.py`](examples/multi_turn.py) | Session with memory across turns |
| [`model_switching.py`](examples/model_switching.py) | Per-call model selection across tasks |
| [`session_streaming.py`](examples/session_streaming.py) | Stream responses within a multi-turn session |
| [`chainlit_pattern.py`](examples/chainlit_pattern.py) | Framework integration (Chainlit / FastAPI) |
| [`api_key_auth.py`](examples/api_key_auth.py) | API key auth for scripts and CI |

```bash
# Run any example
python examples/basic.py
python examples/warmup.py
```

---

## Features

### Warmup (recommended for production)

```python
client = CursorClient()
await client.warmup(pool_size=5)
# First request is now as fast as subsequent ones
```

### Per-call model selection

Use different models for different tasks:

```python
import asyncio
from cursorpipe import CursorClient

async def main():
    client = CursorClient()

    intent = await client.generate(
        model="gpt-5.4-mini-medium",
        prompt="Classify this query: 'show top 10 users'",
        system="Reply with one of: SQL_QUERY, SCHEMA_QUESTION, GREETING",
    )

    sql = await client.generate(
        model="claude-4.5-sonnet-thinking",
        prompt="Generate SQL for: top 10 users by revenue in 2026",
        system="You are a PostgreSQL expert.",
    )

    await client.close()

asyncio.run(main())
```

### Streaming

```python
async for chunk in client.stream(
    model="claude-4.5-sonnet-thinking",
    prompt="Write a detailed analysis of...",
):
    print(chunk, end="", flush=True)
```

### Multi-turn sessions (ACP)

Sessions maintain conversation history **server-side**:

```python
async with client.session("claude-4.5-sonnet-thinking") as session:
    r1 = await session.prompt("Generate SQL for top 10 users by revenue")
    print(r1.text)

    r2 = await session.prompt("Add a WHERE clause for date > 2026-01-01")
    print(r2.text)  # Has full context of r1
```

### Framework integration (Chainlit / FastAPI)

```python
# on_chat_start
session = await client.create_session("claude-4.5-sonnet-thinking")

# on_message (server has history — only send new message)
response = await session.prompt(message.content)

# on_chat_end
session.discard()
```

### Module-level convenience

For quick scripts without explicit client setup:

```python
import asyncio
from cursorpipe import generate, warmup, close

async def main():
    await warmup(pool_size=3)
    result = await generate(
        model="gpt-5.4-mini-medium",
        prompt="What is 2+2?",
    )
    print(result)
    await close()

asyncio.run(main())
```

---

## Configuration

All settings load from environment variables (prefix `CURSORPIPE_`) or a `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `CURSORPIPE_AGENT_BIN` | `agent` | Path to the agent binary, or `agent` to search PATH |
| `CURSORPIPE_STRATEGY` | `auto` | Transport: `acp` (persistent), `subprocess` (per-request), `auto` |
| `CURSORPIPE_DEFAULT_MODE` | `ask` | ACP/CLI mode: `ask` (pure LLM), `agent` (tools), `plan` |
| `CURSORPIPE_REQUEST_TIMEOUT_S` | `300` | Per-request timeout in seconds |
| `CURSORPIPE_ACP_STARTUP_TIMEOUT_S` | `30` | Max seconds to wait for ACP process startup |
| `CURSORPIPE_ACP_MAX_RESTARTS` | `3` | Auto-restart attempts for crashed ACP process |
| `CURSORPIPE_WORKSPACE` | `""` | Working directory for the agent (empty = cwd) |
| `CURSORPIPE_API_KEY` | `""` | Cursor API key (also reads `CURSOR_API_KEY`). Passed as `--api-key` CLI flag. |
| `CURSORPIPE_ENABLE_PROFILING` | `false` | Log timing diagnostics (TTFC, per-chunk gaps) |

Or pass config programmatically:

```python
from cursorpipe import CursorClient, CursorPipeConfig, Strategy

config = CursorPipeConfig(
    api_key="crsr_...",
    strategy=Strategy.ACP,
    request_timeout_s=120,
)
client = CursorClient(config)
```

---

## Transport Strategies

### ACP (default, recommended)

Spawns a persistent `agent acp` process and communicates via stdin/stdout JSON-RPC. Sessions are dispensed (one per request) for isolation.

- Fastest: ~50ms overhead per request (no process spawn)
- Supports multi-turn sessions with server-side history
- Session isolation: each request/user gets a fresh session
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

---

## API Reference

### CursorClient

| Method | Description |
|--------|-------------|
| `warmup(pool_size=5)` | Pre-start ACP process and pre-create sessions |
| `generate(model, prompt, *, system, temperature, max_tokens, timeout_s)` | Single completion, returns `str` |
| `chat(model, messages, *, temperature, max_tokens, timeout_s)` | Chat with message history, returns `str` |
| `stream(model, prompt, *, system, timeout_s)` | Streaming completion, yields `str` chunks |
| `session(model)` | Create a `CursorSession` context manager |
| `create_session(model)` | Create a `CursorSession` with explicit lifecycle |
| `list_models()` | Discover available models |
| `close()` | Shut down transports |

### CursorSession

| Method | Description |
|--------|-------------|
| `prompt(text, *, timeout_s)` | Send a prompt (history preserved), returns `CompletionResult` |
| `stream_prompt(text, *, timeout_s)` | Streaming prompt, yields `str` chunks |
| `discard()` | Release this session |
| `model` | The model for this session |
| `session_id` | The ACP session ID |
| `turn_count` | Number of prompts sent |

### Exceptions

All exceptions inherit from `CursorPipeError`:

| Exception | When |
|-----------|------|
| `AgentNotFoundError` | Agent binary not found |
| `AuthenticationError` | Auth failed or missing |
| `AgentTimeoutError` | Request exceeded timeout |
| `RateLimitError` | Cursor returned 429 |
| `AgentCrashError` | Agent process exited unexpectedly |
| `SessionError` | ACP session error |

> Full API docs: **[abhi5h3k.github.io/cursorpipe/api-reference](https://abhi5h3k.github.io/cursorpipe/api-reference/)**

---

## Testing

```bash
# Preflight checks — tells you what's missing
pytest tests/test_preflight.py -v

# Unit tests (no agent needed, fast)
pytest tests/test_unit.py -v

# Integration tests (needs agent + auth, slow)
pytest tests/test_integration.py -v -m integration

# Everything
pytest -v
```

---

## Contributing

```bash
# Clone and install with dev dependencies
git clone https://github.com/Abhi5h3k/cursorpipe.git
cd cursorpipe
pip install -e ".[dev]"

# Set up pre-commit hooks (ruff format + lint)
pre-commit install

# Run linter
ruff check .

# Run formatter
ruff format .

# Run tests
pytest -v
```

---

## Architecture

```
Your Python code
    |
    v
CursorClient (cursorpipe)
    |
    +--> AcpTransport ----stdin/stdout----> agent acp (persistent process)
    |       |                                   |
    |       +--> SessionDispenser               |
    |            (pre-created sessions)         |
    |                                           |
    +--> SubprocessTransport ---spawn---->  agent --print (per request)
                                                |
                                                v
                                          Cursor API (cloud)
                                                |
                                                v
                                        Claude / GPT / etc.
```

---

## License

MIT
