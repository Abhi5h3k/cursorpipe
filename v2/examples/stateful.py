"""cursorpipe v2 example: Multi-turn stateful session.

Demonstrates the X-Cursor-Session-ID header for persistent conversations.
The server reuses the same SDK agent across turns so context is remembered.

Prerequisites:
  - cursorpipe v2 server running (python -m cursorpipe_server inside v2/)
  - CURSOR_API_KEY set in .env or environment
  - pip install requests

Run:
  python v2/examples/stateful.py
"""

import requests

BASE_URL = "http://localhost:8080"
SESSION_ID = "example-stateful-session"


def chat(message: str) -> str:
    """Send a message in the stateful session and return the reply."""
    response = requests.post(
        f"{BASE_URL}/v1/chat/completions",
        headers={"X-Cursor-Session-ID": SESSION_ID},
        json={
            "model": "composer-2.5",
            "messages": [{"role": "user", "content": message}],
        },
        timeout=90,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def main() -> None:
    print("=== Multi-turn stateful session ===\n")

    # Turn 1: establish context
    r1 = chat("My name is Alice. Remember that.")
    print(f"Turn 1 → {r1}\n")

    # Turn 2: verify context is retained by the agent
    r2 = chat("What is my name?")
    print(f"Turn 2 → {r2}\n")

    # Clean up the session
    del_resp = requests.delete(f"{BASE_URL}/v1/sessions/{SESSION_ID}", timeout=10)
    if del_resp.status_code == 200:
        print("Session deleted.")
    else:
        print(f"Session delete returned {del_resp.status_code}.")


if __name__ == "__main__":
    main()
