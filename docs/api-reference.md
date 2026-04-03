# API Reference

---

## HTTP API (cursorpipe-server)

cursorpipe-server exposes an OpenAI-compatible HTTP API. See [HTTP Server](server.md) for full endpoint documentation.

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/chat/completions` | Chat completions (streaming + non-streaming) |
| GET | `/v1/models` | List available models |
| GET | `/health` | Health check |

### Request schema

```python
{
    "model": "claude-4.5-sonnet-thinking",
    "messages": [
        {"role": "system", "content": "..."},
        {"role": "user", "content": "..."}
    ],
    "stream": false,      # true for SSE streaming
    "temperature": 0,
    "max_tokens": 2048
}
```

### Server config

| Variable | Default | Description |
|----------|---------|-------------|
| `CURSORPIPE_HOST` | `0.0.0.0` | Bind address |
| `CURSORPIPE_PORT` | `8080` | Bind port |
| `CURSORPIPE_POOL_SIZE` | `5` | Sessions to pre-create at startup |
| `CURSORPIPE_BEARER_TOKEN` | `""` | Optional auth for incoming requests |

---

## Python API

### CursorClient

The main entry point. Handles transport selection, fallback, and resource cleanup.

```python
from cursorpipe import CursorClient

client = CursorClient()          # auto-load config from env / .env
client = CursorClient(config)    # explicit CursorPipeConfig
```

#### Methods

| Method | Description |
|--------|-------------|
| `warmup(pool_size=5)` | Pre-start ACP process and pre-create sessions |
| `generate(model, prompt, *, system, temperature, max_tokens, timeout_s)` | Single completion, returns `str` |
| `chat(model, messages, *, temperature, max_tokens, timeout_s)` | Chat with message history, returns `str` |
| `stream(model, prompt, *, system, timeout_s)` | Streaming completion, yields `str` chunks |
| `session(model)` | Create a `CursorSession` context manager |
| `create_session(model)` | Create a `CursorSession` with explicit lifecycle |
| `list_models()` | Discover available models |
| `close()` | Shut down transports and release resources |

#### warmup()

Pre-start the ACP process and fill the session dispenser. Call once at app startup to eliminate cold-start latency on the first real request.

```python
await client.warmup(pool_size=5)
```

Without warmup, the first request takes ~14s (process spawn + session creation + LLM).
With warmup, the first request takes ~5s (LLM only).

#### generate()

```python
response = await client.generate(
    model="claude-4.5-sonnet-thinking",
    prompt="Explain Python's GIL.",
    system="You are a helpful teacher.",    # optional
    temperature=0,                          # optional, default 0
    max_tokens=2048,                        # optional, default 2048
    timeout_s=60,                           # optional, default from config
)
```

#### chat()

Accepts a list of message dicts. Messages are merged into a single prompt internally.

```python
response = await client.chat(
    model="claude-4.5-sonnet-thinking",
    messages=[
        {"role": "system", "content": "You are a SQL expert."},
        {"role": "user", "content": "Show top 10 users"},
        {"role": "assistant", "content": "SELECT * FROM users LIMIT 10;"},
        {"role": "user", "content": "Add a date filter for 2026"},
    ],
)
```

#### stream()

Returns an async iterator. Use `async for` to get chunks:

```python
async for chunk in client.stream(
    model="claude-4.5-sonnet-thinking",
    prompt="Write a detailed analysis...",
):
    print(chunk, end="", flush=True)
```

#### session()

Creates a multi-turn session with server-side history (ACP only). Use as an async context manager:

```python
async with client.session("claude-4.5-sonnet-thinking") as session:
    r1 = await session.prompt("Generate SQL for top 10 users")
    r2 = await session.prompt("Add a WHERE clause")  # remembers r1
```

#### create_session()

Creates a multi-turn session with explicit lifecycle control — ideal for frameworks like Chainlit or FastAPI where create, use, and destroy happen in different callback functions:

```python
session = await client.create_session("claude-4.5-sonnet-thinking")
r1 = await session.prompt("Generate SQL for top 10 users")
r2 = await session.prompt("Add a WHERE clause")
session.discard()
```

---

### CursorSession

Returned by `client.session()` or `client.create_session()`.

| Property / Method | Description |
|-------------------|-------------|
| `prompt(text, *, timeout_s)` | Send a prompt (history preserved), returns `CompletionResult` |
| `stream_prompt(text, *, timeout_s)` | Streaming prompt, yields `str` chunks |
| `discard()` | Release this session (no-op if already discarded) |
| `model` | The model for this session |
| `session_id` | The ACP session ID |
| `turn_count` | Number of prompts sent |

---

### CursorPipeConfig

All settings are loaded from environment variables (prefix `CURSORPIPE_`) or a `.env` file.

```python
from cursorpipe import CursorPipeConfig, Strategy

config = CursorPipeConfig(
    api_key="crsr_...",
    strategy=Strategy.ACP,
    request_timeout_s=120,
)
```

| Variable | Default | Description |
|----------|---------|-------------|
| `CURSORPIPE_AGENT_BIN` | `agent` | Path to the agent binary |
| `CURSORPIPE_STRATEGY` | `auto` | Transport: `acp`, `subprocess`, `auto` |
| `CURSORPIPE_DEFAULT_MODE` | `ask` | ACP mode: `ask`, `agent`, `plan` |
| `CURSORPIPE_REQUEST_TIMEOUT_S` | `300` | Per-request timeout in seconds |
| `CURSORPIPE_ACP_STARTUP_TIMEOUT_S` | `30` | Max seconds for ACP startup |
| `CURSORPIPE_ACP_MAX_RESTARTS` | `3` | Auto-restart attempts for crashed ACP |
| `CURSORPIPE_WORKSPACE` | `""` | Working directory for the agent |
| `CURSORPIPE_API_KEY` | `""` | Cursor API key (also reads `CURSOR_API_KEY`) |
| `CURSORPIPE_ENABLE_PROFILING` | `false` | Log timing diagnostics (TTFC, per-chunk gaps) |

---

### CompletionResult

Returned by `session.prompt()`.

| Field | Type | Description |
|-------|------|-------------|
| `text` | `str` | The response text |
| `model` | `str` | Model that generated the response |
| `session_id` | `str` | ACP session ID |
| `stop_reason` | `str` | Why generation stopped |
| `duration_ms` | `int` | Response time (subprocess only) |

---

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

```python
from cursorpipe import CursorPipeError, AuthenticationError

try:
    response = await client.generate(model="...", prompt="...")
except AuthenticationError:
    print("Run `agent login` or set CURSORPIPE_API_KEY")
except CursorPipeError as e:
    print(f"Something went wrong: {e}")
```

---

### Module-level convenience

For quick scripts without explicit client management:

```python
from cursorpipe import generate, chat, warmup, close

await warmup(pool_size=3)
result = await generate(model="gpt-5.4-mini-medium", prompt="What is 2+2?")
await close()
```

These use a global singleton `CursorClient` under the hood.
