# cursorpipe

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Cursor CLI](https://img.shields.io/badge/cursor%20cli-v2026.03.25-purple.svg)](https://cursor.com/docs/cli/installation)

> **Two versions available:**
> - **[v2 (recommended)](v2/README.md)** — SDK-based, requires `CURSOR_API_KEY`, adds stateful sessions, thinking support, and CORS
> - **v1 (this page)** — CLI-based, works with `CURSOR_API_KEY` **or** `agent login` (no key needed if you have a Cursor IDE session)

**Async Python client and OpenAI-compatible HTTP server for the Cursor Agent CLI** — pipe prompts to frontier LLMs via [ACP (Agent Client Protocol)](https://cursor.com/docs/cli/acp) with persistent sessions, streaming, and per-call model selection.

> **[Read the full documentation](https://abhi5h3k.github.io/cursorpipe/)**

<img width="2752" height="1536" alt="cursorpipe" src="https://github.com/user-attachments/assets/f2b3c1c7-e5f5-4cce-b9f4-18822f6fbcd0" />


---

## Why cursorpipe?

If you have a [Cursor](https://cursor.com) subscription, you already have access to frontier models (Claude, GPT, etc.) through the Cursor Agent CLI. **cursorpipe** lets you use those models programmatically — from Python, from any language via HTTP, or from any LLM tool via Docker.

No OpenAI or Anthropic API keys needed. One Cursor subscription, three ways to use it.

<img width="2816" height="1536" alt="architecture" src="https://github.com/user-attachments/assets/c415aadf-1b76-4ce0-ae72-bc4250258e40" />

---

## Three ways to use cursorpipe

### 1. Docker — self-hosted OpenAI-compatible API (any language)

Turn your Cursor subscription into a self-hosted LLM API with one command. Works with **any language**, **any framework**, **any tool** that speaks the OpenAI protocol.

```bash
# bash / macOS / Linux / WSL
git clone https://github.com/Abhi5h3k/cursorpipe.git
cd cursorpipe
export CURSOR_API_KEY=crsr_your_key_here
docker compose up
```

```powershell
# Windows (PowerShell)
git clone https://github.com/Abhi5h3k/cursorpipe.git
cd cursorpipe
$env:CURSOR_API_KEY = "crsr_your_key_here"
docker compose up
```

Then call it from anywhere:

```bash
# bash / macOS / Linux / WSL
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-4.5-sonnet-thinking","messages":[{"role":"user","content":"Hello!"}]}'
```

```powershell
# Windows (PowerShell)
Invoke-RestMethod http://localhost:8080/v1/chat/completions `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"model":"claude-4.5-sonnet-thinking","messages":[{"role":"user","content":"Hello!"}]}'
```

Works out of the box with OpenAI SDK, LangChain, LiteLLM, Open WebUI, LobeChat, Vercel AI SDK, and anything that speaks the OpenAI API.

### 2. HTTP Server — standalone (no Docker)

```bash
# bash / macOS / Linux / WSL
pip install "cursorpipe[server] @ git+https://github.com/Abhi5h3k/cursorpipe.git@v0.1.0"
export CURSOR_API_KEY=crsr_your_key_here
cursorpipe-server
```

```powershell
# Windows (PowerShell)
pip install "cursorpipe[server] @ git+https://github.com/Abhi5h3k/cursorpipe.git@v0.1.0"
$env:CURSOR_API_KEY = "crsr_your_key_here"
cursorpipe-server
```

Server starts on `http://localhost:8080` with OpenAI-compatible endpoints.

### 3. Python Library — async-first

```bash
pip install "cursorpipe @ git+https://github.com/Abhi5h3k/cursorpipe.git@v0.1.0"
```

```python
import asyncio
from cursorpipe import CursorClient

async def main():
    client = CursorClient()
    await client.warmup(pool_size=3)

    response = await client.generate(
        model="claude-4.5-sonnet-thinking",
        prompt="Explain what an API is in two sentences.",
    )
    print(response)
    await client.close()

asyncio.run(main())
```

<img width="2752" height="1536" alt="ways to use cursorpipe" src="https://github.com/user-attachments/assets/1f071585-9867-45db-888e-eb71e4df5add" />


---

## Prerequisites

### Cursor Agent CLI

```bash
# macOS / Linux / WSL
curl https://cursor.com/install -fsS | bash
```

```powershell
# Windows (PowerShell)
irm 'https://cursor.com/install?win32=true' | iex
```

> **Docker users** — the Dockerfile handles this automatically during build.

### Authentication

```bash
# Interactive login (local dev)
agent login
```

```bash
# OR set an API key — bash / macOS / Linux / WSL
export CURSOR_API_KEY=crsr_your_key_here
```

```powershell
# OR set an API key — Windows (PowerShell)
$env:CURSOR_API_KEY = "crsr_your_key_here"
```

```cmd
REM OR set an API key — Windows (CMD)
set CURSOR_API_KEY=crsr_your_key_here
```

Get your API key at [cursor.com/dashboard/api](https://cursor.com/dashboard/api?section=user-keys#user-api-keys) — see [How to create a Cursor API key](https://abhi5h3k.github.io/cursorpipe/cursor-api-key/) for a step-by-step guide.

> **Corporate / proxy environments:** In networks with a TLS-intercepting proxy (e.g. Zscaler), the `agent` binary's outbound connection to `cursor.sh` may be blocked or fail with a certificate error. Ask your network team to whitelist `*.cursor.sh` and `*.cursor.com`, or point the agent to your corporate CA via `SSL_CERT_FILE` / `NODE_EXTRA_CA_CERTS`.

---

## HTTP API Reference

See the full [API reference](https://abhi5h3k.github.io/cursorpipe/api-reference/) for schemas, error codes, and streaming details.

### POST `/v1/chat/completions`

OpenAI-compatible chat completions. Supports streaming (SSE) and non-streaming.

**Request:**

```json
{
  "model": "claude-4.5-sonnet-thinking",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello!"}
  ],
  "stream": false,
  "temperature": 0,
  "max_tokens": 2048
}
```

**Response (non-streaming):**

```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1712160000,
  "model": "claude-4.5-sonnet-thinking",
  "choices": [{
    "index": 0,
    "message": {"role": "assistant", "content": "Hello! How can I help?"},
    "finish_reason": "stop"
  }],
  "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
}
```

**Streaming** — set `"stream": true` and receive Server-Sent Events:

```
data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","model":"claude-4.5-sonnet-thinking","choices":[{"index":0,"delta":{"role":"assistant","content":"Hello"},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","model":"claude-4.5-sonnet-thinking","choices":[{"index":0,"delta":{"content":"!"},"finish_reason":null}]}

data: [DONE]
```

### GET `/v1/models`

List available models.

### GET `/health`

Health check for Docker/Kubernetes.

---

## Using with popular tools

### OpenAI Python SDK

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8080/v1", api_key="unused")
response = client.chat.completions.create(
    model="claude-4.5-sonnet-thinking",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)
```

### OpenAI Node.js SDK

```javascript
import OpenAI from "openai";

const client = new OpenAI({ baseURL: "http://localhost:8080/v1", apiKey: "unused" });
const response = await client.chat.completions.create({
  model: "claude-4.5-sonnet-thinking",
  messages: [{ role: "user", content: "Hello!" }],
});
console.log(response.choices[0].message.content);
```

### LangChain

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    base_url="http://localhost:8080/v1",
    api_key="unused",
    model="claude-4.5-sonnet-thinking",
)
print(llm.invoke("Hello!").content)
```

### curl

```bash
# bash / macOS / Linux / WSL
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-4.5-sonnet-thinking","messages":[{"role":"user","content":"Hello!"}]}'
```

```powershell
# Windows (PowerShell)
Invoke-RestMethod http://localhost:8080/v1/chat/completions `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"model":"claude-4.5-sonnet-thinking","messages":[{"role":"user","content":"Hello!"}]}'
```

---

## Python Library Features

### Warmup (recommended for production)

```python
client = CursorClient()
await client.warmup(pool_size=5)
```

### Per-call model selection

```python
# With the default AUTO strategy, each call with a specific model name is
# automatically routed through subprocess, which passes --model to the CLI.
# Using model="auto" keeps the request on the warm ACP session instead.
intent = await client.generate(model="gpt-5.4-mini-medium", prompt="Classify: 'top 10 users'")
sql = await client.generate(model="claude-4.5-sonnet-thinking", prompt="Generate SQL for: top 10 users")
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

```python
async with client.session("claude-4.5-sonnet-thinking") as session:
    r1 = await session.prompt("Generate SQL for top 10 users by revenue")
    r2 = await session.prompt("Add a WHERE clause for date > 2026-01-01")
```

<img width="2752" height="1536" alt="session" src="https://github.com/user-attachments/assets/d3ecad3b-9b43-4966-9ff8-7a5bf3ef4bc6" />


### Active request tracking

`CursorClient` exposes an `active_requests` property that reports how many LLM requests are currently in-flight. Useful for load-aware concurrency scaling in background workers.

```python
client = CursorClient()
print(client.active_requests)  # 0 when idle
```

All code paths are tracked: `generate()`, `chat()`, `stream()`, `session.prompt()`, and `session.stream_prompt()`. The counter is decremented even if the request raises an exception.

### Framework integration (Chainlit / FastAPI)

```python
session = await client.create_session("claude-4.5-sonnet-thinking")
response = await session.prompt(message.content)
session.discard()
```

---

## Configuration

All settings load from environment variables (prefix `CURSORPIPE_`) or a `.env` file. See the full [Configuration reference](https://abhi5h3k.github.io/cursorpipe/configuration/) in the docs.

### Core settings

| Variable | Default | Description |
|----------|---------|-------------|
| `CURSORPIPE_AGENT_BIN` | `agent` | Path to the agent binary |
| `CURSORPIPE_STRATEGY` | `auto` | Transport: `acp` (persistent, Cursor auto-selects model), `subprocess` (per-call, `--model` passed), `auto` (smart: specific model → subprocess, `"auto"` → ACP) |
| `CURSORPIPE_DEFAULT_MODE` | `ask` | ACP mode: `ask`, `agent`, `plan` |
| `CURSORPIPE_REQUEST_TIMEOUT_S` | `300` | Per-request timeout in seconds |
| `CURSORPIPE_ACP_STARTUP_TIMEOUT_S` | `30` | Max seconds for ACP startup |
| `CURSORPIPE_ACP_MAX_RESTARTS` | `3` | Auto-restart attempts for crashed ACP |
| `CURSORPIPE_WORKSPACE` | `""` | Working directory for the agent |
| `CURSORPIPE_API_KEY` | `""` | Cursor API key (also reads `CURSOR_API_KEY`) |
| `CURSORPIPE_ENABLE_PROFILING` | `false` | Log timing diagnostics |

### Server settings (HTTP server / Docker only)

| Variable | Default | Description |
|----------|---------|-------------|
| `CURSORPIPE_HOST` | `0.0.0.0` | Bind address |
| `CURSORPIPE_PORT` | `8080` | Bind port |
| `CURSORPIPE_POOL_SIZE` | `5` | Sessions to pre-create at startup |
| `CURSORPIPE_BEARER_TOKEN` | `""` | Optional auth token for incoming requests |

---

## Examples

The [`examples/`](examples/) folder has runnable scripts for every feature. See the [examples docs](https://abhi5h3k.github.io/cursorpipe/examples/) for annotated walkthroughs.

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
| [`openai_sdk.py`](examples/openai_sdk.py) | OpenAI SDK against cursorpipe-server |

---

## Architecture

<img width="2816" height="1536" alt="architecture" src="https://github.com/user-attachments/assets/c415aadf-1b76-4ce0-ae72-bc4250258e40" />


---

## Testing

```bash
pytest tests/test_preflight.py -v   # Environment checks
pytest tests/test_unit.py -v        # Fast, offline
pytest tests/test_integration.py -v # Real API calls (slow)
pytest -v                           # Everything
```

See the [full testing guide](https://abhi5h3k.github.io/cursorpipe/testing/) for HTTP server tests, environment setup, and per-test descriptions.

---

## Contributing

```bash
git clone https://github.com/Abhi5h3k/cursorpipe.git
cd cursorpipe
pip install -e ".[dev,server]"
pre-commit install
ruff check .
ruff format .
pytest -v
```

---

## License

MIT
