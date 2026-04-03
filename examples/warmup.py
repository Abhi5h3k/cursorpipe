"""cursorpipe example: Pre-warming for zero cold-start latency.

Demonstrates ``client.warmup()`` which pre-starts the ACP process and
pre-creates session slots so the first real request is as fast as
subsequent ones.

Without warmup:
  First request  ~14s  (process spawn + session creation + LLM)
  Second request  ~5s  (LLM only)

With warmup:
  warmup()        ~8s  (done once at startup)
  First request   ~5s  (LLM only — same as subsequent)

Tested with:
  - cursorpipe 0.1.0
  - Cursor Agent CLI v2026.03.25-933d5a6
  - Python 3.14

Run:
  python examples/warmup.py
"""

import asyncio
import time

from cursorpipe import CursorClient


async def main() -> None:
    client = CursorClient()

    # Pre-warm: spawn the ACP process and create 3 ready sessions
    print("Warming up...")
    t0 = time.monotonic()
    await client.warmup(pool_size=3)
    print(f"Warmup done in {time.monotonic() - t0:.1f}s\n")

    # First request — no cold start, goes straight to LLM
    print("Sending first request...")
    t1 = time.monotonic()
    response = await client.generate(
        model="claude-4.5-sonnet-thinking",
        prompt="Reply with exactly: WARMUP_OK",
    )
    print(f"Response: {response.strip()}")
    print(f"First request took {time.monotonic() - t1:.1f}s (should be ~5s, not ~14s)\n")

    # Second request — same speed
    t2 = time.monotonic()
    response2 = await client.generate(
        model="claude-4.5-sonnet-thinking",
        prompt="Reply with exactly: SECOND_OK",
    )
    print(f"Response: {response2.strip()}")
    print(f"Second request took {time.monotonic() - t2:.1f}s")

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
