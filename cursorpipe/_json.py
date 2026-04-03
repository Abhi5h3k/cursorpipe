"""Fast JSON serialization with graceful fallback.

Uses ``orjson`` (Rust-backed, ~4.6x faster) when available, otherwise falls
back to the stdlib ``json`` module transparently.  Install the ``fast`` extra
to get orjson::

    pip install cursorpipe[fast]
"""

from __future__ import annotations

from typing import Any

try:
    import orjson

    def loads(data: str | bytes) -> Any:
        return orjson.loads(data)

    def dumps(obj: Any) -> str:
        return orjson.dumps(obj).decode("utf-8")

except ImportError:
    import json

    loads = json.loads
    dumps = json.dumps  # type: ignore[assignment]
