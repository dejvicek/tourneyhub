import getpass
import io
from collections.abc import Iterator
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime, timedelta
from uuid import uuid7

import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from tourneyhub.cli import main
from tourneyhub.db.models.accounts import (
    AuthAttempt,
    InstanceSettings,
    RefreshToken,
    User,
)
from tourneyhub.engine.accounts import Language
from tourneyhub.engine.auth import AuthAttemptKind
from tourneyhub.services import auth as auth_service
from tourneyhub.settings import Settings


def test_main_without_a_command_fails() -> None:
    # main() binds the log handler to stderr first (§9), so not capsys.
    with redirect_stderr(io.StringIO()) as stderr, pytest.raises(SystemExit) as raised:
        main([])

    assert raised.value.code == 2
    assert "usage: tourneyhub" in stderr.getvalue()


@pytest.fixture
def cli_environment(
    committing_engine: Engine,
    committing_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Engine]:
    """The environment `Settings()` reads, pointing at the test database."""
    monkeypatch.setenv("TOURNEYHUB_ENV", "development")
    monkeypatch.setenv(
        "TOURNEYHUB_DATABASE_URL", committing_settings.database_url.get_secret_value()
    )
    monkeypatch.setenv("TOURNEYHUB_JWT_SECRET", "x" * 32)
    yield committing_engine
    with committing_engine.begin() as connection:
        connection.execute(
            text("UPDATE instance_settings SET signup_code = NULL, updated_at = NULL")
        )


def _run(*argv: str) -> tuple[int, str, str]:
    """Run the command; its log goes to the stderr it binds first (§9)."""
    with (
        redirect_stdout(io.StringIO()) as stdout,
        redirect_stderr(io.StringIO()) as stderr,
    ):
        code = main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


def _stored_code(engine: Engine) -> str | None:
    with Session(engine) as reader:
        return reader.get_one(InstanceSettings, 1).signup_code


def _answer_prompt(monkeypatch: pytest.MonkeyPatch, answer: str) -> list[str]:
    prompts: list[str] = []

    def fake(prompt: str = "") -> str:
        prompts.append(prompt)
        return answer

    monkeypatch.setattr(getpass, "getpass", fake)
    return prompts


@pytest.mark.concurrency
def test_adr007_set_signup_code_stores_the_code_read_from_a_prompt(
    cli_environment: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    prompts = _answer_prompt(monkeypatch, "  Žluťoučký kůň \n")

    code, stdout, _ = _run("set-signup-code")

    assert code == 0
    assert _stored_code(cli_environment) == "Žluťoučký kůň"
    assert prompts == ["Sign-up code: "]
    with Session(cli_environment) as reader:
        assert reader.get_one(InstanceSettings, 1).updated_at is not None
    assert stdout == "The sign-up code is set.\n"


@pytest.mark.concurrency
@pytest.mark.usefixtures("cli_environment")
def test_adr007_set_signup_code_never_prints_the_code_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _answer_prompt(monkeypatch, "very-secret-code")

    _, stdout, stderr = _run("set-signup-code")

    assert "very-secret-code" not in stdout + stderr


@pytest.mark.concurrency
def test_adr007_a_new_code_replaces_the_old_one(
    cli_environment: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _answer_prompt(monkeypatch, "first")
    _run("set-signup-code")
    _answer_prompt(monkeypatch, "second")

    _run("set-signup-code")

    assert _stored_code(cli_environment) == "second"


@pytest.mark.concurrency
def test_adr007_clear_closes_sign_up(
    cli_environment: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    prompts = _answer_prompt(monkeypatch, "open")
    _run("set-signup-code")

    code, stdout, _ = _run("set-signup-code", "--clear")

    assert code == 0
    assert _stored_code(cli_environment) is None
    assert stdout == "Sign-up is closed.\n"
    assert len(prompts) == 1  # --clear asks for nothing


@pytest.mark.concurrency
@pytest.mark.parametrize("answer", ["", "   "])
def test_adr007_an_empty_code_is_refused_and_changes_nothing(
    cli_environment: Engine, monkeypatch: pytest.MonkeyPatch, answer: str
) -> None:
    _answer_prompt(monkeypatch, "kept")
    _run("set-signup-code")
    _answer_prompt(monkeypatch, answer)

    code, stdout, _ = _run("set-signup-code")

    assert code == 1
    assert "--clear" in stdout
    assert _stored_code(cli_environment) == "kept"


def test_adr007_the_code_is_not_an_argument() -> None:
    with redirect_stderr(io.StringIO()), pytest.raises(SystemExit) as raised:
        main(["set-signup-code", "my-code"])

    assert raised.value.code == 2


@pytest.mark.concurrency
def test_adr006_cleanup_deletes_what_no_longer_matters_and_reports_the_counts(
    cli_environment: Engine, settings: Settings
) -> None:
    now = datetime.now(UTC)
    with Session(cli_environment) as setup:
        user = User(
            email=f"{uuid7()}@example.test",
            display_name="Ana",
            password_hash="!",
            language=Language.EN,
            created_at=now,
        )
        setup.add(user)
        setup.flush()
        auth_service.start_session(
            setup, user_id=user.id, key=settings.jwt_secret, now=now
        )
        dead = auth_service.start_session(
            setup, user_id=user.id, key=settings.jwt_secret, now=now
        )
        auth_service.log_out(setup, refresh_token=dead.refresh_token, now=now)
        setup.add_all(
            AuthAttempt(
                kind=AuthAttemptKind.LOGIN_IP,
                key="192.0.2.1",
                succeeded=False,
                created_at=created_at,
            )
            for created_at in (now - timedelta(hours=2), now)
        )
        setup.commit()

    code, stdout, _ = _run("cleanup")

    assert code == 0
    assert stdout == "Deleted 1 refresh tokens and 1 sign-in attempts.\n"
    with Session(cli_environment) as reader:
        assert reader.scalar(select(func.count()).select_from(RefreshToken)) == 1
        assert reader.scalar(select(func.count()).select_from(AuthAttempt)) == 1


def test_adr006_cleanup_takes_no_arguments() -> None:
    with redirect_stderr(io.StringIO()), pytest.raises(SystemExit) as raised:
        main(["cleanup", "--all"])

    assert raised.value.code == 2
