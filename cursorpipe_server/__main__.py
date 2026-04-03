"""CLI entrypoint: ``python -m cursorpipe_server`` or ``cursorpipe-server``."""

from __future__ import annotations

import logging
import sys


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
    app = create_app(cfg)

    uvicorn.run(app, host=cfg.host, port=cfg.port, log_level="info")


if __name__ == "__main__":
    main()
