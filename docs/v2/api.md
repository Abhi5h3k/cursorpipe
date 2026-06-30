# API Reference

All endpoints follow the OpenAI API specification where applicable. Unknown OpenAI fields (e.g. `temperature`, `top_p`) are accepted and silently ignored.

---

## GET `/health`

Health check. Always public (no auth required).

```bash
# bash / macOS / Linux / WSL
curl http://localhost:8080/health
```

```powershell
# Windows (PowerShell)
Invoke-RestMethod http://localhost:8080/health
```

**200 OK — bridge connected:**
```json
{"status": "ok", "bridge": "connected"}
```

**503 — bridge unavailable (SDK crashed or not yet started):**
```json
{"status": "degraded", "bridge": "unavailable"}
```

Use this endpoint for Docker/Kubernetes health checks and readiness probes.

---

## GET `/v1/models`

List available models. Returns the configured default model if the SDK model list call fails.

```bash
# bash / macOS / Linux / WSL
curl http://localhost:8080/v1/models
```

```powershell
# Windows (PowerShell)
Invoke-RestMethod http://localhost:8080/v1/models
```

```json
{
  "object": "list",
  "data": [
    {"id": "composer-2.5", "object": "model", "created": 1749220800, "owned_by": "cursor"},
    {"id": "claude-4.5-sonnet-thinking", "object": "model", "created": 1749220800, "owned_by": "cursor"}
  ]
}
```

---

## POST `/v1/chat/completions`

OpenAI-compatible chat completions. Supports streaming and non-streaming, stateless and stateful.

### Request

```json
{
  "model": "composer-2.5",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello!"}
  ],
  "stream": false,
  "cursor_params": {"reasoning": "medium"}
}
```

| Field | Type | Description |
|---|---|---|
| `model` | string | Model ID. Defaults to `CURSORPIPE_MODEL` if omitted. |
| `messages` | array | Required. Array of `{role, content}` objects. |
| `stream` | boolean | `true` for SSE streaming, `false` for a single response. Default: `false`. |
| `cursor_params` | object | Optional. Per-request Cursor SDK model parameters. Keys and values must match the model's `cursor_parameters` from `GET /v1/models`. Takes priority over `CURSORPIPE_THINKING_LEVEL`. |

Any other OpenAI fields (`temperature`, `top_p`, `max_tokens`, etc.) are accepted and ignored.

**`cursor_params` examples by model family:**

| Model family | Example |
|---|---|
| GPT (`gpt-5.5`, `gpt-5.4` …) | `{"reasoning": "medium"}` — values: `none`, `low`, `medium`, `high`, `extra-high` |
| Claude (`claude-opus-4-8` …) | `{"thinking": "true", "effort": "medium"}` — effort: `low`, `medium`, `high`, `xhigh`, `max` |
| Composer (`composer-2.5`) | `{"fast": "true"}` or `{"fast": "false"}` |
| Any model with large context | `{"context": "1m"}` |

### Non-streaming response

```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1749220800,
  "model": "composer-2.5",
  "choices": [{
    "index": 0,
    "message": {"role": "assistant", "content": "Hello! How can I help?"},
    "finish_reason": "stop"
  }],
  "cursor_metadata": {
    "duration_ms": 1240,
    "run_id": "run_abc123",
    "agent_id": "agent_xyz"
  }
}
```

The `cursor_metadata` field is a cursorpipe extension. Standard OpenAI clients will ignore it.

### Streaming response (SSE)

```
data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","model":"composer-2.5","choices":[{"delta":{"role":"assistant"},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","model":"composer-2.5","choices":[{"delta":{"content":"Hello"},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","model":"composer-2.5","choices":[{"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

### Stateful sessions

Add the `X-Cursor-Session-ID` header to opt into a stateful session. The server reuses the same SDK agent so context is preserved across turns.

```bash
# bash / macOS / Linux / WSL

# First turn
curl http://localhost:8080/v1/chat/completions \
  -H "X-Cursor-Session-ID: my-session" \
  -H "Content-Type: application/json" \
  -d '{"model":"composer-2.5","messages":[{"role":"user","content":"My name is Alice."}]}'

# Second turn (agent remembers Alice)
curl http://localhost:8080/v1/chat/completions \
  -H "X-Cursor-Session-ID: my-session" \
  -H "Content-Type: application/json" \
  -d '{"model":"composer-2.5","messages":[{"role":"user","content":"What is my name?"}]}'
```

```powershell
# Windows (PowerShell)

# First turn
Invoke-RestMethod http://localhost:8080/v1/chat/completions `
  -Method Post `
  -ContentType "application/json" `
  -Headers @{"X-Cursor-Session-ID"="my-session"} `
  -Body '{"model":"composer-2.5","messages":[{"role":"user","content":"My name is Alice."}]}'

# Second turn (agent remembers Alice)
Invoke-RestMethod http://localhost:8080/v1/chat/completions `
  -Method Post `
  -ContentType "application/json" `
  -Headers @{"X-Cursor-Session-ID"="my-session"} `
  -Body '{"model":"composer-2.5","messages":[{"role":"user","content":"What is my name?"}]}'
```

The response echoes the `X-Cursor-Session-ID` header. For stateful calls, `cursor_metadata.session_id` is also populated.

---

## GET `/v1/sessions`

List all active stateful sessions.

```bash
# bash / macOS / Linux / WSL
curl http://localhost:8080/v1/sessions
```

```powershell
# Windows (PowerShell)
Invoke-RestMethod http://localhost:8080/v1/sessions
```

```json
{
  "object": "list",
  "data": [
    {
      "id": "my-session",
      "model": "composer-2.5",
      "created_at": "2026-06-06T12:00:00+00:00",
      "last_used_at": "2026-06-06T12:05:00+00:00"
    }
  ]
}
```

---

## GET `/v1/sessions/{id}`

Get info about a specific session.

```bash
# bash / macOS / Linux / WSL
curl http://localhost:8080/v1/sessions/my-session
```

```powershell
# Windows (PowerShell)
Invoke-RestMethod http://localhost:8080/v1/sessions/my-session
```

Returns 404 if the session does not exist or has been evicted.

---

## POST `/v1/sessions`

Explicitly create a new session and return its ID. Useful when you want to pre-create a session before making chat calls.

```bash
# bash / macOS / Linux / WSL
curl -X POST http://localhost:8080/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-5.5","cursor_params":{"reasoning":"medium"}}'
```

```powershell
# Windows (PowerShell)
Invoke-RestMethod http://localhost:8080/v1/sessions `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"model":"gpt-5.5","cursor_params":{"reasoning":"medium"}}'
```

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "model": "composer-2.5",
  "created_at": "2026-06-06T12:00:00+00:00",
  "last_used_at": "2026-06-06T12:00:00+00:00"
}
```

---

## DELETE `/v1/sessions/{id}`

Close and evict a session immediately (regardless of TTL).

```bash
# bash / macOS / Linux / WSL
curl -X DELETE http://localhost:8080/v1/sessions/my-session
```

```powershell
# Windows (PowerShell)
Invoke-RestMethod http://localhost:8080/v1/sessions/my-session -Method Delete
```

```json
{"deleted": true, "id": "my-session"}
```

Returns 404 if the session does not exist.

---

## Request tracing

Every response includes an `X-Request-ID` header. Provide your own to correlate logs:

```bash
# bash / macOS / Linux / WSL
curl http://localhost:8080/v1/chat/completions \
  -H "X-Request-ID: my-trace-abc-123" \
  -H "Content-Type: application/json" \
  -d '{"model":"composer-2.5","messages":[{"role":"user","content":"Hello!"}]}'
```

```powershell
# Windows (PowerShell)
Invoke-RestMethod http://localhost:8080/v1/chat/completions `
  -Method Post `
  -ContentType "application/json" `
  -Headers @{"X-Request-ID"="my-trace-abc-123"} `
  -Body '{"model":"composer-2.5","messages":[{"role":"user","content":"Hello!"}]}'
```

The server echoes it back unchanged. If absent, a UUID is generated.

---

## Error responses

All errors use the OpenAI error format:

```json
{
  "error": {
    "message": "CURSOR_API_KEY is invalid",
    "type": "authentication_error",
    "code": null
  }
}
```

| HTTP status | When |
|---|---|
| 401 | Invalid or missing bearer token; invalid API key |
| 404 | Session not found |
| 409 | Agent is busy (rate limited by SDK) |
| 422 | Request body validation failed |
| 429 | Rate limited by Cursor API |
| 502 | Cursor API unreachable (network / proxy) |
| 503 | SDK bridge unavailable |
| 504 | Request timed out |
