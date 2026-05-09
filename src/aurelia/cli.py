"""Aurelia command-line entrypoint.

Thin wrapper around ``livekit.agents.cli`` so users get the standard
``dev``/``connect``/``start`` subcommands while we control the worker config
and ensure logging is set up before any LiveKit code runs.

Importantly, this also pushes the contents of ``.env`` into ``os.environ``
before LiveKit's worker reads ``LIVEKIT_URL`` / ``LIVEKIT_API_KEY`` /
``LIVEKIT_API_SECRET`` directly from the OS environment.
"""

from __future__ import annotations

from dotenv import load_dotenv
from livekit.agents import cli as livekit_cli

from aurelia.agent import worker_options
from aurelia.config import get_settings
from aurelia.logging import configure as configure_logging


def main() -> None:
    """Entrypoint registered as the ``aurelia`` console script."""
    # LiveKit's Worker reads LIVEKIT_* directly from os.environ; pydantic-settings
    # reading .env into a Settings object isn't enough. Load .env into the process
    # environment so both code paths see the same values.
    load_dotenv()
    settings = get_settings()
    configure_logging(env=settings.aurelia_env, level=settings.aurelia_log_level)
    livekit_cli.run_app(worker_options())


if __name__ == "__main__":  # pragma: no cover
    main()
