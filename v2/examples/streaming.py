"""cursorpipe v2 example: Streaming SSE completion.

Streams the model's response token by token, printing each chunk as it
arrives. Uses the standard SSE (Server-Sent Events) format.

Prerequisites:
  - cursorpipe v2 server running (python -m cursorpipe_server inside v2/)
  - CURSOR_API_KEY set in .env or environment
  - pip install requests

Run:
  python v2/examples/streaming.py
"""

import json

import requests


def main() -> None:
    url = "http://localhost:8080/v1/chat/completions"
    payload = {
        "model": "composer-2.5",
        "stream": True,
        "messages": [
            {"role": "user", "content": "Count slowly from 1 to 5, one number per line."}
        ],
    }

    print("Streaming response:")
    with requests.post(url, json=payload, stream=True, timeout=90) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line:
                continue
            text = line.decode("utf-8") if isinstance(line, bytes) else line
            if not text.startswith("data:"):
                continue
            data_str = text.removeprefix("data:").strip()
            if data_str == "[DONE]":
                print()  # newline after stream ends
                break
            try:
                chunk = json.loads(data_str)
                delta = chunk["choices"][0]["delta"]
                # reasoning_content arrives before content when EXPOSE_THINKING=true
                if "reasoning_content" in delta and delta["reasoning_content"]:
                    print(f"[thinking] {delta['reasoning_content']}", end="", flush=True)
                if "content" in delta and delta["content"]:
                    print(delta["content"], end="", flush=True)
            except json.JSONDecodeError:
                pass


if __name__ == "__main__":
    main()
