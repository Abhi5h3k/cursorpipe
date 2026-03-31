"""cursorpipe example: Streaming within a multi-turn session.

Combines two features — streaming and sessions — so you see chunks arrive
in real time while the server keeps full conversation history.  The second
turn proves memory works even after a streamed response.

Tested with:
  - cursorpipe 0.1.0
  - Cursor Agent CLI v2026.03.25-933d5a6
  - Python 3.14

Prerequisites:
  - Cursor Agent CLI installed (https://cursor.com/docs/cli/installation)
  - Authenticated via `agent login` or CURSORPIPE_API_KEY set

Run:
  python examples/session_streaming.py
"""

import asyncio

from cursorpipe import CursorClient


async def main() -> None:
    client = CursorClient()

    async with client.session("claude-4.5-sonnet-thinking") as session:
        # Turn 1: stream the response chunk-by-chunk
        print("You: Write a haiku about async Python.\n")
        print("AI:  ", end="")
        async for chunk in session.stream_prompt(
            "Write a haiku about async Python programming."
        ):
            print(chunk, end="", flush=True)
        print("\n")

        # Turn 2: non-streaming follow-up — the model remembers the haiku
        print("You: Now explain the haiku you just wrote.\n")
        r2 = await session.prompt("Now explain the haiku you just wrote.")
        print(f"AI:  {r2.text}\n")

        print(f"Total turns: {session.turn_count}")

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
