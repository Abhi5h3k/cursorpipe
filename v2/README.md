# cursorpipe v2

<img width="2752" height="1536" alt="cursorpipe v2" src="https://github.com/user-attachments/assets/34f432f4-5c21-4d65-9e45-c80f7a1d7b9c" />


An OpenAI-compatible HTTP server powered by the official [Cursor Python SDK](https://cursor.com/docs/sdk/python).

Point any OpenAI client at `http://localhost:8080` and use Cursor's models without code changes.

---

## Features

- **OpenAI-compatible** `/v1/chat/completions` — works with LangChain, LiteLLM, Open WebUI, and any OpenAI client
- **Streaming** — true server-sent events (SSE), token by token
- **Stateless by default** — each request is independent; client sends full conversation history
- **Opt-in stateful sessions** — add `X-Cursor-Session-ID` header to preserve agent state across turns
- **Session management** — REST endpoints to list, create, inspect and delete sessions
- **Thinking/reasoning content** — opt-in `reasoning_content` exposure (compatible with DeepSeek/o1 clients)
- **CORS** — browser clients work out of the box
- **Request tracing** — `X-Request-ID` header on every response
- **Structured logging** — configurable log level via env var
- **Docker** — one command to run anywhere

---

## Installation

```bash
# pip — pinned release (recommended)
pip install "cursorpipe[server] @ git+https://github.com/Abhi5h3k/cursorpipe.git@v2.0.0#subdirectory=v2"

# pip — latest development (HEAD)
pip install "cursorpipe[server] @ git+https://github.com/Abhi5h3k/cursorpipe.git#subdirectory=v2"

# uv — pinned release
uv add "cursorpipe[server] @ git+https://github.com/Abhi5h3k/cursorpipe.git@v2.0.0#subdirectory=v2"
```

The `#subdirectory=v2` tells pip/uv to install from the `v2/` folder of this repo.
Both v1 and v2 share the package name `cursorpipe` — install one or the other, not both.

---

## Quick start

### Option 1 — Python (with uv)

```bash
# Install uv if you don't have it
pip install uv

# Install cursorpipe with server extras
# On Windows/OneDrive set UV_LINK_MODE=copy first:
#   $env:UV_LINK_MODE="copy"
cd v2
uv sync --extra server

# Copy and edit the env file
cp .env.example .env
# → set CURSOR_API_KEY in .env

# Start the server
python -m cursorpipe_server
```

### Option 2 — Docker

```bash
cd v2
cp .env.example .env
# → set CURSOR_API_KEY in .env

docker compose up --build
```

---

## Configuration

All settings are read from environment variables (or `.env` file).

| Variable | Default | Description |
|---|---|---|
| `CURSOR_API_KEY` | *(required)* | Cursor API key from [cursor.com/settings](https://cursor.com/settings) |
| `CURSORPIPE_HOST` | `0.0.0.0` | Bind address |
| `CURSORPIPE_PORT` | `8080` | Listen port |
| `CURSORPIPE_BEARER_TOKEN` | *(empty)* | Protect the API. Empty = no auth |
| `CURSORPIPE_CORS_ORIGINS` | `*` | Comma-separated allowed origins for CORS |
| `CURSORPIPE_MODEL` | `composer-2.5` | Default model |
| `CURSORPIPE_WORKSPACE` | `.` | Working directory for the agent |
| `CURSORPIPE_SESSION_TTL_MINUTES` | `30` | Idle session expiry |
| `CURSORPIPE_EXPOSE_THINKING` | `false` | Include thinking/reasoning in responses |
| `CURSORPIPE_LOG_LEVEL` | `info` | Log level: `debug`, `info`, `warning`, `error`, `critical` |

---

## API reference

### Health

```bash
curl http://localhost:8080/health
# {"status":"ok","bridge":"connected"}
# Returns 503 if the SDK bridge is unavailable.
```

### List models

```bash
curl http://localhost:8080/v1/models
```

### Chat (stateless, non-streaming)

```bash
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "composer-2.5",
    "messages": [{"role": "user", "content": "What is 2+2?"}]
  }'
```

Response includes a `cursor_metadata` field with Cursor-specific details:

```json
{
  "id": "chatcmpl-...",
  "object": "chat.completion",
  "model": "composer-2.5",
  "choices": [{"message": {"role": "assistant", "content": "4"}, "finish_reason": "stop"}],
  "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
  "cursor_metadata": {
    "duration_ms": 1240,
    "run_id": "run_...",
    "agent_id": "agent_...",
    "session_id": null
  }
}
```

### Chat (streaming)

```bash
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -N \
  -d '{
    "model": "composer-2.5",
    "stream": true,
    "messages": [{"role": "user", "content": "Count to 5."}]
  }'
```

### Stateful sessions (multi-turn)

Send `X-Cursor-Session-ID` to opt into stateful mode. The same agent is reused across turns.

```bash
# First turn — server creates a session and echoes the ID
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Cursor-Session-ID: my-session-1" \
  -d '{"model": "composer-2.5", "messages": [{"role": "user", "content": "My name is Alice."}]}'

# Second turn — agent already knows Alice
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Cursor-Session-ID: my-session-1" \
  -d '{"model": "composer-2.5", "messages": [{"role": "user", "content": "What is my name?"}]}'
```

### Session management

```bash
# List all active sessions
curl http://localhost:8080/v1/sessions

# Get a specific session
curl http://localhost:8080/v1/sessions/my-session-1

# Explicitly create a session and get its ID
curl -X POST http://localhost:8080/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{"model": "composer-2.5"}'

# Delete / close a session
curl -X DELETE http://localhost:8080/v1/sessions/my-session-1
```

Session list response shape:

```json
{
  "object": "list",
  "data": [
    {
      "id": "my-session-1",
      "model": "composer-2.5",
      "created_at": "2026-06-06T12:00:00+00:00",
      "last_used_at": "2026-06-06T12:05:00+00:00"
    }
  ]
}
```

### Thinking / reasoning content

Set `CURSORPIPE_EXPOSE_THINKING=true` and use a model that supports thinking.

**Streaming** — thinking chunks arrive before content chunks:

```jsonc
// reasoning_content chunk
{"choices": [{"delta": {"reasoning_content": "The user asked about..."}}]}
// content chunk
{"choices": [{"delta": {"content": "Paris."}}]}
```

**Non-streaming** — thinking appears in `cursor_metadata`:

```json
{
  "cursor_metadata": {
    "thinking": "The user asked about France...",
    "thinking_duration_ms": 1500
  }
}
```

### OpenAI Python SDK

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8080/v1", api_key="not-needed")
response = client.chat.completions.create(
    model="composer-2.5",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)
```

---

## Request tracing

Every response includes an `X-Request-ID` header. Provide your own to correlate logs:

```bash
curl http://localhost:8080/v1/chat/completions \
  -H "X-Request-ID: my-trace-123" \
  ...
```

---

## SDK limitations

These are gaps in the Cursor SDK that cursorpipe cannot work around. Unsupported
parameters are accepted in the request body and silently ignored.

| OpenAI parameter | SDK support | Notes |
|---|---|---|
| `temperature` | None | Accepted but ignored |
| `top_p` | None | Accepted but ignored |
| `stop` sequences | None | Accepted but ignored |
| `n > 1` (multiple completions) | None | Would need N parallel agents |
| `usage.prompt_tokens` | None | SDK returns no token counts; always 0 |
| `function_calling` / `tools` | None | SDK handles tools internally |
| `logprobs` | None | Not applicable |
| `POST /v1/embeddings` | None | No embedding API in the SDK |

---

## Architecture

<img width="2752" height="1536" alt="cursorpipe v2 Architecture" src="https://github.com/user-attachments/assets/d695b118-998a-4120-9374-809bda663b54" />


---

## Differences from cursorpipe v1

| | v1 | v2 |
|---|---|---|
| Backend | Cursor Agent CLI (ACP/stdin-stdout) | Cursor Python SDK (`cursor-sdk`) |
| Auth | `CURSOR_API_KEY` **or** `agent login` (no API key needed) | `CURSOR_API_KEY` required |
| Sessions | Stateless only | Stateless + opt-in stateful |
| Streaming | Yes | Yes |
| Thinking | No | Yes (opt-in) |
| CORS | No | Yes |
| Session management API | No | Yes |
| Docker | Yes | Yes |
