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

## Warmup (recommended for production)

Pre-start the ACP process and pre-create sessions to eliminate the ~14s cold-start on the first request:

```python
import asyncio
import time
from cursorpipe import CursorClient

async def main():
    client = CursorClient()

    # Pre-warm at startup
    t0 = time.monotonic()
    await client.warmup(pool_size=3)
    print(f"Warmup: {time.monotonic() - t0:.1f}s")

    # First request — same speed as subsequent ones
    t1 = time.monotonic()
    response = await client.generate(
        model="claude-4.5-sonnet-thinking",
        prompt="Reply with: WARMUP_OK",
    )
    print(f"Response in {time.monotonic() - t1:.1f}s: {response.strip()}")

    await client.close()

asyncio.run(main())
```

```bash
python examples/warmup.py
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

## Framework integration (Chainlit / FastAPI)

For frameworks where session create, use, and destroy happen in different callback functions, use `create_session()` with explicit lifecycle:

```python
import asyncio
from cursorpipe import CursorClient

client = CursorClient()

async def app_startup():
    await client.warmup(pool_size=5)

async def on_chat_start(user_id):
    session = await client.create_session("claude-4.5-sonnet-thinking")
    return session  # store in user session

async def on_message(session, message):
    # Server has full history — only send the new message
    async for chunk in session.stream_prompt(message):
        print(chunk, end="", flush=True)
    print()

async def on_chat_end(session):
    session.discard()

async def main():
    await app_startup()

    # Simulate a user conversation
    session = await on_chat_start("alice")
    await on_message(session, "What is 42 * 3?")
    await on_message(session, "Now double that.")  # server remembers the first turn
    await on_chat_end(session)

    await client.close()

asyncio.run(main())
```

```bash
python examples/chainlit_pattern.py
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

## Model switching

Route different tasks to different models in a single client — use a fast model for classification, a powerful model for generation:

```python
import asyncio
from cursorpipe import CursorClient

async def main():
    client = CursorClient()

    # Fast model for classification
    intent = await client.generate(
        model="gpt-5.4-mini-medium",
        prompt="Classify this query: 'show top 10 users by revenue'",
        system="Reply with exactly one of: SQL_QUERY, SCHEMA_QUESTION, GREETING",
    )
    print(f"Intent: {intent.strip()}")

    # Powerful model for the actual work
    sql = await client.generate(
        model="claude-4.5-sonnet-thinking",
        prompt="Generate a PostgreSQL query for: top 10 users by revenue in 2026",
        system="You are a PostgreSQL expert. Reply with only the SQL query.",
    )
    print(f"SQL:\n{sql.strip()}")

    await client.close()

asyncio.run(main())
```

```bash
python examples/model_switching.py
```

## Session streaming

Stream responses chunk-by-chunk within a multi-turn session — real-time output with full conversation memory:

```python
import asyncio
from cursorpipe import CursorClient

async def main():
    client = CursorClient()

    async with client.session("claude-4.5-sonnet-thinking") as session:
        # Turn 1: stream the response
        print("AI: ", end="")
        async for chunk in session.stream_prompt(
            "Write a haiku about async Python programming."
        ):
            print(chunk, end="", flush=True)
        print()

        # Turn 2: non-streaming follow-up — the model remembers the haiku
        r2 = await session.prompt("Now explain the haiku you just wrote.")
        print(f"AI: {r2.text}")

        print(f"Total turns: {session.turn_count}")

    await client.close()

asyncio.run(main())
```

```bash
python examples/session_streaming.py
```
