"""cursorpipe example: Streaming responses.

Instead of waiting for the full response, stream chunks as they arrive.
Each chunk is printed immediately, so you see the text appear word by word
— just like a chatbot typing in real time.

Tested with:
  - cursorpipe 0.1.0
  - Cursor Agent CLI v2026.03.25-933d5a6
  - Python 3.14

Prerequisites:
  - Cursor Agent CLI installed (https://cursor.com/docs/cli/installation)
  - Authenticated via `agent login` or CURSORPIPE_API_KEY set

Run:
  python examples/streaming.py
"""

import asyncio

from cursorpipe import CursorClient


async def main() -> None:
    client = CursorClient()

    print("Streaming response:\n")

    # stream() returns an async iterator — use `async for` to get chunks
    async for chunk in client.stream(
        model="claude-4.5-sonnet-thinking",
        prompt="Write a short poem about coding at midnight.",
    ):
        # Each chunk is a small piece of text; print without newline
        print(chunk, end="", flush=True)

    # Print a final newline after the stream ends
    print()

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
