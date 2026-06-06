# Thinking / Reasoning Content

Some Cursor models (e.g. `claude-4.5-sonnet-thinking`) expose their internal
reasoning process before producing a final answer. cursorpipe v2 can surface
this as `reasoning_content` — the same pattern used by DeepSeek R1 and OpenAI o1.

**Disabled by default.** When disabled, behaviour is identical to a standard
chat completion — no performance impact, no extra data.

---

## Enable

Set the environment variable before starting the server:

```bash
CURSORPIPE_EXPOSE_THINKING=true python -m cursorpipe_server
```

Or in `.env`:

```bash
CURSORPIPE_EXPOSE_THINKING=true
```

---

## Streaming

When thinking is enabled, the server emits thinking chunks **before** the regular
content chunks. Each thinking chunk has `delta.reasoning_content` set:

```
data: {"choices":[{"delta":{"reasoning_content":"The user is asking about France..."},"finish_reason":null}]}

data: {"choices":[{"delta":{"content":"Paris."},"finish_reason":null}]}

data: [DONE]
```

### Python example

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8080/v1", api_key="not-needed")

stream = client.chat.completions.create(
    model="claude-4.5-sonnet-thinking",
    stream=True,
    messages=[{"role": "user", "content": "What is 17 × 23?"}],
)

for chunk in stream:
    delta = chunk.choices[0].delta
    if hasattr(delta, "reasoning_content") and delta.reasoning_content:
        print(f"[thinking] {delta.reasoning_content}", end="", flush=True)
    if delta.content:
        print(delta.content, end="", flush=True)
```

---

## Non-streaming

Thinking content appears in `cursor_metadata` rather than in the `message` field,
keeping the standard `choices[0].message.content` clean:

```json
{
  "choices": [{
    "message": {"role": "assistant", "content": "391"},
    "finish_reason": "stop"
  }],
  "cursor_metadata": {
    "thinking": "17 × 23 = 17 × 20 + 17 × 3 = 340 + 51 = 391",
    "thinking_duration_ms": 1240,
    "duration_ms": 2100
  }
}
```

### Python example

```python
response = client.chat.completions.create(
    model="claude-4.5-sonnet-thinking",
    messages=[{"role": "user", "content": "What is 17 × 23?"}],
)

# Standard content
print(response.choices[0].message.content)

# Thinking (in cursor_metadata — OpenAI SDK ignores unknown fields)
import json
raw = json.loads(response.model_dump_json())
thinking = raw.get("cursor_metadata", {}).get("thinking")
if thinking:
    print(f"[thinking] {thinking}")
```

---

## Compatibility

- **Open WebUI** — renders `reasoning_content` chunks natively when it detects the DeepSeek pattern
- **LangChain / LiteLLM** — thinking chunks are ignored (no `content` field), standard content works normally
- **curl** — visible as raw SSE `data:` lines with `reasoning_content`

---

## Notes

- Only models that support thinking produce `SDKThinkingMessage` events; for other models the feature has zero overhead.
- When `CURSORPIPE_EXPOSE_THINKING=false` (the default), `run.messages()` is still used internally — the thinking events are simply discarded.
- Non-streaming responses always include thinking in `cursor_metadata`, never in `choices[0].message.reasoning_content`, to keep the response fully OpenAI-compatible.
