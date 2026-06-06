# cursorpipe v2

**OpenAI-compatible HTTP server powered by the official [Cursor Python SDK](https://cursor.com/docs/sdk/python).**

Point any OpenAI-compatible client at `http://localhost:8080` and use Cursor's frontier models without changing a line of code.

---

## Why v2?

| | v1 (CLI-based) | v2 (SDK-based) |
|---|---|---|
| Backend | Cursor Agent CLI subprocess | Official `cursor-sdk` Python library |
| Auth | `CURSOR_API_KEY` **or** `agent login` (no key needed) | `CURSOR_API_KEY` required |
| Stateful sessions | No | Yes (`X-Cursor-Session-ID`) |
| Thinking/reasoning | No | Yes (opt-in) |
| CORS | No | Yes |
| Session management API | No | Yes |
| Docker | Yes | Yes |

**Use v1** if you have a Cursor IDE login but no API key (common in corporate environments where an admin controls access).

**Use v2** if you have a Cursor API key and want stateful sessions, thinking support, and a production-ready server.

<img width="2752" height="1536" alt="cursorpipe v2 Architecture" src="https://github.com/user-attachments/assets/d695b118-998a-4120-9374-809bda663b54" />

---

## Quick start

### Option 1 — pip install (simplest)

```bash
# bash / macOS / Linux / WSL
pip install "cursorpipe[server] @ git+https://github.com/Abhi5h3k/cursorpipe.git@v2.0.1#subdirectory=v2"
export CURSOR_API_KEY=crsr_your_key_here
cursorpipe-server
```

```powershell
# Windows (PowerShell)
pip install "cursorpipe[server] @ git+https://github.com/Abhi5h3k/cursorpipe.git@v2.0.1#subdirectory=v2"
$env:CURSOR_API_KEY = "crsr_your_key_here"
cursorpipe-server
```

Server starts on `http://localhost:8080`.

> `#subdirectory=v2` tells pip to install from the `v2/` folder of this repo.
> v1 and v2 share the package name `cursorpipe` — install one or the other, not both.

### Option 2 — Docker

#### 2a — Pre-built image (fastest, no clone needed)

```bash
# bash / macOS / Linux / WSL
docker run --rm -p 8080:8080 \
  -e CURSOR_API_KEY=crsr_your_key_here \
  ghcr.io/abhi5h3k/cursorpipe:latest
```

```powershell
# Windows (PowerShell)
docker run --rm -p 8080:8080 `
  -e CURSOR_API_KEY=crsr_your_key_here `
  ghcr.io/abhi5h3k/cursorpipe:latest
```

For multiple settings, use an env file:

```bash
cp v2/.env.example .env
# → fill in CURSOR_API_KEY and any overrides

docker run --rm -p 8080:8080 --env-file .env \
  ghcr.io/abhi5h3k/cursorpipe:latest
```

The image is rebuilt automatically on every push to `main`.

#### 2b — Build from source

```bash
# bash / macOS / Linux / WSL
git clone https://github.com/Abhi5h3k/cursorpipe.git
cd cursorpipe/v2
cp .env.example .env
# → set CURSOR_API_KEY in .env
docker compose up --build
```

```powershell
# Windows (PowerShell)
git clone https://github.com/Abhi5h3k/cursorpipe.git
cd cursorpipe/v2
cp .env.example .env
# → set CURSOR_API_KEY in .env
docker compose up --build
```

### Option 3 — clone + uv (for development)

```bash
git clone https://github.com/Abhi5h3k/cursorpipe.git
cd cursorpipe/v2

# Windows/OneDrive: set UV_LINK_MODE=copy to avoid hardlink errors
# $env:UV_LINK_MODE="copy"
uv sync --extra server

cp .env.example .env
# → set CURSOR_API_KEY in .env

python -m cursorpipe_server
```

---

## First request

```bash
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "composer-2.5",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

```python
# Works with the standard OpenAI SDK — no changes needed
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8080/v1", api_key="not-needed")
response = client.chat.completions.create(
    model="composer-2.5",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)
```

---

## Features at a glance

- **OpenAI-compatible** `/v1/chat/completions` — works with LangChain, LiteLLM, Open WebUI, and any OpenAI client
- **Streaming** — true SSE, token by token
- **Stateless by default** — each request is independent; client sends full conversation history
- **Opt-in stateful sessions** — add `X-Cursor-Session-ID` to preserve agent state across turns
- **Session management API** — list, create, inspect, and delete sessions via REST
- **Thinking/reasoning content** — opt-in `reasoning_content` exposure (compatible with DeepSeek/o1 clients)
- **CORS** — browser clients work out of the box
- **Request tracing** — `X-Request-ID` on every response
- **Structured logging** — configurable log level
- **Docker + healthcheck** — production-ready from day one

---

## Next steps

- [Configuration](config.md) — all environment variables
- [API Reference](api.md) — endpoint documentation
- [Thinking / Reasoning](thinking.md) — how to expose model thinking
- [SDK Limitations](limitations.md) — what cursorpipe v2 cannot do
