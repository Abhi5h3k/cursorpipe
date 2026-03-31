# cursorpipe

**Async Python client for the Cursor Agent CLI** — pipe prompts to frontier LLMs via [ACP (Agent Client Protocol)](https://cursor.com/docs/cli/acp) with persistent sessions, streaming, and per-call model selection.

---

## Why cursorpipe?

If you have a [Cursor](https://cursor.com) subscription, you already have access to frontier models (Claude, GPT, etc.) through the Cursor Agent CLI. **cursorpipe** lets you use those models programmatically from Python — no separate API keys needed.

## Highlights

- **Async-first** — built on `asyncio` for non-blocking LLM calls
- **Persistent ACP transport** — keeps a single agent process alive, ~50ms overhead per request
- **Multi-turn sessions** — server-side conversation history, no need to resend messages
- **Per-call model selection** — route different tasks to different models in a single client
- **Streaming** — `async for` over response chunks as they arrive
- **No prompt-length limit** — prompts sent over stdin, not CLI args
- **Auto-fallback** — tries ACP first, falls back to subprocess if needed
- **Typed everything** — Pydantic models, custom exceptions, `py.typed` for IDE support

## Quick example

```python
import asyncio
from cursorpipe import CursorClient

async def main():
    client = CursorClient()

    response = await client.generate(
        model="claude-4.5-sonnet-thinking",
        prompt="Explain what an API is in two sentences.",
    )
    print(response)

    await client.close()

asyncio.run(main())
```

## Next steps

- [Getting Started](getting-started.md) — install and run your first prompt
- [Examples](examples.md) — runnable scripts for every feature
- [API Reference](api-reference.md) — full method and class documentation
- [Architecture](architecture.md) — how ACP and subprocess transports work
