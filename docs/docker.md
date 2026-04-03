# Docker Deployment

Run cursorpipe-server as a Docker container — one command to turn your Cursor subscription into a self-hosted OpenAI-compatible API.

---

## Quick start

```bash
git clone https://github.com/Abhi5h3k/cursorpipe.git
cd cursorpipe

# Set your Cursor API key
export CURSOR_API_KEY=crsr_your_key_here

# Build and start
docker compose up
```

The server is now running on `http://localhost:8080`.

```bash
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-4.5-sonnet-thinking","messages":[{"role":"user","content":"Hello!"}]}'
```

---

## How the Dockerfile works

The Dockerfile:

1. Starts from `python:3.12-slim`
2. Downloads the Cursor Agent CLI from Cursor's official servers using `curl https://cursor.com/install -fsS | bash`
3. Installs cursorpipe with server and fast-JSON extras
4. Exposes port 8080
5. Runs `cursorpipe-server`

!!! note "No proprietary binaries bundled"
    The Cursor CLI is **not** bundled in the image. It is downloaded at build time from Cursor's official install endpoint — the same command you would run manually. You build the image yourself.

---

## docker-compose.yml

```yaml
services:
  cursorpipe:
    build: .
    ports:
      - "8080:8080"
    environment:
      - CURSOR_API_KEY=${CURSOR_API_KEY}
      - CURSORPIPE_POOL_SIZE=${CURSORPIPE_POOL_SIZE:-5}
      - CURSORPIPE_BEARER_TOKEN=${CURSORPIPE_BEARER_TOKEN:-}
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 5s
      retries: 3
    restart: unless-stopped
```

---

## Environment variables

Pass configuration via the `environment` section in docker-compose or `docker run -e`:

| Variable | Default | Description |
|----------|---------|-------------|
| `CURSOR_API_KEY` | **required** | Your Cursor API key |
| `CURSORPIPE_PORT` | `8080` | Server port |
| `CURSORPIPE_POOL_SIZE` | `5` | ACP sessions to pre-create |
| `CURSORPIPE_BEARER_TOKEN` | `""` | Protect the API with a bearer token |
| `CURSORPIPE_REQUEST_TIMEOUT_S` | `300` | Per-request timeout |

See [Configuration](getting-started.md) for the full list of `CURSORPIPE_*` variables.

---

## Building manually

```bash
docker build -t cursorpipe-server .
```

## Running manually

```bash
docker run -d \
  --name cursorpipe \
  -p 8080:8080 \
  -e CURSOR_API_KEY=crsr_your_key_here \
  cursorpipe-server
```

---

## Health checks

The container includes a built-in health check hitting `GET /health`:

```bash
docker inspect --format='{{.State.Health.Status}}' cursorpipe
```

Returns `healthy` once the server has started and warmed up.

---

## Production tips

### Reverse proxy (nginx)

Put nginx in front for TLS termination:

```nginx
server {
    listen 443 ssl;
    server_name api.example.com;

    ssl_certificate     /etc/ssl/certs/cert.pem;
    ssl_certificate_key /etc/ssl/private/key.pem;

    location / {
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;

        # Required for SSE streaming
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
    }
}
```

### Resource limits

```yaml
services:
  cursorpipe:
    # ...
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: "1.0"
```

### Bearer token auth

Protect your server from unauthorized access:

```bash
export CURSORPIPE_BEARER_TOKEN=my-secret-token
docker compose up
```

Clients must include `Authorization: Bearer my-secret-token` on every request (except `/health`).

---

## Logs

```bash
# Follow logs
docker compose logs -f

# Tail last 50 lines
docker compose logs --tail 50
```

---

## Stopping

```bash
docker compose down
```
