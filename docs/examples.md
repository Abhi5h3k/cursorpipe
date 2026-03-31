# Examples

All examples are runnable scripts in the [`examples/`](https://github.com/Abhi5h3k/cursorpipe/tree/main/examples) folder.

!!! info "Tested with"
    - cursorpipe 0.1.0
    - Cursor Agent CLI v2026.03.25-933d5a6
    - Python 3.14

## Basic completion

The simplest way to get a response — one prompt, one answer:

```python
import asyncio
from cursorpipe import CursorClient

async def main():
    client = CursorClient()

    response = await client.generate(
        model="claude-4.5-sonnet-thinking",
        prompt="Explain what an API is in two sentences, as if to a 10-year-old.",
    )
    print(response)

    await client.close()

asyncio.run(main())
```

```bash
python examples/basic.py
```

## Streaming

See the response appear word-by-word instead of waiting for the full answer:

```python
import asyncio
from cursorpipe import CursorClient

async def main():
    client = CursorClient()

    async for chunk in client.stream(
        model="claude-4.5-sonnet-thinking",
        prompt="Write a short poem about coding at midnight.",
    ):
        print(chunk, end="", flush=True)
    print()

    await client.close()

asyncio.run(main())
```

```bash
python examples/streaming.py
```

## Multi-turn sessions

Sessions keep conversation history on the server — the LLM remembers everything from previous turns:

```python
import asyncio
from cursorpipe import CursorClient

async def main():
    client = CursorClient()

    async with client.session("claude-4.5-sonnet-thinking") as session:
        r1 = await session.prompt("What is 42 * 3?")
        print(f"AI: {r1.text}")

        r2 = await session.prompt("Now double that result.")
        print(f"AI: {r2.text}")

        r3 = await session.prompt("What was the original multiplication I asked about?")
        print(f"AI: {r3.text}")

        print(f"\nTotal turns: {session.turn_count}")

    await client.close()

asyncio.run(main())
```

```bash
python examples/multi_turn.py
```

## API key authentication

Use an API key instead of interactive `agent login` — ideal for scripts, CI, and servers:

```python
import asyncio
from cursorpipe import CursorClient, CursorPipeConfig

async def main():
    # Option 1: auto-load from CURSORPIPE_API_KEY env var or .env file
    client = CursorClient()

    # Option 2: pass explicitly
    # config = CursorPipeConfig(api_key="crsr_your_key_here")
    # client = CursorClient(config)

    response = await client.generate(
        model="claude-4.5-sonnet-thinking",
        prompt="Reply with exactly: AUTH_OK",
        system="Reply with exactly what is asked, nothing else.",
    )
    print("Auth working!" if "AUTH_OK" in response else f"Unexpected: {response}")

    await client.close()

asyncio.run(main())
```

```bash
CURSORPIPE_API_KEY=crsr_your_key python examples/api_key_auth.py
```

Get your API key at [cursor.com/dashboard/cloud-agents](https://cursor.com/dashboard/cloud-agents).
