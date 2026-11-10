import argparse
import getpass
import logging.config
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime

from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from tourneyhub.db.session import create_db_engine, create_session_factory
from tourneyhub.logging_config import LOGGING_CONFIG
from tourneyhub.services import instance as instance_service
from tourneyhub.services import maintenance
from tourneyhub.settings import Settings


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point of the `tourneyhub` command (ADR-007)."""
    logging.config.dictConfig(LOGGING_CONFIG)  # as create_app() does (§4.6)
    parser = argparse.ArgumentParser(prog="tourneyhub")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate", help="upgrade the database to the newest revision")
    signup_code = commands.add_parser(
        "set-signup-code",
        help="set the sign-up code, read from a prompt, or close sign-up",
    )
    signup_code.add_argument(
        "--clear", action="store_true", help="close sign-up instead (ADR-007)"
    )
    commands.add_parser(
        "cleanup", help="delete expired refresh tokens and old sign-in attempts"
    )
    args = parser.parse_args(argv)
    if args.command == "migrate":
        migrate()
    elif args.command == "set-signup-code":
        return set_signup_code(clear=args.clear)
    else:
        cleanup()
    return 0


def migrate() -> None:
    """Run `alembic upgrade head` from the installed package (ADR-014)."""
    config = Config()  # the image has no pyproject.toml
    config.set_main_option("script_location", "tourneyhub:migrations")
    command.upgrade(config, "head")


@contextmanager
def _transaction() -> Iterator[Session]:
    """One transaction with the database of the environment's settings."""
    engine = create_db_engine(Settings())
    try:
        with create_session_factory(engine).begin() as session:
            yield session
    finally:
        engine.dispose()


def set_signup_code(*, clear: bool) -> int:
    """Set the sign-up code from a prompt, or close sign-up (ADR-007, FR-005).

    The code is read with `getpass`, so it is in no argument, no shell history
    and no process list, and it is never printed back.
    """
    code = None
    if not clear:
        code = getpass.getpass("Sign-up code: ").strip()
        if not code:
            print("The code is empty; use --clear to close sign-up.")
            return 1
    with _transaction() as session:
        instance_service.set_signup_code(session, code=code, now=datetime.now(UTC))
    print("Sign-up is closed." if code is None else "The sign-up code is set.")
    return 0


def cleanup() -> None:
    """Delete refresh tokens and sign-in attempts that no longer matter (ADR-006).

    Running it on a schedule is not set up yet (P15).
    """
    with _transaction() as session:
        result = maintenance.clean_up(session, now=datetime.now(UTC))
    print(
        f"Deleted {result.refresh_tokens} refresh tokens"
        f" and {result.auth_attempts} sign-in attempts."
    )
