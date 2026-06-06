"""cursorpipe v2 example: OpenAI Python SDK.

Drop-in replacement for the OpenAI API — just set base_url to cursorpipe v2.
Works with the standard openai Python package without any code changes.

Prerequisites:
  - cursorpipe v2 server running (python -m cursorpipe_server inside v2/)
  - CURSOR_API_KEY set in .env or environment
  - pip install openai

Run:
  python v2/examples/openai_sdk.py
"""

from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8080/v1",
    api_key="not-needed",  # cursorpipe uses CURSOR_API_KEY server-side
)


def non_streaming() -> None:
    print("=== Non-streaming ===")
    response = client.chat.completions.create(
        model="composer-2.5",
        messages=[{"role": "user", "content": "Explain async/await in one sentence."}],
    )
    print(response.choices[0].message.content)
    print()


def streaming() -> None:
    print("=== Streaming ===")
    stream = client.chat.completions.create(
        model="composer-2.5",
        stream=True,
        messages=[{"role": "user", "content": "List three Python best practices."}],
    )
    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            print(delta.content, end="", flush=True)
    print()


def with_system_prompt() -> None:
    print("=== With system prompt ===")
    response = client.chat.completions.create(
        model="composer-2.5",
        messages=[
            {"role": "system", "content": "You are a concise assistant. Answer in one word."},
            {"role": "user", "content": "What is the capital of France?"},
        ],
    )
    print(response.choices[0].message.content)
    print()


if __name__ == "__main__":
    non_streaming()
    streaming()
    with_system_prompt()
