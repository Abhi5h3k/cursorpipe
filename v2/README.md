# cursorpipe v2

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](../LICENSE)
[![cursor-sdk](https://img.shields.io/badge/cursor--sdk-0.1.7-purple.svg)](https://cursor.com/docs/sdk/python)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg)](https://fastapi.tiangolo.com)
[![OpenAI compatible](https://img.shields.io/badge/OpenAI-compatible-412991.svg)](https://platform.openai.com/docs/api-reference/chat)

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

## Quick start

### Option 1 — pip install (simplest)

```bash
# bash / macOS / Linux / WSL
pip install "cursorpipe[server] @ git+https://github.com/Abhi5h3k/cursorpipe.git@v2.0.7#subdirectory=v2"
export CURSOR_API_KEY=crsr_your_key_here
cursorpipe-server
```

```powershell
# Windows (PowerShell)
pip install "cursorpipe[server] @ git+https://github.com/Abhi5h3k/cursorpipe.git@v2.0.7#subdirectory=v2"
$env:CURSOR_API_KEY = "crsr_your_key_here"
cursorpipe-server
```

Server starts on `http://localhost:8080`.

> **Note:** `#subdirectory=v2` tells pip to install from the `v2/` folder of this repo.
> v1 and v2 share the package name `cursorpipe` — install one or the other, not both.

### Option 2 — Docker

#### 2a — Pre-built image (fastest, no clone needed)

Pull the image that is automatically built on every push to `main`:

```bash
# bash / macOS / Linux / WSL — pass a single env var
docker run --rm -p 8080:8080 --pull always \
  -e CURSOR_API_KEY=crsr_your_key_here \
  ghcr.io/abhi5h3k/cursorpipe:latest
```

```powershell
# Windows (PowerShell)
docker run --rm -p 8080:8080 --pull always `
  -e CURSOR_API_KEY=crsr_your_key_here `
  ghcr.io/abhi5h3k/cursorpipe:latest
```

> **Tip:** `--pull always` ensures Docker fetches the latest image before starting, even if a local copy exists.

For multiple settings, use an env file — cleaner than a long chain of `-e` flags:

```bash
# bash / macOS / Linux / WSL
cp v2/.env.example .env
# → fill in CURSOR_API_KEY and any overrides

docker run --rm -p 8080:8080 --pull always --env-file .env \
  ghcr.io/abhi5h3k/cursorpipe:latest
```

```powershell
# Windows (PowerShell)
Copy-Item v2\.env.example .env
# → fill in CURSOR_API_KEY and any overrides

docker run --rm -p 8080:8080 --pull always --env-file .env `
  ghcr.io/abhi5h3k/cursorpipe:latest
```

See the [Configuration](#configuration) table for all available env vars.

#### 2b — Build from source

```bash
# bash / macOS / Linux / WSL
git clone https://github.com/Abhi5h3k/cursorpipe.git
cd cursorpipe/v2
cp .env.example .env
# → set CURSOR_API_KEY (and any other vars) in .env
docker compose up --build
```

```powershell
# Windows (PowerShell)
git clone https://github.com/Abhi5h3k/cursorpipe.git
cd cursorpipe/v2
cp .env.example .env
# → set CURSOR_API_KEY (and any other vars) in .env
docker compose up --build
```

### Option 3 — clone + uv (for development)

```bash
# bash / macOS / Linux / WSL
git clone https://github.com/Abhi5h3k/cursorpipe.git
cd cursorpipe/v2
uv sync --extra server
cp .env.example .env
# → set CURSOR_API_KEY in .env
python -m cursorpipe_server
```

```powershell
# Windows (PowerShell)
git clone https://github.com/Abhi5h3k/cursorpipe.git
cd cursorpipe/v2
# OneDrive: uncomment to avoid hardlink errors
# $env:UV_LINK_MODE = "copy"
uv sync --extra server
Copy-Item .env.example .env
# → set CURSOR_API_KEY in .env
python -m cursorpipe_server
```

---

## Configuration

All settings are read from environment variables (or `.env` file).

| Variable | Default | Description |
|---|---|---|
| `CURSOR_API_KEY` | *(required)* | Cursor API key from [cursor.com/settings](https://cursor.com/settings). `CURSORPIPE_API_KEY` is also accepted (v1 compatibility). |
| `CURSORPIPE_HOST` | `0.0.0.0` | Bind address |
| `CURSORPIPE_PORT` | `8080` | Listen port |
| `CURSORPIPE_BEARER_TOKEN` | *(empty)* | Protect the API. Empty = no auth |
| `CURSORPIPE_CORS_ORIGINS` | `*` | Comma-separated allowed origins for CORS |
| `CURSORPIPE_MODEL` | `composer-2.5` | Default model |
| `CURSORPIPE_WORKSPACE` | `.` | Working directory for the agent |
| `CURSORPIPE_SESSION_TTL_MINUTES` | `30` | Idle session expiry |
| `CURSORPIPE_THINKING_LEVEL` | `off` | Request and surface thinking: `off`, `low`, or `high`. Backward compat: `CURSORPIPE_EXPOSE_THINKING=true` maps to `high`. |
| `CURSORPIPE_LOG_LEVEL` | `info` | Log level: `debug`, `info`, `warning`, `error`, `critical` |

---

## API reference

### Health

```bash
# bash / macOS / Linux / WSL
curl http://localhost:8080/health
# {"status":"ok","bridge":"connected"}
```

```powershell
# Windows (PowerShell)
Invoke-RestMethod http://localhost:8080/health
```

Returns 503 if the SDK bridge is unavailable.

### List models

```bash
# bash / macOS / Linux / WSL
curl http://localhost:8080/v1/models
```

```powershell
# Windows (PowerShell)
Invoke-RestMethod http://localhost:8080/v1/models
```

### Chat (stateless, non-streaming)

<img width="1663" height="837" alt="v2 API call" src="https://github.com/user-attachments/assets/d6080d16-9329-4143-9172-e0845642aac0" />



```bash
# bash / macOS / Linux / WSL
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"composer-2.5","messages":[{"role":"user","content":"What is 2+2?"}]}'
```

```powershell
# Windows (PowerShell)
Invoke-RestMethod http://localhost:8080/v1/chat/completions `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"model":"composer-2.5","messages":[{"role":"user","content":"What is 2+2?"}]}'
```

Response includes a `cursor_metadata` field with Cursor-specific details:

```json
{
  "id": "chatcmpl-...",
  "object": "chat.completion",
  "model": "composer-2.5",
  "choices": [{"message": {"role": "assistant", "content": "4"}, "finish_reason": "stop"}],
  "cursor_metadata": {
    "duration_ms": 1240,
    "run_id": "run_...",
    "agent_id": "agent_..."
  }
}
```

### Chat (streaming)

```bash
# bash / macOS / Linux / WSL
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -N \
  -d '{"model":"composer-2.5","stream":true,"messages":[{"role":"user","content":"Count to 5."}]}'
```

```powershell
# Windows (PowerShell) — Invoke-RestMethod buffers the full response; use curl.exe for true streaming
curl.exe http://localhost:8080/v1/chat/completions `
  -H "Content-Type: application/json" `
  -N `
  -d '{\"model\":\"composer-2.5\",\"stream\":true,\"messages\":[{\"role\":\"user\",\"content\":\"Count to 5.\"}]}'
```

### Stateful sessions (multi-turn)

Send `X-Cursor-Session-ID` to opt into stateful mode. The same agent is reused across turns.

```bash
# bash / macOS / Linux / WSL

# First turn — server creates a session and echoes the ID
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Cursor-Session-ID: my-session-1" \
  -d '{"model":"composer-2.5","messages":[{"role":"user","content":"My name is Alice."}]}'

# Second turn — agent already knows Alice
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Cursor-Session-ID: my-session-1" \
  -d '{"model":"composer-2.5","messages":[{"role":"user","content":"What is my name?"}]}'
```

```powershell
# Windows (PowerShell)

# First turn
Invoke-RestMethod http://localhost:8080/v1/chat/completions `
  -Method Post `
  -ContentType "application/json" `
  -Headers @{"X-Cursor-Session-ID"="my-session-1"} `
  -Body '{"model":"composer-2.5","messages":[{"role":"user","content":"My name is Alice."}]}'

# Second turn — agent already knows Alice
Invoke-RestMethod http://localhost:8080/v1/chat/completions `
  -Method Post `
  -ContentType "application/json" `
  -Headers @{"X-Cursor-Session-ID"="my-session-1"} `
  -Body '{"model":"composer-2.5","messages":[{"role":"user","content":"What is my name?"}]}'
```

### Session management

```bash
# bash / macOS / Linux / WSL

# List all active sessions
curl http://localhost:8080/v1/sessions

# Get a specific session
curl http://localhost:8080/v1/sessions/my-session-1

# Explicitly create a session
curl -X POST http://localhost:8080/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{"model":"composer-2.5"}'

# Delete / close a session
curl -X DELETE http://localhost:8080/v1/sessions/my-session-1
```

```powershell
# Windows (PowerShell)

# List all active sessions
Invoke-RestMethod http://localhost:8080/v1/sessions

# Get a specific session
Invoke-RestMethod http://localhost:8080/v1/sessions/my-session-1

# Explicitly create a session
Invoke-RestMethod http://localhost:8080/v1/sessions `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"model":"composer-2.5"}'

# Delete / close a session
Invoke-RestMethod http://localhost:8080/v1/sessions/my-session-1 -Method Delete
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

Set `CURSORPIPE_THINKING_LEVEL=high` (or `low`) before starting the server. Thinking is requested via an SDK model parameter — no special model name needed. Check `GET /v1/models` → `cursor_parameters` to see which models support it.

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
# bash / macOS / Linux / WSL
curl http://localhost:8080/v1/chat/completions \
  -H "X-Request-ID: my-trace-123" \
  -H "Content-Type: application/json" \
  -d '{"model":"composer-2.5","messages":[{"role":"user","content":"Hello!"}]}'
```

```powershell
# Windows (PowerShell)
Invoke-RestMethod http://localhost:8080/v1/chat/completions `
  -Method Post `
  -ContentType "application/json" `
  -Headers @{"X-Request-ID"="my-trace-123"} `
  -Body '{"model":"composer-2.5","messages":[{"role":"user","content":"Hello!"}]}'
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
| `usage` (token counts) | None | SDK returns no token counts; `usage` field removed from responses |
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
