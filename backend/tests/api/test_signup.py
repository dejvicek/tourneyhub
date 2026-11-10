import threading
import unicodedata
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Literal

import httpx2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from tourneyhub.app import create_app
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

CODE = "Thursday-foosball"
PASSWORD = "a passphrase of 15 or more"
CUSTOM_HEADER = {"X-Requested-With": "tourneyhub"}


def _sign_up(client: TestClient, *, code: str = CODE, **fields: str) -> httpx2.Response:
    body = {
        "signup_code": code,
        "email": "new@example.test",
        "display_name": "New Organizer",
        "password": PASSWORD,
    } | fields
    return client.post("/api/v1/auth/signup", json=body)


@pytest.fixture
def open_signup(set_signup_code: Callable[[str | None], None]) -> None:
    set_signup_code(CODE)


def _user_count(session: Session) -> int:
    session.expire_all()
    return session.scalar(select(func.count()).select_from(User)) or 0


# Success


@pytest.mark.usefixtures("open_signup")
def test_fr001_signing_up_with_the_code_creates_the_account_and_logs_in(
    client: TestClient, session: Session, settings: Settings, now: datetime
) -> None:
    response = _sign_up(client, display_name="  Ana Nováková ")

    assert response.status_code == 201
    assert set(response.json()) == {"access_token"}
    user = session.scalars(select(User)).one()
    assert (user.email, user.display_name) == ("new@example.test", "Ana Nováková")
    assert (user.language, user.is_admin, user.must_change_password) == (
        Language.EN,
        False,
        False,
    )
    assert user.created_at == now
    assert auth_service.verify_password(user.password_hash, PASSWORD)
    assert "PASSWORD" not in response.text
    claims = auth_service.read_access_token(
        response.json()["access_token"], key=settings.jwt_secret, now=now
    )
    assert claims.user_id == user.id


@pytest.mark.usefixtures("open_signup")
def test_fr001_signing_up_starts_a_login_like_a_login_does(
    client: TestClient, session: Session, now: datetime
) -> None:
    response = _sign_up(client)

    set_cookie = response.headers["set-cookie"]
    assert "HttpOnly" in set_cookie
    assert "SameSite=strict" in set_cookie
    assert "Path=/api/v1/auth" in set_cookie
    token = session.scalars(select(RefreshToken)).one()
    assert token.parent_id is None
    assert token.expires_at == now + timedelta(days=90)
    refreshed = client.post("/api/v1/auth/refresh", headers=CUSTOM_HEADER)
    assert refreshed.status_code == 200


@pytest.mark.usefixtures("open_signup")
def test_fr081_a_new_account_remembers_the_language_it_signed_up_in(
    client: TestClient, session: Session
) -> None:
    response = _sign_up(client, language="cs")

    assert response.status_code == 201
    assert session.scalars(select(User.language)).one() == Language.CS


@pytest.mark.usefixtures("open_signup")
def test_fr001_the_new_account_can_log_in(client: TestClient) -> None:
    _sign_up(client, email="Ana@Example.test")
    client.cookies.clear()

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "ana@example.test", "password": PASSWORD},
    )

    assert response.status_code == 200


# The code


def test_adr007_sign_up_is_closed_until_a_code_is_set(
    client: TestClient, session: Session
) -> None:
    response = _sign_up(client)

    assert response.status_code == 422
    assert response.json() == {"code": "invalid_signup_code", "detail": {}}
    assert "set-cookie" not in response.headers
    assert _user_count(session) == 0


def test_adr007_closed_sign_up_refuses_an_empty_code_too(
    client: TestClient, session: Session
) -> None:
    response = _sign_up(client, code="")

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_signup_code"
    assert _user_count(session) == 0


@pytest.mark.usefixtures("open_signup")
@pytest.mark.parametrize(
    "wrong", ["", "thursday-foosball", "Thursday-foosbal", CODE * 2]
)
def test_fr001_a_wrong_code_is_refused_like_closed_sign_up(
    client: TestClient, session: Session, wrong: str
) -> None:
    response = _sign_up(client, code=wrong)

    assert response.status_code == 422
    assert response.json() == {"code": "invalid_signup_code", "detail": {}}
    assert _user_count(session) == 0


def test_fr001_a_code_with_czech_letters_works_and_a_wrong_one_is_refused(
    client: TestClient, session: Session, set_signup_code: Callable[[str | None], None]
) -> None:
    set_signup_code("Žluťoučký kůň")

    wrong = _sign_up(client, code="Zlutoucky kun")
    other_letter = _sign_up(client, code="Žluťoučký kůŇ")
    right = _sign_up(client, code="Žluťoučký kůň")

    assert (wrong.status_code, other_letter.status_code) == (422, 422)
    assert right.status_code == 201
    assert _user_count(session) == 1


def test_fr001_a_non_ascii_code_against_an_ascii_one_is_refused_not_a_500(
    client: TestClient, set_signup_code: Callable[[str | None], None]
) -> None:
    set_signup_code(CODE)

    response = _sign_up(client, code="Thursday-foosball-ž")

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_signup_code"


@pytest.mark.parametrize(
    ("stored_form", "given_form"), [("NFC", "NFD"), ("NFD", "NFC")]
)
def test_fr001_a_letter_typed_as_a_base_letter_and_a_mark_matches_the_composed_one(
    client: TestClient,
    set_signup_code: Callable[[str | None], None],
    stored_form: Literal["NFC", "NFD"],
    given_form: Literal["NFC", "NFD"],
) -> None:
    code = "Žluťoučký kůň"
    set_signup_code(unicodedata.normalize(stored_form, code))
    typed = unicodedata.normalize(given_form, code)
    assert typed != unicodedata.normalize(stored_form, code)

    response = _sign_up(client, code=typed)

    assert response.status_code == 201


def test_fr001_a_different_letter_still_does_not_match_after_normalizing(
    client: TestClient, set_signup_code: Callable[[str | None], None]
) -> None:
    set_signup_code("Žluťoučký kůň")

    response = _sign_up(client, code=unicodedata.normalize("NFD", "Zluťoučký kůň"))

    assert response.status_code == 422


def test_fr001_spaces_around_the_code_are_ignored(
    client: TestClient, set_signup_code: Callable[[str | None], None]
) -> None:
    set_signup_code(CODE)

    response = _sign_up(client, code=f"  {CODE}\n")

    assert response.status_code == 201


@pytest.mark.usefixtures("open_signup")
def test_fr005_changing_the_code_leaves_existing_accounts_alone(
    client: TestClient,
    session: Session,
    set_signup_code: Callable[[str | None], None],
) -> None:
    _sign_up(client)

    set_signup_code("another code")

    assert _user_count(session) == 1
    assert _sign_up(client, email="other@example.test").status_code == 422


# The email


@pytest.mark.usefixtures("open_signup")
@pytest.mark.parametrize("again", ["new@example.test", "NEW@Example.TEST"])
def test_fr002_an_email_belongs_to_one_account_in_any_letter_case(
    client: TestClient, session: Session, again: str
) -> None:
    _sign_up(client)

    response = _sign_up(client, email=again)

    assert response.status_code == 422
    assert response.json() == {"code": "email_taken", "detail": {}}
    assert _user_count(session) == 1


@pytest.mark.usefixtures("open_signup")
def test_fr002_an_email_taken_by_an_admin_is_taken_too(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="boss@example.test", is_admin=True)

    response = _sign_up(client, email="Boss@example.test")

    assert response.json()["code"] == "email_taken"


@pytest.mark.usefixtures("open_signup")
def test_adr006_the_code_is_checked_before_the_email_so_a_stranger_learns_nothing(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="ana@example.test")

    response = _sign_up(client, code="wrong", email="ana@example.test")

    assert response.json()["code"] == "invalid_signup_code"


# Validation


@pytest.mark.usefixtures("open_signup")
@pytest.mark.parametrize(
    ("fields", "loc", "error_type"),
    [
        pytest.param({"password": "x" * 14}, "password", "too_short", id="short"),
        pytest.param({"password": "x" * 1025}, "password", "too_long", id="long"),
        pytest.param(
            {"display_name": "   "}, "display_name", "string_too_short", id="blank-name"
        ),
        pytest.param(
            {"display_name": "x" * 101},
            "display_name",
            "string_too_long",
            id="long-name",
        ),
        pytest.param(
            {"email": "no-at-sign"}, "email", "string_pattern_mismatch", id="no-at"
        ),
        pytest.param(
            {"email": "two@@example.test"},
            "email",
            "string_pattern_mismatch",
            id="two-ats",
        ),
        pytest.param(
            {"email": "a b@example.test"},
            "email",
            "string_pattern_mismatch",
            id="space",
        ),
        pytest.param(
            {"email": "ana@localhost"}, "email", "string_pattern_mismatch", id="no-dot"
        ),
        pytest.param(
            {"email": f"{'a' * 320}@example.test"},
            "email",
            "string_too_long",
            id="long-email",
        ),
        pytest.param({"language": "de"}, "language", "enum", id="language"),
        pytest.param(
            {"signup_code": "x" * 257}, "signup_code", "too_long", id="long-code"
        ),
        pytest.param({"is_admin": "yes"}, "is_admin", "extra_forbidden", id="extra"),
    ],
)
def test_fr001_an_invalid_request_is_refused_and_not_counted_as_an_attempt(
    client: TestClient,
    session: Session,
    fields: dict[str, str],
    loc: str,
    error_type: str,
) -> None:
    response = _sign_up(client, **fields)

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_failed"
    assert [(e["loc"], e["type"]) for e in body["detail"]["errors"]] == [
        (["body", loc], error_type)
    ]
    assert _user_count(session) == 0
    assert session.scalar(select(func.count()).select_from(AuthAttempt)) == 0


@pytest.mark.usefixtures("open_signup")
def test_fr002_a_password_of_15_characters_is_enough(client: TestClient) -> None:
    assert _sign_up(client, password="x" * 15).status_code == 201


@pytest.mark.usefixtures("open_signup")
def test_fr002_the_password_is_counted_in_characters_not_bytes(
    client: TestClient,
) -> None:
    assert _sign_up(client, password="ž" * 14).status_code == 422
    assert _sign_up(client, password="ž" * 15).status_code == 201


@pytest.mark.usefixtures("open_signup")
def test_fr001_a_password_is_never_echoed_in_an_error(client: TestClient) -> None:
    response = _sign_up(client, password="hunter2-short")

    assert response.status_code == 422
    assert "hunter2" not in response.text


# The throttle


def _attempts(session: Session) -> list[tuple[AuthAttemptKind, str, bool]]:
    session.expire_all()
    return sorted(
        session.execute(
            select(AuthAttempt.kind, AuthAttempt.key, AuthAttempt.succeeded)
        ).all()
    )


@pytest.mark.usefixtures("open_signup")
def test_adr006_a_failed_and_a_successful_sign_up_are_counted_per_ip(
    client: TestClient, session: Session
) -> None:
    _sign_up(client, code="wrong")
    _sign_up(client)

    assert _attempts(session) == [
        (AuthAttemptKind.SIGNUP_IP, "testclient", False),
        (AuthAttemptKind.SIGNUP_IP, "testclient", True),
    ]


@pytest.mark.usefixtures("open_signup")
def test_adr006_after_five_wrong_codes_sign_up_answers_429_with_retry_after(
    client: TestClient, session: Session
) -> None:
    for _ in range(5):
        assert _sign_up(client, code="wrong").status_code == 422

    response = _sign_up(client)  # the right code is not checked

    assert response.status_code == 429
    assert response.json() == {
        "code": "too_many_attempts",
        "detail": {"retry_after": 1},
    }
    assert response.headers["retry-after"] == "1"
    assert "set-cookie" not in response.headers
    assert _user_count(session) == 0
    assert len(_attempts(session)) == 5  # the refused attempt is not counted


@pytest.mark.usefixtures("open_signup")
def test_adr006_the_sign_up_limit_ends_after_its_waiting_period(
    client: TestClient, travel: Callable[[timedelta], datetime]
) -> None:
    for _ in range(5):
        _sign_up(client, code="wrong")
    assert _sign_up(client).status_code == 429

    travel(timedelta(seconds=1))

    assert _sign_up(client).status_code == 201


@pytest.mark.usefixtures("open_signup")
def test_adr006_failed_logins_do_not_use_up_the_sign_up_limit(
    client: TestClient,
) -> None:
    for _ in range(6):
        client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.test", "password": "a wrong passphrase"},
        )

    assert _sign_up(client).status_code == 201


@pytest.mark.usefixtures("open_signup")
def test_adr006_a_taken_email_counts_as_a_failed_attempt(
    client: TestClient, session: Session
) -> None:
    _sign_up(client)
    _sign_up(client)

    assert _attempts(session) == [
        (AuthAttemptKind.SIGNUP_IP, "testclient", False),
        (AuthAttemptKind.SIGNUP_IP, "testclient", True),
    ]


# Races


@pytest.fixture
def committed_signup_code(committing_engine: Engine) -> Iterator[None]:
    with Session(committing_engine) as setup:
        setup.get_one(InstanceSettings, 1).signup_code = CODE
        setup.commit()
    yield
    with committing_engine.begin() as connection:
        connection.execute(text("UPDATE instance_settings SET signup_code = NULL"))


@pytest.mark.concurrency
@pytest.mark.usefixtures("committed_signup_code")
def test_fr002_two_parallel_sign_ups_with_one_email_leave_one_account_and_a_409(
    committing_settings: Settings,
    committing_engine: Engine,
    wait_for_a_lock_wait: Callable[[], None],
) -> None:
    outcome: list[httpx2.Response] = []

    with (
        Session(committing_engine) as first,
        TestClient(create_app(committing_settings)) as client,
    ):
        first.add(
            User(
                email="race@example.test",
                display_name="First",
                password_hash=auth_service.hash_password(PASSWORD),
                language=Language.EN,
                created_at=datetime.now(UTC),
            )
        )
        first.flush()  # inserted, not committed: the second does not see it

        def second_sign_up() -> None:
            outcome.append(_sign_up(client, email="Race@example.test"))

        second = threading.Thread(target=second_sign_up)
        second.start()
        wait_for_a_lock_wait()  # the unique index makes it wait for the first
        first.commit()
        second.join()

    assert [(r.status_code, r.json()["code"]) for r in outcome] == [
        (409, "email_taken")
    ]
