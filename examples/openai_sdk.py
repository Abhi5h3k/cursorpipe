"""Use cursorpipe-server with the standard OpenAI Python SDK.

Prerequisites:
    1. Start the server:   cursorpipe-server
    2. Install the SDK:    pip install openai

The OpenAI SDK speaks the same protocol cursorpipe-server exposes,
so any code written for OpenAI works unchanged — just point base_url
at the local server.
"""

from openai import OpenAI

BASE_URL = "http://localhost:8080/v1"

client = OpenAI(base_url=BASE_URL, api_key="unused")

# --- Non-streaming ---------------------------------------------------------

response = client.chat.completions.create(
    model="claude-4.5-sonnet-thinking",
    messages=[{"role": "user", "content": "Explain what an API is in two sentences."}],
)
print(response.choices[0].message.content)

# --- Streaming -------------------------------------------------------------

print("\n--- streaming ---")
stream = client.chat.completions.create(
    model="claude-4.5-sonnet-thinking",
    messages=[{"role": "user", "content": "Write a haiku about Python."}],
    stream=True,
)
for chunk in stream:
    delta = chunk.choices[0].delta
    if delta.content:
        print(delta.content, end="", flush=True)
print()
