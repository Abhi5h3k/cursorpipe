"""CLI entrypoint: ``python -m cursorpipe_server`` or ``cursorpipe-server``."""

from __future__ import annotations

import logging
import socket
import sys


def _port_is_free(host: str, port: int) -> bool:
    bind_host = "127.0.0.1" if host in ("0.0.0.0", "") else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((bind_host, port))
            return True
        except OSError:
            return False


def main() -> None:
    try:
        import uvicorn
    except ImportError:
        print(
            "uvicorn is required to run cursorpipe-server.\n"
            "Install with: pip install cursorpipe[server]",
            file=sys.stderr,
        )
        sys.exit(1)

    from cursorpipe_server.app import ServerConfig, create_app

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    cfg = ServerConfig()

    if not _port_is_free(cfg.host, cfg.port):
        print(
            f"ERROR: Port {cfg.port} is already in use.\n"
            f"Set a different port with: CURSORPIPE_PORT=<port>",
            file=sys.stderr,
        )
        sys.exit(1)

    app = create_app(cfg)
    uvicorn.run(app, host=cfg.host, port=cfg.port, log_level="info")


if __name__ == "__main__":
    main()
