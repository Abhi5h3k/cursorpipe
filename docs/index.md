# cursorpipe

**Async Python client and OpenAI-compatible HTTP server for the Cursor Agent CLI** — pipe prompts to frontier LLMs via [ACP (Agent Client Protocol)](https://cursor.com/docs/cli/acp) with persistent sessions, streaming, and per-call model selection.

---

## Three ways to use cursorpipe

### Docker — self-hosted OpenAI-compatible API

Turn your Cursor subscription into a self-hosted LLM API with one command. Works with **any language**, **any framework**, **any tool** that speaks the OpenAI protocol.

```bash
git clone https://github.com/Abhi5h3k/cursorpipe.git && cd cursorpipe
export CURSOR_API_KEY=crsr_your_key_here
docker compose up
```

### HTTP Server — standalone

```bash
pip install "cursorpipe[server] @ git+https://github.com/Abhi5h3k/cursorpipe.git"
cursorpipe-server
```

### Python Library — async-first

```python
from cursorpipe import CursorClient

client = CursorClient()
response = await client.generate(
    model="claude-4.5-sonnet-thinking",
    prompt="Explain what an API is in two sentences.",
)
```

---

## Highlights

- **Language-agnostic HTTP API** — OpenAI-compatible; works with any SDK, any language
- **Docker-ready** — one `docker compose up` and you have an LLM API
- **Async-first Python library** — built on `asyncio` for non-blocking LLM calls
- **Persistent ACP transport** — keeps a single agent process alive, ~50ms overhead per request
- **Multi-turn sessions** — server-side conversation history, no need to resend messages
- **Session isolation** — every request gets a fresh session; no history leaks between users or calls
- **Warmup support** — pre-start the process and pre-create sessions to eliminate cold-start latency
- **Per-call model selection** — route different tasks to different models in a single client
- **Streaming** — SSE over HTTP, or `async for` in Python
- **Auto-fallback** — tries ACP first, falls back to subprocess if needed
- **Typed everything** — Pydantic models, custom exceptions, `py.typed` for IDE support

## Next steps

- [Getting Started](getting-started.md) — install and run your first prompt
- [HTTP Server](server.md) — OpenAI-compatible API documentation
- [Docker](docker.md) — one-command Docker deployment
- [Examples](examples.md) — runnable scripts for every feature
- [API Reference](api-reference.md) — full method and class documentation
- [Architecture](architecture.md) — how ACP, subprocess, and HTTP transports work
