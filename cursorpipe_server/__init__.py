"""cursorpipe-server — OpenAI-compatible HTTP server for cursorpipe."""

from cursorpipe_server.app import ServerConfig, create_app

__all__ = ["create_app", "ServerConfig"]
