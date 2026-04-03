# Testing

cursorpipe has three test suites that run in order of increasing requirements.

## Prerequisites

Install dev dependencies:

```bash
pip install -e ".[dev]"
```

For **integration tests** you also need:

- Cursor Agent CLI installed ([installation guide](https://cursor.com/docs/cli/installation))
- Authentication configured via `agent login` or `CURSORPIPE_API_KEY`

## Test suites

### Preflight checks

Validates that your environment is ready — agent binary found, authentication configured, API reachable.  Run this first to get clear error messages instead of cryptic failures deeper in the suite.

```bash
pytest tests/test_preflight.py -v
```

| Check | What it verifies |
|-------|-----------------|
| Agent on PATH | The agent binary is discoverable |
| Agent is executable | The resolved binary can actually run |
| Agent version | `agent --version` exits cleanly |
| Authentication | API key, auth token, or login session exists |
| Connectivity | A minimal prompt returns a response |
| Model discovery | `agent --list-models` returns at least one model |

### Unit tests

Fast, offline tests for internal components — config loading, Pydantic models, error hierarchy, and the NDJSON stream parser.  No agent binary or network access required.

```bash
pytest tests/test_unit.py -v
```

### Integration tests

End-to-end tests that make **real API calls** through the Cursor agent.  These are slow and consume API quota.

```bash
pytest tests/test_integration.py -v -m integration
```

| Test | What it verifies |
|------|-----------------|
| Subprocess generate | Single-call via subprocess transport |
| Subprocess streaming | Streaming via subprocess transport |
| ACP generate | Single-call via persistent ACP transport |
| ACP streaming | Streaming via ACP transport |
| ACP model switching | Switching models between calls |
| ACP multi-turn session | Session memory across turns |
| ACP session streaming | `session.stream_prompt()` yields chunks |
| Model discovery | `list_models()` returns available models |
| Auto fallback | AUTO strategy falls back from ACP to subprocess |

## Running everything

```bash
pytest -v
```

This runs all three suites.  Integration tests are skipped automatically if the agent binary or authentication is not available.

## Skipping integration tests

If you only want the fast offline tests:

```bash
pytest -m "not integration" -v
```

---

## Testing the HTTP server

### Quick smoke test

Start the server and hit the health endpoint:

```bash
# Terminal 1: start the server
cursorpipe-server

# Terminal 2: test health
curl http://localhost:8080/health
# {"status":"ok"}
```

### Test completions

```bash
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-4.5-sonnet-thinking","messages":[{"role":"user","content":"Reply with OK"}]}'
```

### Test streaming

```bash
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-4.5-sonnet-thinking","messages":[{"role":"user","content":"Count to 5"}],"stream":true}'
```

### Test model listing

```bash
curl http://localhost:8080/v1/models
```

### Test with OpenAI SDK

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8080/v1", api_key="unused")
r = client.chat.completions.create(
    model="claude-4.5-sonnet-thinking",
    messages=[{"role": "user", "content": "Reply with OK"}],
)
assert "OK" in r.choices[0].message.content
print("OpenAI SDK test passed")
```

### Test with Docker

```bash
docker compose up -d
curl http://localhost:8080/health
# {"status":"ok"}

curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-4.5-sonnet-thinking","messages":[{"role":"user","content":"Reply with OK"}]}'

docker compose down
```
