import getpass
import io
from collections.abc import Iterator
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid7

import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from tourneyhub.cli import main
from tourneyhub.db.models.accounts import (
    AdminAction,
    AuthAttempt,
    InstanceSettings,
    RefreshToken,
    User,
)
from tourneyhub.engine.accounts import Language
from tourneyhub.engine.admin import AdminActionKind, AdminActionSource
from tourneyhub.engine.auth import AuthAttemptKind
from tourneyhub.services import auth as auth_service
from tourneyhub.services.instance import (
    SIGNUP_CODE_MAX_LENGTH,
    SIGNUP_CODE_MIN_LENGTH,
)
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
    _answer_prompt(monkeypatch, "first-code-123")
    _run("set-signup-code")
    _answer_prompt(monkeypatch, "second-code-123")

    _run("set-signup-code")

    assert _stored_code(cli_environment) == "second-code-123"


@pytest.mark.concurrency
def test_adr007_clear_closes_sign_up(
    cli_environment: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    prompts = _answer_prompt(monkeypatch, "open-code-12345")
    _run("set-signup-code")

    code, stdout, _ = _run("set-signup-code", "--clear")

    assert code == 0
    assert _stored_code(cli_environment) is None
    assert stdout == "Sign-up is closed.\n"
    assert len(prompts) == 1  # --clear asks for nothing


@pytest.mark.concurrency
@pytest.mark.parametrize(
    "answer",
    [
        pytest.param("", id="empty"),
        pytest.param("   ", id="blank"),
        pytest.param("x" * 11, id="too-short"),
        pytest.param(f"  {'x' * 11}  ", id="too-short-after-stripping"),
        pytest.param("x" * 257, id="too-long"),
    ],
)
def test_adr007_a_code_of_the_wrong_length_is_refused_and_changes_nothing(
    cli_environment: Engine, monkeypatch: pytest.MonkeyPatch, answer: str
) -> None:
    _answer_prompt(monkeypatch, "kept-code-12345")
    _run("set-signup-code")
    _answer_prompt(monkeypatch, answer)

    code, stdout, _ = _run("set-signup-code")

    assert code == 1
    assert "12 to 256 characters" in stdout
    assert not answer.strip() or answer.strip() not in stdout
    assert _stored_code(cli_environment) == "kept-code-12345"


@pytest.mark.concurrency
@pytest.mark.parametrize("length", [12, 256])
def test_adr007_a_code_of_the_limit_lengths_is_accepted(
    cli_environment: Engine, monkeypatch: pytest.MonkeyPatch, length: int
) -> None:
    _answer_prompt(monkeypatch, "x" * length)

    code, _, _ = _run("set-signup-code")

    assert code == 0
    assert _stored_code(cli_environment) == "x" * length


@pytest.mark.concurrency
def test_adr007_generate_stores_a_random_code_and_prints_only_it(
    cli_environment: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    prompts = _answer_prompt(monkeypatch, "unused")

    code, stdout, _ = _run("set-signup-code", "--generate")
    again = _run("set-signup-code", "--generate")[1]

    assert code == 0
    printed = stdout.removesuffix("\n")
    assert "\n" not in stdout.removesuffix("\n")  # the code, and nothing else
    assert len(printed) == 22
    assert printed.isascii()
    assert printed != again.strip()  # random
    assert _stored_code(cli_environment) == again.strip()
    assert prompts == []  # nothing is asked


@pytest.mark.concurrency
def test_adr007_a_generated_code_is_within_the_length_limits(
    cli_environment: Engine,
) -> None:
    _run("set-signup-code", "--generate")

    stored = _stored_code(cli_environment)
    assert stored is not None
    assert SIGNUP_CODE_MIN_LENGTH <= len(stored) <= SIGNUP_CODE_MAX_LENGTH


@pytest.mark.parametrize("flags", [["--clear", "--generate"]])
def test_adr007_clear_and_generate_exclude_each_other(flags: list[str]) -> None:
    with redirect_stderr(io.StringIO()), pytest.raises(SystemExit) as raised:
        main(["set-signup-code", *flags])

    assert raised.value.code == 2


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


def _actions(engine: Engine) -> list[AdminAction]:
    with Session(engine) as reader:
        return list(reader.scalars(select(AdminAction).order_by(AdminAction.id)))


def _answer_prompts(monkeypatch: pytest.MonkeyPatch, *answers: str) -> list[str]:
    """Answer the prompts one after the other; returns the prompts asked."""
    remaining = list(answers)
    prompts: list[str] = []

    def fake(prompt: str = "") -> str:
        prompts.append(prompt)
        return remaining.pop(0)

    monkeypatch.setattr(getpass, "getpass", fake)
    return prompts


def _user(engine: Engine, email: str) -> User | None:
    with Session(engine) as reader:
        return reader.scalars(
            select(User).where(func.lower(User.email) == email.lower())
        ).one_or_none()


def _make_account(engine: Engine, email: str, *, is_admin: bool = False) -> UUID:
    with Session(engine) as setup:
        user = User(
            email=email,
            display_name="Ola",
            password_hash="!",
            is_admin=is_admin,
            language=Language.EN,
            created_at=datetime.now(UTC),
        )
        setup.add(user)
        setup.commit()
        return user.id


PASSWORD = "a long enough passphrase"


@pytest.mark.concurrency
def test_adr007_set_signup_code_records_a_cli_action_without_the_code(
    cli_environment: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _answer_prompt(monkeypatch, "very-secret-code")

    _run("set-signup-code")
    _run("set-signup-code", "--generate")
    _run("set-signup-code", "--clear")

    actions = _actions(cli_environment)
    assert [
        (a.source, a.action, a.admin_user_id, a.target_user_id) for a in actions
    ] == [(AdminActionSource.CLI, AdminActionKind.SET_SIGNUP_CODE, None, None)] * 3
    assert "very-secret-code" not in repr([vars(a) for a in actions])


@pytest.mark.concurrency
def test_adr007_set_signup_code_records_nothing_when_the_code_is_unchanged(
    cli_environment: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _run("set-signup-code", "--clear")  # sign-up is closed already
    _answer_prompt(monkeypatch, "the-same-code-123")
    _run("set-signup-code")
    changed_at = _updated_at(cli_environment)

    _run("set-signup-code")  # the same code again
    _run("set-signup-code", "--clear")
    _run("set-signup-code", "--clear")  # closed twice

    assert [a.action for a in _actions(cli_environment)] == [
        AdminActionKind.SET_SIGNUP_CODE
    ] * 2  # set, then clear
    assert _updated_at(cli_environment) != changed_at  # the clear changed it
    assert _stored_code(cli_environment) is None


def _updated_at(engine: Engine) -> datetime | None:
    with Session(engine) as reader:
        return reader.get_one(InstanceSettings, 1).updated_at


@pytest.mark.concurrency
def test_adr007_a_refused_code_records_nothing(
    cli_environment: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _answer_prompt(monkeypatch, "short")

    code, _, _ = _run("set-signup-code")

    assert code == 1
    assert _actions(cli_environment) == []


@pytest.mark.concurrency
def test_adr007_create_admin_makes_an_admin_and_records_it(
    cli_environment: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    prompts = _answer_prompts(monkeypatch, PASSWORD, PASSWORD)

    code, stdout, stderr = _run("create-admin", "--email", "boss@example.test")

    assert code == 0
    assert stdout == "The admin account is created.\n"
    assert prompts == ["Password: ", "Password again: "]
    assert PASSWORD not in stdout + stderr
    user = _user(cli_environment, "boss@example.test")
    assert user is not None
    assert (user.is_admin, user.must_change_password, user.display_name) == (
        True,
        False,
        "boss",
    )
    assert auth_service.verify_password(user.password_hash, PASSWORD)
    [action] = _actions(cli_environment)
    assert (
        action.source,
        action.action,
        action.admin_user_id,
        action.target_user_id,
    ) == (AdminActionSource.CLI, AdminActionKind.CREATE_ADMIN, None, user.id)


@pytest.mark.concurrency
def test_adr007_create_admin_takes_a_display_name(
    cli_environment: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _answer_prompts(monkeypatch, PASSWORD, PASSWORD)

    _run("create-admin", "--email", "boss@example.test", "--display-name", " Šéf ")

    user = _user(cli_environment, "boss@example.test")
    assert user is not None
    assert user.display_name == "Šéf"


@pytest.mark.concurrency
def test_adr007_create_admin_stores_the_display_name_as_the_api_does(
    cli_environment: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _answer_prompts(monkeypatch, PASSWORD, PASSWORD)

    # C + combining caron, then a run of spaces with a no-break space
    _run(
        "create-admin",
        "--email",
        "boss@example.test",
        "--display-name",
        "  C\u030cen\u011bk \u00a0 Boss ",
    )

    user = _user(cli_environment, "boss@example.test")
    assert user is not None
    assert user.display_name == "Čeněk Boss"


@pytest.mark.concurrency
@pytest.mark.parametrize(
    ("name", "message"),
    [
        pytest.param("", "1 to 100", id="empty"),
        pytest.param("   \u00a0 ", "1 to 100", id="blank"),
        pytest.param("x" * 101, "1 to 100", id="too-long"),
        pytest.param("Boss\u200b", "invisible", id="zero-width-space"),
        pytest.param("Bo\u202ess", "invisible", id="right-to-left-override"),
        pytest.param("\u3164", "invisible", id="hangul-filler"),
        pytest.param("\u2800 Boss", "invisible", id="braille-blank"),
        pytest.param("Boss\nTwo", "invisible", id="line-break"),
    ],
)
def test_adr007_create_admin_refuses_a_display_name_the_api_would_refuse(
    cli_environment: Engine,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    message: str,
) -> None:
    prompts = _answer_prompts(monkeypatch, PASSWORD, PASSWORD)

    code, stdout, _ = _run(
        "create-admin", "--email", "boss@example.test", "--display-name", name
    )

    assert code == 1
    assert message in stdout
    assert prompts == []  # refused before the password is asked
    assert _user(cli_environment, "boss@example.test") is None
    assert _actions(cli_environment) == []


@pytest.mark.concurrency
def test_adr007_create_admin_with_no_usable_name_in_the_email_asks_for_one(
    cli_environment: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _answer_prompts(monkeypatch, PASSWORD, PASSWORD)

    code, stdout, _ = _run("create-admin", "--email", f"{'x' * 101}@example.test")

    assert code == 1
    assert "--display-name" in stdout
    assert _actions(cli_environment) == []


@pytest.mark.concurrency
@pytest.mark.parametrize(
    ("email", "answers", "message"),
    [
        pytest.param("not-an-email", [], "not an email", id="bad-email"),
        pytest.param("a@example.test", ["x" * 14], "15 to 1024", id="short"),
        pytest.param("a@example.test", ["x" * 1025], "15 to 1024", id="long"),
        pytest.param(
            "a@example.test", [PASSWORD, PASSWORD + "!"], "differ", id="mismatch"
        ),
    ],
)
def test_adr007_create_admin_refuses_bad_input_and_creates_nothing(
    cli_environment: Engine,
    monkeypatch: pytest.MonkeyPatch,
    email: str,
    answers: list[str],
    message: str,
) -> None:
    _answer_prompts(monkeypatch, *answers)

    code, stdout, _ = _run("create-admin", "--email", email)

    assert code == 1
    assert message in stdout
    assert PASSWORD not in stdout
    assert _user(cli_environment, email) is None
    assert _actions(cli_environment) == []


@pytest.mark.concurrency
def test_adr007_create_admin_with_a_taken_email_points_to_grant_admin(
    cli_environment: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _make_account(cli_environment, "Boss@Example.test")
    _answer_prompts(monkeypatch, PASSWORD, PASSWORD)

    code, stdout, _ = _run("create-admin", "--email", "boss@example.test")

    assert code == 1
    assert "grant-admin" in stdout
    user = _user(cli_environment, "boss@example.test")
    assert user is not None
    assert user.is_admin is False  # untouched
    assert _actions(cli_environment) == []


@pytest.mark.concurrency
def test_adr007_grant_admin_sets_the_flag_and_records_it(
    cli_environment: Engine,
) -> None:
    ola = _make_account(cli_environment, "ola@example.test")

    code, stdout, _ = _run("grant-admin", "--email", " OLA@example.test ")

    assert (code, stdout) == (0, "The account is now admin.\n")
    user = _user(cli_environment, "ola@example.test")
    assert user is not None
    assert user.is_admin is True
    assert user.updated_at is not None
    [action] = _actions(cli_environment)
    assert (
        action.source,
        action.action,
        action.admin_user_id,
        action.target_user_id,
    ) == (AdminActionSource.CLI, AdminActionKind.GRANT_ADMIN, None, ola)


@pytest.mark.concurrency
def test_adr007_granting_an_admin_again_changes_and_records_nothing(
    cli_environment: Engine,
) -> None:
    _make_account(cli_environment, "ola@example.test", is_admin=True)

    code, stdout, _ = _run("grant-admin", "--email", "ola@example.test")

    assert (code, stdout) == (0, "The account is already admin.\n")
    assert _actions(cli_environment) == []


@pytest.mark.concurrency
def test_adr007_revoke_admin_clears_the_flag_and_records_it(
    cli_environment: Engine,
) -> None:
    ola = _make_account(cli_environment, "ola@example.test", is_admin=True)

    code, stdout, _ = _run("revoke-admin", "--email", "ola@example.test")

    assert (code, stdout) == (0, "The account is now not an admin.\n")
    user = _user(cli_environment, "ola@example.test")
    assert user is not None
    assert user.is_admin is False
    [action] = _actions(cli_environment)
    assert (action.source, action.action, action.admin_user_id) == (
        AdminActionSource.CLI,
        AdminActionKind.REVOKE_ADMIN,
        None,
    )
    assert action.target_user_id == ola


@pytest.mark.concurrency
def test_adr007_revoking_a_non_admin_changes_and_records_nothing(
    cli_environment: Engine,
) -> None:
    _make_account(cli_environment, "ola@example.test")

    code, stdout, _ = _run("revoke-admin", "--email", "ola@example.test")

    assert (code, stdout) == (0, "The account is already not an admin.\n")
    assert _actions(cli_environment) == []


@pytest.mark.concurrency
@pytest.mark.parametrize("command", ["grant-admin", "revoke-admin"])
def test_adr007_an_unknown_email_is_refused(
    cli_environment: Engine, command: str
) -> None:
    code, stdout, _ = _run(command, "--email", "nobody@example.test")

    assert (code, stdout) == (1, "No account has that email.\n")
    assert _actions(cli_environment) == []


@pytest.mark.parametrize("command", ["create-admin", "grant-admin", "revoke-admin"])
def test_adr007_the_admin_commands_need_an_email(command: str) -> None:
    with redirect_stderr(io.StringIO()), pytest.raises(SystemExit) as raised:
        main([command])

    assert raised.value.code == 2
