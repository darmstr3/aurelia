"""Aurelia command-line entrypoint.

Thin wrapper around ``livekit.agents.cli`` so users get the standard
``dev``/``connect``/``start`` subcommands while we control the worker config
and ensure logging is set up before any LiveKit code runs.
"""

from __future__ import annotations

from livekit.agents import cli as livekit_cli

from aurelia.agent import worker_options
from aurelia.config import get_settings
from aurelia.logging import configure as configure_logging


def main() -> None:
    """Entrypoint registered as the ``aurelia`` console script."""
    settings = get_settings()
    configure_logging(env=settings.aurelia_env, level=settings.aurelia_log_level)
    livekit_cli.run_app(worker_options())


if __name__ == "__main__":  # pragma: no cover
    main()
