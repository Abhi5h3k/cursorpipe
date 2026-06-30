"""cursorpipe v2 example: Thinking / reasoning content.

Demonstrates two ways to request model reasoning:

1. Per-request cursor_params (new in v2.0.8) — pass reasoning/thinking/effort
   parameters directly in the request body via extra_body. Works for all models.
   This takes priority over the global CURSORPIPE_THINKING_LEVEL setting.

2. Global server setting — set CURSORPIPE_THINKING_LEVEL=high before starting
   the server. Applies to all requests that don't supply cursor_params.

How cursor_params work
----------------------
Pass cursor_params (a dict of param_id → value) in the request body.
The server maps these to Cursor SDK ModelSelection.params before sending to the
model. Valid IDs and values per model are listed in GET /v1/models →
cursor_parameters.

Examples by model family:
  GPT  (gpt-5.5, gpt-5.4 …):  {"reasoning": "medium"}   # none|low|medium|high|extra-high
  Claude (claude-opus-4-8 …): {"thinking": "true", "effort": "medium"}  # effort: low|medium|high|xhigh|max
  Composer (composer-2.5):    {"fast": "true"}

The old global approach:
    CURSORPIPE_THINKING_LEVEL=high   # or "low"

Prerequisites:
  - cursorpipe v2 server running (with or without CURSORPIPE_THINKING_LEVEL)
  - CURSOR_API_KEY set in .env or environment
  - pip install requests

Run:
  python -m cursorpipe_server &
  python v2/examples/thinking.py
"""

import json

import requests

BASE_URL = "http://localhost:8080"


# ── Step 1: discover which models support reasoning/thinking ──────────────────


def get_reasoning_models() -> dict[str, list[dict]]:
    """Return models grouped by the reasoning-style parameter they support.

    Returns a dict with keys 'reasoning' (GPT-style) and 'thinking' (Claude-style).
    """
    resp = requests.get(f"{BASE_URL}/v1/models", timeout=15)
    resp.raise_for_status()
    models = resp.json()["data"]
    result: dict[str, list[dict]] = {"reasoning": [], "thinking": []}
    for m in models:
        for param in m.get("cursor_parameters", []):
            if param["id"] in ("reasoning", "thinking"):
                result[param["id"]].append(
                    {
                        "id": m["id"],
                        "values": [v["value"] for v in param.get("values", [])],
                    }
                )
    return result


# ── Step 2: per-request cursor_params (new in v2.0.8) ────────────────────────


def per_request_reasoning(model: str, reasoning_value: str) -> None:
    """Use cursor_params to pass reasoning=<value> for a GPT-style model."""
    print(f"\n=== Per-request reasoning ({model}, reasoning={reasoning_value}) ===\n")

    resp = requests.post(
        f"{BASE_URL}/v1/chat/completions",
        json={
            "model": model,
            "messages": [{"role": "user", "content": "What is 17 × 23? Show your work."}],
            "cursor_params": {"reasoning": reasoning_value},
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


def per_request_thinking(model: str, effort: str = "medium") -> None:
    """Use cursor_params to pass thinking=true + effort=<value> for a Claude model."""
    print(f"\n=== Per-request thinking ({model}, effort={effort}) ===\n")

    resp = requests.post(
        f"{BASE_URL}/v1/chat/completions",
        json={
            "model": model,
            "messages": [{"role": "user", "content": "What is 17 × 23? Show your work."}],
            "cursor_params": {"thinking": "true", "effort": effort},
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


# ── Step 3: streaming with cursor_params ──────────────────────────────────────


def streaming_with_cursor_params(model: str, cursor_params: dict) -> None:
    """Stream a completion with per-request cursor_params."""
    print(f"\n=== Streaming with cursor_params {cursor_params} ({model}) ===\n")

    with requests.post(
        f"{BASE_URL}/v1/chat/completions",
        json={
            "model": model,
            "stream": True,
            "messages": [
                {"role": "user", "content": "Explain why the sky is blue in two sentences."}
            ],
            "cursor_params": cursor_params,
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

    print()


# ── Step 4: global server-level thinking (old approach, still works) ──────────


def non_streaming_thinking(model: str) -> None:
    """Show thinking from the global CURSORPIPE_THINKING_LEVEL setting."""
    print(f"\n=== Global thinking level ({model}) ===\n")

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
            "or CURSORPIPE_THINKING_LEVEL is 'off' and no cursor_params were passed."
        )


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    print("=== cursorpipe v2 — Thinking / Reasoning Example ===")
    print(
        "\nDiscovers models by parameter type and demonstrates both per-request "
        "cursor_params and the global CURSORPIPE_THINKING_LEVEL approach.\n"
    )

    models = get_reasoning_models()

    # GPT-style: reasoning=low|medium|high|extra-high
    if models["reasoning"]:
        m = models["reasoning"][0]
        print(f"GPT-style reasoning model: {m['id']}  (values: {', '.join(m['values'])})")
        per_request_reasoning(m["id"], "medium")
        streaming_with_cursor_params(m["id"], {"reasoning": "low"})
    else:
        print("No GPT-style reasoning models found on your account.")

    # Claude-style: thinking=true + effort=low|medium|high|xhigh|max
    if models["thinking"]:
        m = models["thinking"][0]
        print(f"\nClaude-style thinking model: {m['id']}  (values: {', '.join(m['values'])})")
        per_request_thinking(m["id"], effort="medium")
        streaming_with_cursor_params(m["id"], {"thinking": "true", "effort": "low"})
    else:
        print("\nNo Claude-style thinking models found — falling back to global setting demo.")
        non_streaming_thinking("composer-2.5")


if __name__ == "__main__":
    main()
