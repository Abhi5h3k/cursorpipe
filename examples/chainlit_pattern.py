"""cursorpipe example: Framework integration pattern (Chainlit / FastAPI).

Shows the recommended pattern for using cursorpipe in a multi-user
framework where session create, use, and destroy happen in different
callback functions.

This is a *standalone simulation* — it does not require Chainlit to be
installed.  It mimics the Chainlit lifecycle to show the integration
pattern.

Key concepts:
  - client.warmup() at app startup (once)
  - client.create_session() on chat start (per user)
  - session.prompt() / session.stream_prompt() on each message
  - session.discard() on chat end

Tested with:
  - cursorpipe 0.1.0
  - Cursor Agent CLI v2026.03.25-933d5a6
  - Python 3.14

Run:
  python examples/chainlit_pattern.py
"""

import asyncio

from cursorpipe import CursorClient

# Simulates Chainlit's cl.user_session per-user storage
user_sessions: dict[str, object] = {}

client = CursorClient()


async def app_startup() -> None:
    """Called once when the app starts (Chainlit startup hook)."""
    await client.warmup(pool_size=5)
    print("[app] Warmup complete — ready to serve users\n")


async def on_chat_start(user_id: str) -> None:
    """Called when a user opens a new chat (Chainlit @on_chat_start)."""
    session = await client.create_session("claude-4.5-sonnet-thinking")
    user_sessions[user_id] = session
    print(f"[{user_id}] Session created: {session.session_id[:12]}...")


async def on_message(user_id: str, message: str) -> None:
    """Called on each user message (Chainlit @on_message)."""
    session = user_sessions[user_id]

    print(f"[{user_id}] You: {message}")
    print(f"[{user_id}] AI:  ", end="")

    async for chunk in session.stream_prompt(message):
        print(chunk, end="", flush=True)
    print("\n")


async def on_chat_end(user_id: str) -> None:
    """Called when user closes chat / refreshes page (Chainlit @on_chat_end)."""
    session = user_sessions.pop(user_id, None)
    if session:
        session.discard()
        print(f"[{user_id}] Session discarded\n")


async def main() -> None:
    await app_startup()

    # Simulate User A opening chat and having a multi-turn conversation
    await on_chat_start("alice")
    await on_message("alice", "What is 42 * 3?")
    await on_message("alice", "Now double that result.")  # server remembers prior turns

    # Simulate User B opening a concurrent chat (fully isolated)
    await on_chat_start("bob")
    await on_message("bob", "Write a haiku about Python.")

    # Users leave
    await on_chat_end("alice")
    await on_chat_end("bob")

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
