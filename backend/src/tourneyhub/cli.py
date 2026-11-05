import argparse
import logging.config
from collections.abc import Sequence

from alembic import command
from alembic.config import Config

from tourneyhub.logging_config import LOGGING_CONFIG


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point of the `tourneyhub` command (ADR-007)."""
    logging.config.dictConfig(LOGGING_CONFIG)  # as create_app() does (§4.6)
    parser = argparse.ArgumentParser(prog="tourneyhub")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate", help="upgrade the database to the newest revision")
    args = parser.parse_args(argv)
    if args.command == "migrate":
        migrate()
    return 0


def migrate() -> None:
    """Run `alembic upgrade head` from the installed package (ADR-014)."""
    config = Config()  # the image has no pyproject.toml
    config.set_main_option("script_location", "tourneyhub:migrations")
    command.upgrade(config, "head")
