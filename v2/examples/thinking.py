"""cursorpipe v2 example: Thinking / reasoning content.

When CURSORPIPE_EXPOSE_THINKING=true, the server exposes the model's
internal reasoning as:
  - Streaming: delta.reasoning_content chunks (before delta.content)
  - Non-streaming: cursor_metadata.thinking field

This matches the pattern used by DeepSeek R1 and OpenAI o1 clients.

Prerequisites:
  - cursorpipe v2 server running with CURSORPIPE_EXPOSE_THINKING=true
  - A model that supports thinking (e.g. claude-4.5-sonnet-thinking)
  - CURSOR_API_KEY set in .env or environment
  - pip install requests

Run:
  CURSORPIPE_EXPOSE_THINKING=true python -m cursorpipe_server &
  python v2/examples/thinking.py
"""

import json

import requests

BASE_URL = "http://localhost:8080"
MODEL = "claude-4.5-sonnet-thinking"


def non_streaming_with_thinking() -> None:
    print("=== Non-streaming with thinking ===\n")
    response = requests.post(
        f"{BASE_URL}/v1/chat/completions",
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": "What is 17 * 23? Show your work."}],
        },
        timeout=90,
    )
    response.raise_for_status()
    data = response.json()

    meta = data.get("cursor_metadata", {})
    if meta.get("thinking"):
        print(f"[Thinking] {meta['thinking'][:300]}...\n")
        print(f"[Thinking duration: {meta.get('thinking_duration_ms', 0)}ms]\n")

    content = data["choices"][0]["message"]["content"]
    print(f"[Answer] {content}\n")


def streaming_with_thinking() -> None:
    print("=== Streaming with thinking ===\n")
    with requests.post(
        f"{BASE_URL}/v1/chat/completions",
        json={
            "model": MODEL,
            "stream": True,
            "messages": [{"role": "user", "content": "What is 17 * 23?"}],
        },
        stream=True,
        timeout=90,
    ) as response:
        response.raise_for_status()
        in_thinking = False
        for line in response.iter_lines():
            if not line:
                continue
            text = line.decode("utf-8") if isinstance(line, bytes) else line
            if not text.startswith("data:"):
                continue
            data_str = text.removeprefix("data:").strip()
            if data_str == "[DONE]":
                print()
                break
            try:
                chunk = json.loads(data_str)
                delta = chunk["choices"][0]["delta"]
                if delta.get("reasoning_content"):
                    if not in_thinking:
                        print("[Thinking] ", end="", flush=True)
                        in_thinking = True
                    print(delta["reasoning_content"], end="", flush=True)
                if delta.get("content"):
                    if in_thinking:
                        print("\n[Answer] ", end="", flush=True)
                        in_thinking = False
                    print(delta["content"], end="", flush=True)
            except json.JSONDecodeError:
                pass


if __name__ == "__main__":
    non_streaming_with_thinking()
    streaming_with_thinking()
