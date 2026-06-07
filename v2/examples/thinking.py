"""cursorpipe v2 example: Thinking / reasoning content.

Demonstrates how to enable and consume thinking output from models that
support it.

How thinking works in cursorpipe v2
------------------------------------
Thinking is requested from the Cursor SDK via a model parameter:

    ModelSelection(id="composer-2.5", params=[ModelParameterValue(id="thinking", value="high")])

cursorpipe v2 handles this automatically when you set:

    CURSORPIPE_THINKING_LEVEL=high   # or "low"

in your .env file (or as an environment variable) before starting the server.
The model does NOT need a special name — thinking is a parameter, not a separate
model. Use /v1/models to discover which models on your account support it.

Prerequisites:
  - cursorpipe v2 server running with CURSORPIPE_THINKING_LEVEL=high
  - CURSOR_API_KEY set in .env or environment
  - pip install requests

Run:
  CURSORPIPE_THINKING_LEVEL=high python -m cursorpipe_server &
  python v2/examples/thinking.py
"""

import json

import requests

BASE_URL = "http://localhost:8080"


# ── Step 1: discover which models support thinking ────────────────────────────


def get_thinking_models() -> list[dict]:
    """Return models whose cursor_parameters include thinking=low|high."""
    resp = requests.get(f"{BASE_URL}/v1/models", timeout=15)
    resp.raise_for_status()
    models = resp.json()["data"]
    thinking_models = []
    for m in models:
        for param in m.get("cursor_parameters", []):
            if param["id"] == "thinking":
                thinking_models.append(
                    {
                        "id": m["id"],
                        "thinking_values": [v["value"] for v in param.get("values", [])],
                    }
                )
                break
    return thinking_models


# ── Step 2: non-streaming completion with thinking ────────────────────────────


def non_streaming_thinking(model: str) -> None:
    """Show thinking in cursor_metadata for a non-streaming request."""
    print(f"\n=== Non-streaming thinking ({model}) ===\n")

    resp = requests.post(
        f"{BASE_URL}/v1/chat/completions",
        json={
            "model": model,
            "messages": [{"role": "user", "content": "What is 17 × 23? Show your work."}],
        },
        timeout=120,
    )
    resp.raise_for_status()
    body = resp.json()

    print("Answer:", body["choices"][0]["message"]["content"])

    meta = body.get("cursor_metadata", {})
    if meta.get("thinking"):
        print(f"\n[thinking] ({meta.get('thinking_duration_ms', 0)} ms)")
        print(meta["thinking"])
    else:
        print(
            "\n[no thinking] — either the model does not support it, "
            "or CURSORPIPE_THINKING_LEVEL is 'off'."
        )


# ── Step 3: streaming completion with thinking ────────────────────────────────


def streaming_thinking(model: str) -> None:
    """Show thinking chunks arriving before content chunks in SSE stream."""
    print(f"\n=== Streaming thinking ({model}) ===\n")

    with requests.post(
        f"{BASE_URL}/v1/chat/completions",
        json={
            "model": model,
            "stream": True,
            "messages": [
                {"role": "user", "content": "Explain why the sky is blue in two sentences."}
            ],
        },
        stream=True,
        timeout=120,
    ) as resp:
        resp.raise_for_status()
        for raw_line in resp.iter_lines():
            if not raw_line:
                continue
            line = raw_line.decode() if isinstance(raw_line, bytes) else raw_line
            if not line.startswith("data:"):
                continue
            payload = line.removeprefix("data:").strip()
            if payload == "[DONE]":
                break
            try:
                chunk = json.loads(payload)
                delta = chunk["choices"][0]["delta"]
                if delta.get("reasoning_content"):
                    print(f"[thinking] {delta['reasoning_content']}", end="", flush=True)
                elif delta.get("content"):
                    print(delta["content"], end="", flush=True)
            except (json.JSONDecodeError, KeyError):
                pass

    print()  # newline after stream


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    print("=== cursorpipe v2 — Thinking / Reasoning Example ===")
    print(
        "\nNote: set CURSORPIPE_THINKING_LEVEL=high (or low) before starting the server.\n"
    )

    # Discover thinking-capable models
    thinking_models = get_thinking_models()
    if thinking_models:
        print("Models with thinking support on your account:")
        for m in thinking_models:
            print(f"  {m['id']}  (levels: {', '.join(m['thinking_values'])})")
        model = thinking_models[0]["id"]
    else:
        print(
            "No models with thinking parameters found — falling back to composer-2.5.\n"
            "cursor_parameters may be empty if the server is running without an API key."
        )
        model = "composer-2.5"

    non_streaming_thinking(model)
    streaming_thinking(model)


if __name__ == "__main__":
    main()
