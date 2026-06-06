"""cursorpipe v2 example: Basic stateless completion.

The simplest way to get a response from cursorpipe v2.
Sends a single request and prints the reply.

Prerequisites:
  - cursorpipe v2 server running (python -m cursorpipe_server inside v2/)
  - CURSOR_API_KEY set in .env or environment
  - pip install requests

Run:
  python v2/examples/basic.py
"""

import json

import requests


def main() -> None:
    url = "http://localhost:8080/v1/chat/completions"
    payload = {
        "model": "composer-2.5",
        "messages": [
            {"role": "user", "content": "Explain what an API is in two sentences."}
        ],
    }

    response = requests.post(url, json=payload, timeout=90)
    response.raise_for_status()

    data = response.json()
    content = data["choices"][0]["message"]["content"]
    print("Response:")
    print(content)

    # cursor_metadata contains Cursor-specific details (duration, run_id, etc.)
    meta = data.get("cursor_metadata", {})
    print(f"\n[duration_ms={meta.get('duration_ms', 0)}, run_id={meta.get('run_id')}]")


if __name__ == "__main__":
    main()
