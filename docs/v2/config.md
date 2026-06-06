# Configuration

All settings are read from environment variables or a `.env` file in the `v2/` directory.
Copy `.env.example` to `.env` and edit it before starting the server.

---

## Required

| Variable | Description |
|---|---|
| `CURSOR_API_KEY` | Cursor API key. Generate at [cursor.com/settings](https://cursor.com/settings) → API Keys. `CURSORPIPE_API_KEY` is also accepted (v1 compatibility — both names work). |

---

## Server

| Variable | Default | Description |
|---|---|---|
| `CURSORPIPE_HOST` | `0.0.0.0` | Bind address |
| `CURSORPIPE_PORT` | `8080` | Listen port |
| `CURSORPIPE_BEARER_TOKEN` | *(empty)* | Protect the API with a bearer token. Empty = no auth. |
| `CURSORPIPE_CORS_ORIGINS` | `*` | Comma-separated allowed CORS origins. `*` allows all. |

---

## Agent

| Variable | Default | Description |
|---|---|---|
| `CURSORPIPE_MODEL` | `composer-2.5` | Default model when none is specified in the request |
| `CURSORPIPE_WORKSPACE` | `.` | Working directory passed to the SDK agent |

---

## Sessions

| Variable | Default | Description |
|---|---|---|
| `CURSORPIPE_SESSION_TTL_MINUTES` | `30` | Idle stateful sessions are evicted after this many minutes |

---

## Features

| Variable | Default | Description |
|---|---|---|
| `CURSORPIPE_EXPOSE_THINKING` | `false` | Expose model thinking/reasoning in responses (see [Thinking docs](thinking.md)) |

---

## Logging

| Variable | Default | Description |
|---|---|---|
| `CURSORPIPE_LOG_LEVEL` | `info` | Log level for both Python stdlib logging and uvicorn. Accepted: `debug`, `info`, `warning`, `error`, `critical` |

---

## Example `.env`

```bash
# Required
CURSOR_API_KEY=crsr_your_key_here

# Server
CURSORPIPE_HOST=0.0.0.0
CURSORPIPE_PORT=8080
CURSORPIPE_BEARER_TOKEN=          # leave empty to disable auth
CURSORPIPE_CORS_ORIGINS=*

# Agent
CURSORPIPE_MODEL=composer-2.5
CURSORPIPE_WORKSPACE=.

# Sessions
CURSORPIPE_SESSION_TTL_MINUTES=30

# Features
CURSORPIPE_EXPOSE_THINKING=false

# Logging
CURSORPIPE_LOG_LEVEL=info
```

---

## Notes

- Both `CURSOR_API_KEY` and `CURSORPIPE_API_KEY` are accepted for the API key. `CURSOR_API_KEY` is preferred — it matches the name the Cursor SDK itself uses. `CURSORPIPE_API_KEY` is supported for compatibility with v1.
- The server refuses to start if `CURSOR_API_KEY` is not set — it will print a clear error with a link to generate a key.
- When `CURSORPIPE_BEARER_TOKEN` is set, every request to `/v1/*` must include `Authorization: Bearer <token>`. The `/health` endpoint is always public.
