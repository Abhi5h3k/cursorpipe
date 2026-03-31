"""cursorpipe example: Basic completion.

The simplest way to get a response from an LLM through cursorpipe.
Creates a client, sends one prompt, prints the response, and exits.

Tested with:
  - cursorpipe 0.1.0
  - Cursor Agent CLI v2026.03.25-933d5a6
  - Python 3.14

Prerequisites:
  - Cursor Agent CLI installed (https://cursor.com/docs/cli/installation)
  - Authenticated via `agent login` or CURSORPIPE_API_KEY set

Run:
  python examples/basic.py
"""

import asyncio

from cursorpipe import CursorClient


async def main() -> None:
    # Create a client — picks up auth from `agent login` or env vars automatically
    client = CursorClient()

    # Send a prompt and get the full response as a string
    response = await client.generate(
        model="claude-4.5-sonnet-thinking",
        prompt="Explain what an API is in two sentences, as if to a 10-year-old.",
    )

    print("Response:")
    print(response)

    # Always close the client when done to shut down the agent process
    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
