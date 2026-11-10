import hashlib
import threading
import warnings
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid7

import httpx2
import jwt
import pytest
from argon2 import PasswordHasher
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from tourneyhub.app import create_app
from tourneyhub.db.models.accounts import AuthAttempt, RefreshToken, User
from tourneyhub.db.models.leagues import League
from tourneyhub.engine.accounts import Language
from tourneyhub.engine.auth import AuthAttemptKind
from tourneyhub.services import auth as auth_service
from tourneyhub.settings import Settings

PASSWORD = "a passphrase of 15 or more"
CUSTOM_HEADER = {"X-Requested-With": "tourneyhub"}


def _log_in(
    client: TestClient, email: str, password: str = PASSWORD
) -> httpx2.Response:
    return client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )


def _present(
    client: TestClient, path: str, token: str | None, *, custom_header: bool = True
) -> httpx2.Response:
    """POST to an auth route with exactly this refresh cookie, or none."""
    client.cookies.clear()
    headers = dict(CUSTOM_HEADER) if custom_header else {}
    if token is not None:
        headers["Cookie"] = f"refresh_token={token}"
    return client.post(path, headers=headers)


def _refresh(client: TestClient, token: str | None) -> httpx2.Response:
    return _present(client, "/api/v1/auth/refresh", token)


def _cookie(response: httpx2.Response) -> str:
    token: str = response.cookies["refresh_token"]
    return token


def _row(session: Session, token: str) -> RefreshToken:
    session.expire_all()  # the auth dependencies write through sessions of their own
    return session.scalars(
        select(RefreshToken).where(
            RefreshToken.token_hash == hashlib.sha256(token.encode()).digest()
        )
    ).one()


def _family(session: Session, family_id: UUID) -> list[RefreshToken]:
    session.expire_all()
    return list(
        session.scalars(
            select(RefreshToken)
            .where(RefreshToken.family_id == family_id)
            .order_by(RefreshToken.created_at, RefreshToken.id)
        )
    )


def _claims(access_token: str, settings: Settings) -> dict[str, object]:
    claims: dict[str, object] = jwt.decode(
        access_token,
        settings.jwt_secret.get_secret_value(),
        algorithms=["HS256"],
        options={"verify_exp": False, "verify_iat": False},
    )
    return claims


@pytest.fixture
def ana(make_user: Callable[..., User]) -> User:
    return make_user(email="ana@example.test", password=PASSWORD)


@pytest.fixture
def logged_in(client: TestClient, ana: User) -> str:
    """Log Ana in and return her refresh token."""
    response = _log_in(client, ana.email)
    assert response.status_code == 200
    return _cookie(response)


# Login


def test_adr006_login_returns_an_hs256_access_token_for_15_minutes(
    client: TestClient, ana: User, settings: Settings, session: Session, now: datetime
) -> None:
    response = _log_in(client, "Ana@Example.TEST")

    assert response.status_code == 200
    assert set(response.json()) == {"access_token"}
    access_token = response.json()["access_token"]
    assert jwt.get_unverified_header(access_token)["alg"] == "HS256"
    claims = _claims(access_token, settings)
    assert claims["sub"] == str(ana.id)
    assert claims["iat"] == int(now.timestamp())
    assert claims["exp"] == int((now + timedelta(minutes=15)).timestamp())
    assert claims["fid"] == str(_row(session, _cookie(response)).family_id)


def test_adr006_login_starts_a_family_with_a_256_bit_token_stored_as_its_hash(
    client: TestClient, ana: User, session: Session, now: datetime
) -> None:
    response = _log_in(client, ana.email)

    token = _cookie(response)
    assert len(token) == 43  # secrets.token_urlsafe(32): 256 bits
    row = _row(session, token)
    assert row.user_id == ana.id
    assert row.parent_id is None
    assert row.token_hash == hashlib.sha256(token.encode()).digest()
    assert row.expires_at == now + timedelta(days=90)
    assert (row.rotated_at, row.revoked_at) == (None, None)


def test_adr006_each_login_starts_its_own_family(
    client: TestClient, ana: User, session: Session
) -> None:
    first = _cookie(_log_in(client, ana.email))
    second = _cookie(_log_in(client, ana.email))

    assert _row(session, first).family_id != _row(session, second).family_id


def test_adr006_login_with_a_wrong_password_is_not_authenticated(
    client: TestClient, ana: User
) -> None:
    response = _log_in(client, ana.email, "a wrong passphrase, long")

    assert response.status_code == 401
    assert response.json() == {"code": "not_authenticated", "detail": {}}
    assert "set-cookie" not in response.headers


def test_adr006_login_with_an_unknown_email_answers_like_a_wrong_password(
    client: TestClient, ana: User
) -> None:
    wrong_password = _log_in(client, ana.email, "a wrong passphrase, long")
    unknown_email = _log_in(client, "nobody@example.test")

    assert unknown_email.status_code == wrong_password.status_code == 401
    assert unknown_email.json() == wrong_password.json()
    assert unknown_email.headers.keys() == wrong_password.headers.keys()


def test_adr006_a_failed_login_is_counted_although_its_transaction_rolls_back(
    client: TestClient, ana: User, session: Session, now: datetime
) -> None:
    _log_in(client, "Ana@Example.test", "a wrong passphrase, long")
    _log_in(client, ana.email)

    session.expire_all()
    attempts = session.execute(
        select(AuthAttempt.kind, AuthAttempt.key, AuthAttempt.succeeded).where(
            AuthAttempt.created_at == now
        )
    ).all()
    assert sorted(attempts) == [
        (AuthAttemptKind.LOGIN_EMAIL, "ana@example.test", False),
        (AuthAttemptKind.LOGIN_EMAIL, "ana@example.test", True),
        (AuthAttemptKind.LOGIN_IP, "testclient", False),
        (AuthAttemptKind.LOGIN_IP, "testclient", True),
    ]


def test_adr006_after_three_failures_login_answers_429_with_retry_after(
    client: TestClient, ana: User, session: Session
) -> None:
    for _ in range(3):
        _log_in(client, ana.email, "a wrong passphrase, long")

    response = _log_in(client, ana.email)  # the right password is not checked

    assert response.status_code == 429
    assert response.json() == {
        "code": "too_many_attempts",
        "detail": {"retry_after": 1},
    }
    assert response.headers["retry-after"] == "1"
    assert "set-cookie" not in response.headers
    session.expire_all()
    assert session.scalar(select(func.count()).select_from(AuthAttempt)) == 6


def test_adr006_login_rehashes_a_password_hashed_with_other_parameters(
    client: TestClient, make_user: Callable[..., User], session: Session, now: datetime
) -> None:
    weak = PasswordHasher(time_cost=1, memory_cost=8 * 1024, parallelism=1)
    user = make_user(password_hash=weak.hash(PASSWORD))

    response = _log_in(client, user.email)

    assert response.status_code == 200
    session.refresh(user)
    assert not PasswordHasher().check_needs_rehash(user.password_hash)
    assert PasswordHasher().verify(user.password_hash, PASSWORD)
    assert user.updated_at == now


def test_adr006_login_keeps_a_hash_with_the_current_parameters(
    client: TestClient, ana: User, session: Session
) -> None:
    before = ana.password_hash

    _log_in(client, ana.email)

    session.refresh(ana)
    assert ana.password_hash == before
    assert ana.updated_at is None


def test_adr006_login_succeeds_while_a_password_change_is_required(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    user = make_user(password=PASSWORD, must_change_password=True)

    response = _log_in(client, user.email)

    assert response.status_code == 200


# The refresh cookie


@pytest.mark.parametrize("secure", [True, False], ids=["secure", "development"])
def test_adr006_refresh_cookie_is_httponly_samesite_strict_on_the_auth_path(
    client: TestClient, ana: User, settings: Settings, secure: bool
) -> None:
    app = client.app
    assert isinstance(app, FastAPI)
    app.state.settings = settings.model_copy(update={"cookie_secure": secure})

    response = _log_in(client, ana.email)

    name_value, *attributes = response.headers["set-cookie"].split("; ")
    assert name_value == f"refresh_token={_cookie(response)}"
    expected = {"httponly", "max-age=7776000", "path=/api/v1/auth", "samesite=strict"}
    assert {attribute.lower() for attribute in attributes} == (
        expected | {"secure"} if secure else expected
    )


# Access tokens


def test_adr006_an_access_token_from_login_authenticates_api_calls(
    client: TestClient, ana: User
) -> None:
    access_token = _log_in(client, ana.email).json()["access_token"]

    response = client.get(
        f"/api/v1/leagues/{uuid7()}",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.json()["code"] == "league_not_found"  # authenticated, then 404


@pytest.mark.parametrize(
    ("age", "status", "code"),
    [
        pytest.param(
            timedelta(minutes=15) - timedelta(seconds=1), 404, None, id="valid"
        ),
        pytest.param(timedelta(minutes=15), 401, "token_expired", id="expired"),
    ],
)
def test_adr006_an_access_token_expires_after_15_minutes(
    client: TestClient,
    ana: User,
    auth_header: Callable[..., dict[str, str]],
    now: datetime,
    age: timedelta,
    status: int,
    code: str | None,
) -> None:
    response = client.get(
        f"/api/v1/leagues/{uuid7()}",
        headers=auth_header(ana.id, issued_at=now - age),
    )

    assert response.status_code == status
    if code is not None:
        assert response.json() == {"code": code, "detail": {}}


def _hs512(claims: dict[str, object], key: str) -> str:
    # The right key with another algorithm; PyJWT warns that it is short for HS512.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return jwt.encode(claims, key, algorithm="HS512")


def _forged(settings: Settings, now: datetime, user_id: UUID) -> dict[str, str]:
    claims = {
        "sub": str(user_id),
        "fid": str(uuid7()),
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }
    key = settings.jwt_secret.get_secret_value()
    return {
        "another-key": jwt.encode(claims, "y" * 32, algorithm="HS256"),
        "alg-none": jwt.encode(claims, None, algorithm="none"),
        "hs512": _hs512(claims, key),
        "sub-not-a-uuid": jwt.encode(claims | {"sub": "ana"}, key, algorithm="HS256"),
        "fid-missing": jwt.encode(
            {k: v for k, v in claims.items() if k != "fid"}, key, algorithm="HS256"
        ),
        "not-a-jwt": "not.a.jwt",
    }


@pytest.mark.parametrize(
    "kind",
    ["another-key", "alg-none", "hs512", "sub-not-a-uuid", "fid-missing", "not-a-jwt"],
)
def test_adr006_only_a_valid_hs256_access_token_is_accepted(
    client: TestClient, ana: User, settings: Settings, now: datetime, kind: str
) -> None:
    token = _forged(settings, now, ana.id)[kind]

    response = client.get(
        f"/api/v1/leagues/{uuid7()}", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 401
    assert response.json() == {"code": "not_authenticated", "detail": {}}


def test_adr006_an_access_token_of_a_deleted_user_is_not_authenticated(
    client: TestClient, auth_header: Callable[..., dict[str, str]]
) -> None:
    response = client.get(f"/api/v1/leagues/{uuid7()}", headers=auth_header(uuid7()))

    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"


def test_adr006_no_route_accepts_x_user_id_any_more(
    client: TestClient, make_league: Callable[..., League]
) -> None:
    app = client.app
    assert isinstance(app, FastAPI)
    league = make_league()

    response = client.get(
        f"/api/v1/leagues/{league.id}", headers={"X-User-Id": str(league.owner_user_id)}
    )

    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"
    parameters = [
        parameter["name"].lower()
        for path in app.openapi()["paths"].values()
        for operation in path.values()
        for parameter in operation.get("parameters", [])
    ]
    assert "x-user-id" not in parameters


# Refresh


def test_adr006_refresh_rotates_the_token_within_its_family(
    client: TestClient, logged_in: str, session: Session, settings: Settings
) -> None:
    response = _refresh(client, logged_in)

    assert response.status_code == 200
    new_token = _cookie(response)
    old, new = _row(session, logged_in), _row(session, new_token)
    assert old.rotated_at is not None
    assert new.parent_id == old.id
    assert new.family_id == old.family_id
    assert new.rotated_at is None
    assert _claims(response.json()["access_token"], settings)["fid"] == str(
        old.family_id
    )


def test_adr006_each_refresh_restarts_the_90_days(
    client: TestClient,
    logged_in: str,
    session: Session,
    travel: Callable[[timedelta], datetime],
) -> None:
    later = travel(timedelta(days=89))

    response = _refresh(client, logged_in)

    assert _row(session, _cookie(response)).expires_at == later + timedelta(days=90)


@pytest.mark.parametrize(
    "after",
    [pytest.param(timedelta(0), id="at-once"), pytest.param(timedelta(seconds=59))],
)
def test_adr006_a_token_rotated_less_than_60_seconds_ago_gets_another_token(
    client: TestClient,
    logged_in: str,
    session: Session,
    travel: Callable[[timedelta], datetime],
    now: datetime,
    after: timedelta,
) -> None:
    first = _cookie(_refresh(client, logged_in))
    travel(after)

    response = _refresh(client, logged_in)

    assert response.status_code == 200
    second = _cookie(response)
    presented = _row(session, logged_in)
    assert presented.rotated_at == now  # unchanged
    assert presented.revoked_at is None
    for token in (first, second):
        row = _row(session, token)
        assert (row.parent_id, row.revoked_at) == (presented.id, None)


def test_adr006_a_token_rotated_60_seconds_ago_is_reuse_and_revokes_the_family(
    client: TestClient,
    logged_in: str,
    session: Session,
    travel: Callable[[timedelta], datetime],
) -> None:
    newest = _cookie(_refresh(client, logged_in))
    detected_at = travel(timedelta(seconds=60))

    response = _refresh(client, logged_in)

    assert response.status_code == 401
    assert response.json() == {"code": "not_authenticated", "detail": {}}
    family = _family(session, _row(session, logged_in).family_id)
    assert len(family) == 2  # no token was issued
    assert {row.revoked_at for row in family} == {detected_at}
    assert _refresh(client, newest).status_code == 401


def test_adr006_reuse_detection_leaves_other_families_alone(
    client: TestClient,
    logged_in: str,
    ana: User,
    travel: Callable[[timedelta], datetime],
) -> None:
    other_device = _cookie(_log_in(client, ana.email))
    _refresh(client, logged_in)
    travel(timedelta(minutes=5))

    _refresh(client, logged_in)

    assert _refresh(client, other_device).status_code == 200


def test_adr006_a_normal_rotation_revokes_the_unrotated_siblings(
    client: TestClient,
    logged_in: str,
    session: Session,
    travel: Callable[[timedelta], datetime],
) -> None:
    first_child = _cookie(_refresh(client, logged_in))
    second_child = _cookie(_refresh(client, logged_in))  # within the window
    rotated_at = travel(timedelta(seconds=10))

    response = _refresh(client, second_child)

    assert response.status_code == 200
    assert _row(session, first_child).revoked_at == rotated_at
    assert _row(session, second_child).revoked_at is None
    assert _refresh(client, first_child).status_code == 401


def test_adr006_a_revoked_token_is_refused_even_within_the_window(
    client: TestClient, logged_in: str, session: Session
) -> None:
    _refresh(client, logged_in)
    _present(client, "/api/v1/auth/logout", logged_in)
    family_before = [
        (row.id, row.rotated_at, row.revoked_at)
        for row in _family(session, _row(session, logged_in).family_id)
    ]

    response = _refresh(client, logged_in)

    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"
    family_after = [
        (row.id, row.rotated_at, row.revoked_at)
        for row in _family(session, _row(session, logged_in).family_id)
    ]
    assert family_after == family_before


def test_adr006_an_expired_refresh_token_is_refused_and_changes_nothing(
    client: TestClient,
    logged_in: str,
    session: Session,
    travel: Callable[[timedelta], datetime],
) -> None:
    travel(timedelta(days=90))

    response = _refresh(client, logged_in)

    assert response.status_code == 401
    row = _row(session, logged_in)
    assert (row.rotated_at, row.revoked_at) == (None, None)
    assert len(_family(session, row.family_id)) == 1


@pytest.mark.parametrize(
    "token", [pytest.param(None, id="no-cookie"), pytest.param("x" * 43, id="unknown")]
)
def test_adr006_refresh_without_a_known_token_is_not_authenticated(
    client: TestClient, token: str | None
) -> None:
    response = _refresh(client, token)

    assert response.status_code == 401
    assert response.json() == {"code": "not_authenticated", "detail": {}}


@pytest.mark.parametrize("path", ["/api/v1/auth/refresh", "/api/v1/auth/logout"])
def test_adr006_cookie_routes_require_the_custom_header(
    client: TestClient, logged_in: str, session: Session, path: str
) -> None:
    response = _present(client, path, logged_in, custom_header=False)

    assert response.status_code == 422
    assert response.json()["detail"]["errors"] == [
        {"loc": ["header", "X-Requested-With"], "type": "missing"}
    ]
    row = _row(session, logged_in)
    assert (row.rotated_at, row.revoked_at) == (None, None)


# Logout


def test_adr006_logout_revokes_the_family_and_removes_the_cookie(
    client: TestClient, logged_in: str, session: Session, now: datetime
) -> None:
    newest = _cookie(_refresh(client, logged_in))

    response = _present(client, "/api/v1/auth/logout", newest)

    assert response.status_code == 204
    cookie = response.headers["set-cookie"].lower()
    assert cookie.startswith('refresh_token="";')
    assert "max-age=0" in cookie
    assert "path=/api/v1/auth" in cookie
    family = _family(session, _row(session, newest).family_id)
    assert {row.revoked_at for row in family} == {now}
    assert _refresh(client, newest).status_code == 401


def test_adr006_logout_keeps_the_time_of_an_earlier_revocation(
    client: TestClient,
    logged_in: str,
    session: Session,
    travel: Callable[[timedelta], datetime],
    now: datetime,
) -> None:
    sibling = _cookie(_refresh(client, logged_in))
    newest = _cookie(_refresh(client, _cookie(_refresh(client, logged_in))))
    logged_out_at = travel(timedelta(minutes=1))

    _present(client, "/api/v1/auth/logout", newest)

    assert _row(session, sibling).revoked_at == now
    assert _row(session, newest).revoked_at == logged_out_at


def test_adr006_logout_leaves_the_other_devices_logged_in(
    client: TestClient, logged_in: str, ana: User
) -> None:
    other_device = _cookie(_log_in(client, ana.email))

    _present(client, "/api/v1/auth/logout", logged_in)

    assert _refresh(client, other_device).status_code == 200


@pytest.mark.parametrize(
    "token", [pytest.param(None, id="no-cookie"), pytest.param("x" * 43, id="unknown")]
)
def test_adr006_logout_without_a_known_token_is_harmless(
    client: TestClient, token: str | None
) -> None:
    response = _present(client, "/api/v1/auth/logout", token)

    assert response.status_code == 204


# Locks and transactions on a real database (§9)


def _commit_login(engine: Engine, settings: Settings, at: datetime) -> str:
    with Session(engine) as setup:
        user = User(
            email=f"{uuid7()}@example.test",
            display_name="Racer",
            password_hash=auth_service.hash_password(PASSWORD),
            language=Language.EN,
            created_at=at,
        )
        setup.add(user)
        setup.flush()
        attempt = auth_service.start_login_attempt(
            setup, email=user.email, ip="192.0.2.1", now=at
        )
        tokens = auth_service.log_in(
            setup,
            attempt=attempt,
            email=user.email,
            password=PASSWORD,
            key=settings.jwt_secret,
            now=at,
        )
        setup.commit()
    return tokens.refresh_token


def _committed_row(engine: Engine, token: str) -> RefreshToken:
    with Session(engine) as reader:
        return reader.scalars(
            select(RefreshToken).where(
                RefreshToken.token_hash == hashlib.sha256(token.encode()).digest()
            )
        ).one()


@pytest.mark.concurrency
def test_adr006_refresh_waits_for_the_family_lock_and_then_sees_the_rotation(
    committing_settings: Settings,
    committing_engine: Engine,
    wait_for_a_lock_wait: Callable[[], None],
) -> None:
    rotated_at = datetime.now(UTC)
    token = _commit_login(committing_engine, committing_settings, rotated_at)
    outcome: list[int] = []

    with (
        Session(committing_engine) as first,
        TestClient(create_app(committing_settings)) as client,
    ):
        auth_service.refresh_session(
            first,
            refresh_token=token,
            key=committing_settings.jwt_secret,
            now=rotated_at,
        )

        def present_again() -> None:
            outcome.append(_refresh(client, token).status_code)

        second = threading.Thread(target=present_again)
        second.start()
        wait_for_a_lock_wait()  # the second presentation waits for the first
        first.commit()
        second.join()

    assert outcome == [200]  # within the window
    presented = _committed_row(committing_engine, token)
    assert presented.rotated_at == rotated_at  # the second did not rotate it again


@pytest.mark.concurrency
def test_adr006_logout_racing_a_refresh_also_revokes_the_token_it_issued(
    committing_settings: Settings,
    committing_engine: Engine,
    wait_for_a_lock_wait: Callable[[], None],
) -> None:
    at = datetime.now(UTC)
    token = _commit_login(committing_engine, committing_settings, at)
    outcome: list[int] = []

    with (
        Session(committing_engine) as refreshing,
        TestClient(create_app(committing_settings)) as client,
    ):
        issued = auth_service.refresh_session(
            refreshing, refresh_token=token, key=committing_settings.jwt_secret, now=at
        )
        assert issued is not None

        def log_out() -> None:
            outcome.append(_present(client, "/api/v1/auth/logout", token).status_code)

        logout = threading.Thread(target=log_out)
        logout.start()
        # The logout's locking statement waits and cannot see the new token;
        # only its second statement does.
        wait_for_a_lock_wait()
        refreshing.commit()
        logout.join()

    assert outcome == [204]
    assert (
        _committed_row(committing_engine, issued.refresh_token).revoked_at is not None
    )


@pytest.mark.concurrency
def test_adr006_reuse_revokes_the_family_in_the_refreshs_own_transaction(
    committing_settings: Settings, committing_engine: Engine
) -> None:
    logged_in_at = datetime.now(UTC) - timedelta(minutes=5)
    token = _commit_login(committing_engine, committing_settings, logged_in_at)
    with Session(committing_engine) as earlier:
        auth_service.refresh_session(
            earlier,
            refresh_token=token,
            key=committing_settings.jwt_secret,
            now=logged_in_at,
        )
        earlier.commit()

    # lock_timeout: a revocation waiting for locks of its own request fails.
    with TestClient(create_app(committing_settings)) as client:
        response = _refresh(client, token)

    assert response.status_code == 401
    assert response.json() == {"code": "not_authenticated", "detail": {}}
    family_id = _committed_row(committing_engine, token).family_id
    with Session(committing_engine) as reader:
        revoked = reader.scalars(
            select(RefreshToken.revoked_at).where(RefreshToken.family_id == family_id)
        ).all()
    assert len(revoked) == 2
    assert None not in revoked


@pytest.mark.concurrency
def test_adr006_a_login_waits_for_a_parallel_attempt_and_counts_it(
    committing_settings: Settings,
    committing_engine: Engine,
    wait_for_a_lock_wait: Callable[[], None],
) -> None:
    at = datetime.now(UTC)
    email = f"{uuid7()}@example.test"
    with Session(committing_engine) as earlier:
        for number in range(2):
            auth_service.start_login_attempt(
                earlier, email=email, ip=f"192.0.2.{number}", now=at
            )
        earlier.commit()
    outcome: list[tuple[int, str | None]] = []

    with (
        Session(committing_engine) as parallel,
        TestClient(create_app(committing_settings)) as client,
    ):
        auth_service.start_login_attempt(  # the third, not committed yet
            parallel, email=email, ip="192.0.2.9", now=at
        )

        def log_in() -> None:
            response = _log_in(client, email)
            outcome.append((response.status_code, response.headers.get("retry-after")))

        login = threading.Thread(target=log_in)
        login.start()
        wait_for_a_lock_wait()
        parallel.commit()
        login.join()

    assert outcome == [(429, "1")]  # it counted the third failure


@pytest.mark.concurrency
def test_adr006_a_burst_of_parallel_logins_checks_only_the_free_attempts(
    committing_settings: Settings, committing_engine: Engine
) -> None:
    email = f"{uuid7()}@example.test"
    statuses: list[int] = []

    with TestClient(create_app(committing_settings)) as client:

        def log_in() -> None:
            statuses.append(_log_in(client, email).status_code)

        burst = [threading.Thread(target=log_in) for _ in range(6)]
        for login in burst:
            login.start()
        for login in burst:
            login.join()

    assert sorted(statuses) == [401, 401, 401, 429, 429, 429]
    with Session(committing_engine) as reader:
        counted = reader.scalar(
            select(func.count())
            .select_from(AuthAttempt)
            .where(AuthAttempt.kind == AuthAttemptKind.LOGIN_EMAIL)
        )
    assert counted == 3
