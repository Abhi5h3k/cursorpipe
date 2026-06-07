# Thinking / Reasoning Content

Some Cursor models support internal reasoning — they "think" before producing
a final answer. cursorpipe v2 can request thinking from the SDK and surface
the reasoning content in the HTTP response, using the same pattern as
DeepSeek R1 and OpenAI o1.

**Disabled by default.** When `CURSORPIPE_THINKING_LEVEL=off` (the default),
behaviour is identical to a standard chat completion — no performance impact,
no extra data.

---

## How thinking works

Thinking is a **model parameter**, not a special model name. The Cursor SDK
accepts it as:

```python
ModelSelection(
    id="composer-2.5",
    params=[ModelParameterValue(id="thinking", value="high")]
)
```

cursorpipe v2 passes this parameter automatically based on your
`CURSORPIPE_THINKING_LEVEL` setting. You do **not** need to use a specially-named
model — any model that supports the `thinking` parameter will think.

---

## Discover which models support thinking

Call `/v1/models` and look at `cursor_parameters`:

```bash
# bash / macOS / Linux / WSL
curl http://localhost:8080/v1/models
```

```powershell
# Windows (PowerShell)
(Invoke-RestMethod http://localhost:8080/v1/models).data |
  Where-Object { $_.cursor_parameters } |
  Select-Object id, cursor_parameters
```

A model that supports thinking will include an entry like:

```json
{
  "id": "composer-2.5",
  "cursor_parameters": [
    {
      "id": "thinking",
      "display_name": "Thinking",
      "values": [
        {"value": "low",  "display_name": "Low"},
        {"value": "high", "display_name": "High"}
      ]
    }
  ]
}
```

---

## Enable

Set `CURSORPIPE_THINKING_LEVEL` before starting the server:

```bash
# bash / macOS / Linux / WSL
export CURSORPIPE_THINKING_LEVEL=high
python -m cursorpipe_server
```

```powershell
# Windows (PowerShell)
$env:CURSORPIPE_THINKING_LEVEL = "high"
python -m cursorpipe_server
```

Or in `.env`:

```bash
CURSORPIPE_THINKING_LEVEL=high   # "off" | "low" | "high"
```

| Value | Effect |
|---|---|
| `off` | Do not request thinking; discard any thinking tokens (default) |
| `low` | Request `thinking=low` from the SDK; surface in response |
| `high` | Request `thinking=high` from the SDK; surface in response |

> **Backward compatibility:** `CURSORPIPE_EXPOSE_THINKING=true` is still
> accepted and maps to `thinking_level=high`. Prefer `CURSORPIPE_THINKING_LEVEL`
> in new configurations.

---

## Streaming

When thinking is enabled, the server emits thinking chunks **before** the
regular content chunks. Each thinking chunk has `delta.reasoning_content` set:

```
data: {"choices":[{"delta":{"reasoning_content":"17 × 20 = 340, 17 × 3 = 51..."},"finish_reason":null}]}

data: {"choices":[{"delta":{"content":"391"},"finish_reason":null}]}

data: [DONE]
```

### curl example

```bash
# bash / macOS / Linux / WSL
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -N \
  -d '{"model":"composer-2.5","stream":true,"messages":[{"role":"user","content":"What is 17 x 23?"}]}'
```

```powershell
# Windows (PowerShell) — use curl.exe for true streaming
curl.exe http://localhost:8080/v1/chat/completions `
  -H "Content-Type: application/json" `
  -N `
  -d '{\"model\":\"composer-2.5\",\"stream\":true,\"messages\":[{\"role\":\"user\",\"content\":\"What is 17 x 23?\"}]}'
```

### Python (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8080/v1", api_key="not-needed")

stream = client.chat.completions.create(
    model="composer-2.5",
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

Thinking content appears in `cursor_metadata` rather than in the `message`
field, keeping `choices[0].message.content` clean and fully OpenAI-compatible:

```json
{
  "choices": [{
    "message": {"role": "assistant", "content": "391"},
    "finish_reason": "stop"
  }],
  "cursor_metadata": {
    "thinking": "17 × 20 = 340, 17 × 3 = 51, total = 391",
    "thinking_duration_ms": 1240,
    "duration_ms": 2100
  }
}
```

### Python (OpenAI SDK)

```python
import json
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8080/v1", api_key="not-needed")

response = client.chat.completions.create(
    model="composer-2.5",
    messages=[{"role": "user", "content": "What is 17 × 23?"}],
)

# Standard content
print(response.choices[0].message.content)

# Thinking lives in cursor_metadata (OpenAI SDK ignores unknown fields)
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

- Only models that expose `thinking` in `cursor_parameters` produce `SDKThinkingMessage` events; for other models the setting has zero overhead.
- When `CURSORPIPE_THINKING_LEVEL=off` (the default), `run.messages()` is still used internally — thinking events are simply discarded.
- Non-streaming responses always put thinking in `cursor_metadata`, never in `choices[0].message.reasoning_content`, to keep the response fully OpenAI-compatible.
- Thinking is a server-level setting — all requests use the same level. Per-request thinking level is not supported.
