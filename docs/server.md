# HTTP Server

cursorpipe-server exposes an **OpenAI-compatible HTTP API** backed by the Cursor Agent CLI. Any tool, SDK, or language that speaks the OpenAI protocol works out of the box — no code changes needed.

---

## Installation

=== "pip"

    ```bash
    pip install "cursorpipe[server] @ git+https://github.com/Abhi5h3k/cursorpipe.git"
    ```

=== "From source"

    ```bash
    git clone https://github.com/Abhi5h3k/cursorpipe.git
    cd cursorpipe
    pip install ".[server]"
    ```

!!! note
    `pip install cursorpipe` (without `[server]`) does **not** install FastAPI or Uvicorn. The server dependencies are fully optional.

---

## Starting the server

```bash
export CURSOR_API_KEY=crsr_your_key_here
cursorpipe-server
```

Or with `python -m`:

```bash
python -m cursorpipe_server
```

The server starts on `http://0.0.0.0:8080` by default.

---

## Configuration

All settings are loaded from environment variables (prefix `CURSORPIPE_`) or a `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `CURSORPIPE_HOST` | `0.0.0.0` | Bind address |
| `CURSORPIPE_PORT` | `8080` | Bind port |
| `CURSORPIPE_POOL_SIZE` | `5` | ACP sessions to pre-create at startup |
| `CURSORPIPE_BEARER_TOKEN` | `""` | When set, all requests (except `/health`) must include `Authorization: Bearer <token>` |
| `CURSORPIPE_API_KEY` | `""` | Cursor API key passed to the agent CLI |

All [core configuration](getting-started.md) variables (`CURSORPIPE_STRATEGY`, `CURSORPIPE_REQUEST_TIMEOUT_S`, etc.) also apply.

---

## Endpoints

### POST `/v1/chat/completions`

OpenAI-compatible chat completions.

**Request body:**

```json
{
  "model": "claude-4.5-sonnet-thinking",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Explain what an API is."}
  ],
  "stream": false,
  "temperature": 0,
  "max_tokens": 2048
}
```

**Response (non-streaming):**

```json
{
  "id": "chatcmpl-abc123def456",
  "object": "chat.completion",
  "created": 1712160000,
  "model": "claude-4.5-sonnet-thinking",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "An API is a set of rules ..."
    },
    "finish_reason": "stop"
  }],
  "usage": {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0
  }
}
```

!!! note "Token counts"
    Cursor does not report token usage, so `usage` fields are always zero.

**Streaming** — set `"stream": true`. The server responds with `text/event-stream` (Server-Sent Events):

```
data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1712160000,"model":"claude-4.5-sonnet-thinking","choices":[{"index":0,"delta":{"role":"assistant","content":""},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1712160000,"model":"claude-4.5-sonnet-thinking","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}

data: {"id":"chatcmpl-abc123","object":"chat.completion.chunk","created":1712160000,"model":"claude-4.5-sonnet-thinking","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

### GET `/v1/models`

Returns available models in OpenAI list format.

```json
{
  "object": "list",
  "data": [
    {"id": "claude-4.5-sonnet-thinking", "object": "model", "created": 1712160000, "owned_by": "cursor"},
    {"id": "gpt-5.4-mini-medium", "object": "model", "created": 1712160000, "owned_by": "cursor"}
  ]
}
```

### GET `/health`

Returns `{"status": "ok"}`. Used for Docker health checks and load balancer probes. Not protected by bearer token auth.

---

## Error responses

Errors follow the OpenAI error format:

```json
{
  "error": {
    "message": "Agent request timed out after 300.0s.",
    "type": "timeout_error",
    "code": "timeout"
  }
}
```

| HTTP Status | cursorpipe Error | Type |
|-------------|-----------------|------|
| 401 | `AuthenticationError` | `authentication_error` |
| 429 | `RateLimitError` | `rate_limit_error` |
| 500 | `AgentCrashError`, `SessionError` | `server_error` |
| 503 | `AgentNotFoundError` | `service_unavailable` |
| 504 | `AgentTimeoutError` | `timeout_error` |

---

## Using with popular clients

### OpenAI Python SDK

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8080/v1", api_key="unused")
response = client.chat.completions.create(
    model="claude-4.5-sonnet-thinking",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)
```

### OpenAI Node.js SDK

```javascript
import OpenAI from "openai";

const client = new OpenAI({ baseURL: "http://localhost:8080/v1", apiKey: "unused" });
const response = await client.chat.completions.create({
  model: "claude-4.5-sonnet-thinking",
  messages: [{ role: "user", content: "Hello!" }],
});
console.log(response.choices[0].message.content);
```

### LangChain

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    base_url="http://localhost:8080/v1",
    api_key="unused",
    model="claude-4.5-sonnet-thinking",
)
print(llm.invoke("Hello!").content)
```

### LiteLLM

```python
import litellm

response = litellm.completion(
    model="openai/claude-4.5-sonnet-thinking",
    messages=[{"role": "user", "content": "Hello!"}],
    api_base="http://localhost:8080/v1",
    api_key="unused",
)
print(response.choices[0].message.content)
```

### curl

```bash
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-4.5-sonnet-thinking","messages":[{"role":"user","content":"Hello!"}]}'
```

### curl (streaming)

```bash
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-4.5-sonnet-thinking","messages":[{"role":"user","content":"Hello!"}],"stream":true}'
```

---

## Incoming request authentication

To protect your server with a bearer token:

```bash
export CURSORPIPE_BEARER_TOKEN=my-secret-token
cursorpipe-server
```

Clients must then include:

```
Authorization: Bearer my-secret-token
```

The `/health` endpoint is always accessible without authentication.

---

## Interactive API docs

FastAPI auto-generates OpenAPI documentation at:

- **Swagger UI**: `http://localhost:8080/docs`
- **ReDoc**: `http://localhost:8080/redoc`
