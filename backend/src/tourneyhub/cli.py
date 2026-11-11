import argparse
import getpass
import logging.config
import re
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime

from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from tourneyhub.db.session import create_db_engine, create_session_factory
from tourneyhub.engine.accounts import Language
from tourneyhub.engine.admin import AdminActionSource
from tourneyhub.logging_config import LOGGING_CONFIG
from tourneyhub.services import accounts as account_service
from tourneyhub.services import admin as admin_service
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
    how = signup_code.add_mutually_exclusive_group()
    how.add_argument(
        "--clear", action="store_true", help="close sign-up instead (ADR-007)"
    )
    how.add_argument(
        "--generate",
        action="store_true",
        help="make a random code and print it, as the only output, once",
    )
    new_admin = commands.add_parser(
        "create-admin",
        help="create an account with admin rights, the password read from a prompt",
    )
    new_admin.add_argument("--email", required=True)
    new_admin.add_argument(
        "--display-name", help="default: the part of the email before the @"
    )
    for name, help_ in (
        ("grant-admin", "give an existing account admin rights"),
        ("revoke-admin", "take admin rights from an account"),
    ):
        commands.add_parser(name, help=help_).add_argument("--email", required=True)
    commands.add_parser(
        "cleanup", help="delete expired refresh tokens and old sign-in attempts"
    )
    args = parser.parse_args(argv)
    if args.command == "migrate":
        migrate()
    elif args.command == "set-signup-code":
        return set_signup_code(clear=args.clear, generate=args.generate)
    elif args.command == "create-admin":
        return create_admin(email=args.email, display_name=args.display_name)
    elif args.command in {"grant-admin", "revoke-admin"}:
        return set_admin_flag(email=args.email, is_admin=args.command == "grant-admin")
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


def set_signup_code(*, clear: bool, generate: bool = False) -> int:
    """Set the sign-up code from a prompt, or close sign-up (ADR-007, FR-005).

    The code is read with `getpass`, so it is in no argument, no shell history
    and no process list, and it is never printed back. The one exception is
    `generate`: a code made here is shown once, as the only output, because
    nobody else knows it.
    """
    code = None
    if generate:
        code = instance_service.generate_signup_code()
    elif not clear:
        code = getpass.getpass("Sign-up code: ").strip()
        shortest = instance_service.SIGNUP_CODE_MIN_LENGTH
        longest = instance_service.SIGNUP_CODE_MAX_LENGTH
        if not shortest <= len(code) <= longest:
            print(
                f"The code needs {shortest} to {longest} characters;"
                " use --clear to close sign-up."
            )
            return 1
    with _transaction() as session:
        admin_service.set_signup_code(
            session,
            source=AdminActionSource.CLI,
            admin_user_id=None,
            code=code,
            now=datetime.now(UTC),
        )
    if generate:
        print(code)
    else:
        print("Sign-up is closed." if code is None else "The sign-up code is set.")
    return 0


def create_admin(*, email: str, display_name: str | None) -> int:
    """Create an account with admin rights; the only way to make a first admin.

    No web route can create an admin (ADR-007). The password is read with
    `getpass` twice and never printed. Recorded as `create_admin`, source `cli`.
    """
    email = email.strip()
    if not (
        len(email) <= account_service.EMAIL_MAX_LENGTH
        and re.fullmatch(account_service.EMAIL_PATTERN, email)
    ):
        print("That is not an email address.")
        return 1
    password = getpass.getpass("Password: ")
    shortest = account_service.MIN_PASSWORD_LENGTH
    longest = account_service.MAX_PASSWORD_LENGTH
    if not shortest <= len(password) <= longest:
        print(f"The password needs {shortest} to {longest} characters.")
        return 1
    if getpass.getpass("Password again: ") != password:
        print("The passwords differ.")
        return 1
    name = (display_name or email.partition("@")[0]).strip()[:100]
    with _transaction() as session:
        user = admin_service.create_admin(
            session,
            email=email,
            display_name=name,
            password=password,
            language=Language.EN,
            now=datetime.now(UTC),
        )
    if user is None:
        print("An account with that email exists; use grant-admin.")
        return 1
    print("The admin account is created.")
    return 0


def set_admin_flag(*, email: str, is_admin: bool) -> int:
    """Give an existing account admin rights, or take them away (ADR-007).

    A change is recorded as `grant_admin` or `revoke_admin`, source `cli`. It
    takes effect on the account's next request, because the flag is read from
    the row (ADR-006).
    """
    with _transaction() as session:
        changed = admin_service.set_admin_flag(
            session, email=email.strip(), is_admin=is_admin, now=datetime.now(UTC)
        )
    if changed is None:
        print("No account has that email.")
        return 1
    wanted = "admin" if is_admin else "not an admin"
    print(f"The account is {'now ' if changed else 'already '}{wanted}.")
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
