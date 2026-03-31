"""cursorpipe example: Authentication with an API key.

Shows how to use a Cursor API key instead of `agent login`.
This is the recommended approach for scripts, CI pipelines, and servers
where interactive browser login isn't possible.

You can get an API key from: https://cursor.com/dashboard/cloud-agents

Tested with:
  - cursorpipe 0.1.0
  - Cursor Agent CLI v2026.03.25-933d5a6
  - Python 3.14

Prerequisites:
  - Cursor Agent CLI installed (https://cursor.com/docs/cli/installation)
  - CURSORPIPE_API_KEY set in .env or environment

Run:
  # Option 1: set env var directly
  CURSORPIPE_API_KEY=crsr_your_key_here python examples/api_key_auth.py

  # Option 2: use a .env file (pydantic-settings loads it automatically)
  echo "CURSORPIPE_API_KEY=crsr_your_key_here" > .env
  python examples/api_key_auth.py

  # Option 3: use the standard CURSOR_API_KEY env var
  CURSOR_API_KEY=crsr_your_key_here python examples/api_key_auth.py
"""

import asyncio
import os

from cursorpipe import CursorClient, CursorPipeConfig


async def main() -> None:
    # Method 1: Let pydantic-settings auto-load from env / .env
    # Just set CURSORPIPE_API_KEY or CURSOR_API_KEY and create the client.
    client = CursorClient()

    # Method 2: Pass the key explicitly in code (useful for testing)
    # api_key = os.getenv("CURSOR_API_KEY", "")
    # config = CursorPipeConfig(api_key=api_key)
    # client = CursorClient(config)

    # Verify it works
    response = await client.generate(
        model="claude-4.5-sonnet-thinking",
        prompt="Reply with exactly: AUTH_OK",
        system="Reply with exactly what is asked, nothing else.",
    )

    if "AUTH_OK" in response:
        print("Authentication successful! API key is working.")
    else:
        print(f"Unexpected response: {response}")

    await client.close()


if __name__ == "__main__":
    if not os.getenv("CURSORPIPE_API_KEY") and not os.getenv("CURSOR_API_KEY"):
        print(
            "No API key found.\n"
            "Set CURSORPIPE_API_KEY or CURSOR_API_KEY in your environment,\n"
            "or create a .env file with CURSORPIPE_API_KEY=crsr_your_key_here\n\n"
            "Get your key at: https://cursor.com/dashboard/cloud-agents"
        )
    else:
        asyncio.run(main())
