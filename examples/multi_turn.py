"""cursorpipe example: Multi-turn sessions with memory.

Sessions keep conversation history on the server side, so you don't need
to resend previous messages. The LLM remembers everything from earlier turns.

This is useful for building chatbots, step-by-step workflows, or any
conversation where context matters.

Tested with:
  - cursorpipe 0.1.0
  - Cursor Agent CLI v2026.03.25-933d5a6
  - Python 3.14

Prerequisites:
  - Cursor Agent CLI installed (https://cursor.com/docs/cli/installation)
  - Authenticated via `agent login` or CURSORPIPE_API_KEY set

Run:
  python examples/multi_turn.py
"""

import asyncio

from cursorpipe import CursorClient


async def main() -> None:
    client = CursorClient()

    # session() creates a context manager that tracks conversation history
    async with client.session("claude-4.5-sonnet-thinking") as session:

        # Turn 1: give the LLM some information
        print("You: What is 42 * 3?")
        r1 = await session.prompt("What is 42 * 3?")
        print(f"AI:  {r1.text}\n")

        # Turn 2: ask a follow-up — the LLM remembers the previous answer
        print("You: Now double that result.")
        r2 = await session.prompt("Now double that result.")
        print(f"AI:  {r2.text}\n")

        # Turn 3: reference something from turn 1
        print("You: What was the original multiplication I asked about?")
        r3 = await session.prompt("What was the original multiplication I asked about?")
        print(f"AI:  {r3.text}\n")

        print(f"Total turns: {session.turn_count}")

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
