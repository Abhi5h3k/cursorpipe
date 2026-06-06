FROM python:3.12-slim

WORKDIR /app

# Install the package with server extras
COPY pyproject.toml README.md ./
COPY cursorpipe/ ./cursorpipe/
COPY cursorpipe_server/ ./cursorpipe_server/

RUN pip install --no-cache-dir ".[server]"

EXPOSE 8080

# Install the cursor-sdk bridge binary (bundled with the package).
# cursor-sdk-bridge is placed on PATH by pip at install time.

CMD ["python", "-m", "cursorpipe_server"]
