"""cursorpipe example: Per-call model selection.

Shows how to route different tasks to different models within a single
client.  This is useful when you want a fast/cheap model for simple tasks
(classification, extraction) and a powerful model for complex tasks
(code generation, analysis).

Tested with:
  - cursorpipe 0.1.0
  - Cursor Agent CLI v2026.03.25-933d5a6
  - Python 3.14

Prerequisites:
  - Cursor Agent CLI installed (https://cursor.com/docs/cli/installation)
  - Authenticated via `agent login` or CURSORPIPE_API_KEY set

Run:
  python examples/model_switching.py
"""

import asyncio

from cursorpipe import CursorClient


async def main() -> None:
    client = CursorClient()

    # Task 1: Use a fast model for classification
    print("Step 1 — Classify the query (fast model):")
    intent = await client.generate(
        model="gpt-5.4-mini-medium",
        prompt="Classify this query: 'show top 10 users by revenue'",
        system="Reply with exactly one of: SQL_QUERY, SCHEMA_QUESTION, GREETING",
    )
    print(f"  Intent: {intent.strip()}\n")

    # Task 2: Use a powerful model for the actual work
    print("Step 2 — Generate SQL (powerful model):")
    sql = await client.generate(
        model="claude-4.5-sonnet-thinking",
        prompt="Generate a PostgreSQL query for: top 10 users by revenue in 2026",
        system="You are a PostgreSQL expert. Reply with only the SQL query.",
    )
    print(f"  SQL:\n{sql.strip()}\n")

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
