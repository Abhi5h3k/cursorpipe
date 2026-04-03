# Getting Started

## Prerequisites

### 1. Cursor Agent CLI

Install the Cursor CLI agent ([official docs](https://cursor.com/docs/cli/installation)):

=== "macOS / Linux / WSL"

    ```bash
    curl https://cursor.com/install -fsS | bash
    ```

=== "Windows (PowerShell)"

    ```powershell
    irm 'https://cursor.com/install?win32=true' | iex
    ```

Verify it's installed:

```bash
agent --version
```

### 2. Authentication

Pick one:

=== "Interactive login (local dev)"

    ```bash
    agent login
    ```

    Opens a browser, authenticates with your Cursor account, and stores credentials locally.

=== "API key (scripts / CI)"

    Get your key at [cursor.com/dashboard/cloud-agents](https://cursor.com/dashboard/cloud-agents), then:

    ```bash
    # As an environment variable
    export CURSORPIPE_API_KEY=crsr_your_key_here

    # Or in a .env file (pydantic-settings loads it automatically)
    echo "CURSORPIPE_API_KEY=crsr_your_key_here" > .env
    ```

    !!! note
        Use `CURSORPIPE_API_KEY` in `.env` files (pydantic-settings prefix).
        As an OS environment variable, both `CURSORPIPE_API_KEY` and `CURSOR_API_KEY` work.

## Installation

=== "pip"

    ```bash
    pip install git+https://github.com/Abhi5h3k/cursorpipe.git
    ```

=== "uv"

    ```bash
    uv pip install git+https://github.com/Abhi5h3k/cursorpipe.git
    ```

=== "From source"

    ```bash
    git clone https://github.com/Abhi5h3k/cursorpipe.git
    cd cursorpipe
    pip install .
    ```

## Your first prompt

Create a file called `hello.py`:

```python
import asyncio
from cursorpipe import CursorClient

async def main():
    client = CursorClient()

    response = await client.generate(
        model="claude-4.5-sonnet-thinking",
        prompt="Say hello in a creative way!",
    )
    print(response)

    await client.close()

asyncio.run(main())
```

Run it:

```bash
python hello.py
```

## Speed up with warmup (recommended)

The first request can take ~14s due to process startup and session creation. Add `warmup()` at startup to move that cost upfront:

```python
async def main():
    client = CursorClient()
    await client.warmup(pool_size=3)  # pre-start process + pre-create sessions

    # First request is now as fast as subsequent ones (~5s)
    response = await client.generate(
        model="claude-4.5-sonnet-thinking",
        prompt="Say hello in a creative way!",
    )
    print(response)

    await client.close()
```

## Optional: faster JSON parsing

Install the `fast` extra for ~4.6x faster JSON serialization (uses Rust-backed `orjson`):

```bash
pip install cursorpipe[fast]
```

That's it! Check out the [Examples](examples.md) page for streaming, sessions, framework integration, and more.
