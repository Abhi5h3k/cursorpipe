"""CLI entry point: `cursorpipe-server` or `python -m cursorpipe_server`."""

import logging

import uvicorn

from cursorpipe._config import settings


def main() -> None:
    log_level = settings.log_level.lower()

    # Configure Python's stdlib logging so all loggers (including
    # cursorpipe.*) respect the chosen level.
    logging.basicConfig(
        level=log_level.upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    uvicorn.run(
        "cursorpipe_server.app:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level=log_level,
    )


if __name__ == "__main__":
    main()
