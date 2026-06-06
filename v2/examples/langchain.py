"""cursorpipe v2 example: LangChain integration.

Use cursorpipe v2 as a drop-in LLM backend for LangChain.
ChatOpenAI with base_url pointing at cursorpipe works without any changes.

Prerequisites:
  - cursorpipe v2 server running (python -m cursorpipe_server inside v2/)
  - CURSOR_API_KEY set in .env or environment
  - pip install langchain-openai

Run:
  python v2/examples/langchain.py
"""

from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    base_url="http://localhost:8080/v1",
    api_key="not-needed",
    model="composer-2.5",
)


def basic_invoke() -> None:
    print("=== Basic invoke ===")
    response = llm.invoke("Explain what a REST API is in one sentence.")
    print(response.content)
    print()


def with_messages() -> None:
    from langchain_core.messages import HumanMessage, SystemMessage

    print("=== With messages ===")
    messages = [
        SystemMessage(content="You are a concise assistant. Answer in one word."),
        HumanMessage(content="What is the capital of Japan?"),
    ]
    response = llm.invoke(messages)
    print(response.content)
    print()


def streaming() -> None:
    print("=== Streaming ===")
    for chunk in llm.stream("List three benefits of Python."):
        print(chunk.content, end="", flush=True)
    print()


if __name__ == "__main__":
    basic_invoke()
    with_messages()
    streaming()
