import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid7

import httpx2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from tourneyhub.api.schemas import MIN_PASSWORD_LENGTH
from tourneyhub.app import create_app
from tourneyhub.db.models.accounts import RefreshToken, User
from tourneyhub.engine.accounts import Language
from tourneyhub.services import accounts as account_service
from tourneyhub.services import auth as auth_service
from tourneyhub.settings import Settings

PASSWORD = "correct horse battery staple"
NEW_PASSWORD = "a brand new passphrase"
CUSTOM_HEADER = {"X-Requested-With": "tourneyhub"}


def _change(
    client: TestClient,
    headers: dict[str, str],
    *,
    current: str = PASSWORD,
    new: str = NEW_PASSWORD,
) -> httpx2.Response:
    return client.post(
        "/api/v1/auth/password",
        json={"current_password": current, "new_password": new},
        headers=headers,
    )


def _log_in(
    client: TestClient, user: User, password: str = PASSWORD
) -> httpx2.Response:
    client.cookies.clear()
    return client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": password}
    )


def _bearer(response: httpx2.Response) -> dict[str, str]:
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _refresh(client: TestClient, response: httpx2.Response) -> int:
    client.cookies.clear()
    return client.post(
        "/api/v1/auth/refresh",
        headers=CUSTOM_HEADER
        | {"Cookie": f"refresh_token={response.cookies['refresh_token']}"},
    ).status_code


@pytest.fixture
def ana(make_user: Callable[..., User]) -> User:
    return make_user(email="ana@example.test", password=PASSWORD)


def test_fr004_changing_the_password_replaces_it(
    client: TestClient, ana: User, session: Session, now: datetime
) -> None:
    device = _log_in(client, ana)

    response = _change(client, _bearer(device))

    assert response.status_code == 204
    assert response.content == b""
    session.refresh(ana)
    assert auth_service.verify_password(ana.password_hash, NEW_PASSWORD)
    assert not auth_service.verify_password(ana.password_hash, PASSWORD)
    assert ana.updated_at == now
    assert _log_in(client, ana, NEW_PASSWORD).status_code == 200
    assert _log_in(client, ana, PASSWORD).status_code == 401


def test_adr006_a_password_change_revokes_the_other_devices_and_keeps_this_one(
    client: TestClient, ana: User, make_user: Callable[..., User], session: Session
) -> None:
    this_device = _log_in(client, ana)
    phone = _log_in(client, ana)
    tablet = _log_in(client, ana)
    stranger = make_user()
    strangers_login = _log_in(client, stranger)

    _change(client, _bearer(this_device))

    assert _refresh(client, this_device) == 200
    assert _refresh(client, phone) == 401
    assert _refresh(client, tablet) == 401
    assert _refresh(client, strangers_login) == 200
    session.expire_all()
    revoked = session.scalars(
        select(RefreshToken.revoked_at).where(RefreshToken.user_id == ana.id)
    ).all()
    assert sum(at is not None for at in revoked) == 2  # the phone and the tablet


def test_adr006_a_password_change_keeps_the_time_of_an_earlier_revocation(
    client: TestClient, ana: User, session: Session, now: datetime
) -> None:
    this_device = _log_in(client, ana)
    gone = _log_in(client, ana)
    client.post(
        "/api/v1/auth/logout",
        headers=CUSTOM_HEADER
        | {"Cookie": f"refresh_token={gone.cookies['refresh_token']}"},
    )
    session.expire_all()
    earlier = now - timedelta(hours=1)
    for token in session.scalars(
        select(RefreshToken).where(RefreshToken.revoked_at.is_not(None))
    ):
        token.revoked_at = earlier
    session.flush()

    _change(client, _bearer(this_device))

    session.expire_all()
    assert session.scalars(
        select(RefreshToken.revoked_at).where(RefreshToken.revoked_at.is_not(None))
    ).all() == [earlier]


def test_fr004_a_wrong_current_password_changes_nothing(
    client: TestClient, ana: User, session: Session
) -> None:
    this_device = _log_in(client, ana)
    phone = _log_in(client, ana)

    response = _change(client, _bearer(this_device), current="not my password at all")

    assert response.status_code == 422
    assert response.json() == {"code": "wrong_password", "detail": {}}
    session.refresh(ana)
    assert auth_service.verify_password(ana.password_hash, PASSWORD)
    assert ana.updated_at is None
    assert _refresh(client, phone) == 200


def test_fr004_a_wrong_current_password_is_not_a_401_that_would_log_the_spa_out(
    client: TestClient, ana: User
) -> None:
    response = _change(
        client, _bearer(_log_in(client, ana)), current="wrong wrong wrong"
    )

    assert response.status_code != 401


@pytest.mark.parametrize("length", [MIN_PASSWORD_LENGTH - 1, 1025])
def test_fr002_the_new_password_follows_the_sign_up_rules(
    client: TestClient, ana: User, session: Session, length: int
) -> None:
    response = _change(client, _bearer(_log_in(client, ana)), new="x" * length)

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_failed"
    assert [(e["loc"], e["type"]) for e in body["detail"]["errors"]] == [
        (["body", "new_password"], "too_short" if length < 100 else "too_long")
    ]
    session.refresh(ana)
    assert auth_service.verify_password(ana.password_hash, PASSWORD)


def test_fr002_a_new_password_of_the_minimum_length_is_accepted(
    client: TestClient, ana: User
) -> None:
    response = _change(
        client, _bearer(_log_in(client, ana)), new="x" * MIN_PASSWORD_LENGTH
    )

    assert response.status_code == 204


def test_adr006_the_new_password_must_differ_from_the_current_one(
    client: TestClient, ana: User
) -> None:
    response = _change(client, _bearer(_log_in(client, ana)), new=PASSWORD)

    assert response.status_code == 422
    assert response.json() == {"code": "password_unchanged", "detail": {}}


def test_fr004_an_account_without_a_usable_hash_cannot_pass_the_current_password_check(
    client: TestClient,
    make_user: Callable[..., User],
    auth_header: Callable[..., dict[str, str]],
) -> None:
    user = make_user(password_hash="!")

    response = _change(client, auth_header(user.id), current="!")

    assert response.status_code == 422
    assert response.json()["code"] == "wrong_password"


def test_adr006_a_password_change_ends_the_required_change_after_an_admin_reset(
    client: TestClient,
    make_user: Callable[..., User],
    session: Session,
) -> None:
    user = make_user(password=PASSWORD, must_change_password=True)
    headers = _bearer(_log_in(client, user))
    assert (
        client.get("/api/v1/leagues/" + str(uuid7()), headers=headers).json()["code"]
        == "password_change_required"
    )

    response = _change(client, headers)

    assert response.status_code == 204
    session.refresh(user)
    assert user.must_change_password is False
    league = client.get("/api/v1/leagues/" + str(uuid7()), headers=headers)
    assert league.json()["code"] == "league_not_found"


def test_adr006_a_password_change_needs_an_access_token(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/password",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"


def test_adr006_a_password_change_with_an_expired_token_is_token_expired(
    client: TestClient,
    ana: User,
    auth_header: Callable[..., dict[str, str]],
    now: datetime,
) -> None:
    stale = auth_header(ana.id, issued_at=now - timedelta(minutes=16))

    response = _change(client, stale)

    assert response.status_code == 401
    assert response.json()["code"] == "token_expired"


def test_adr006_a_password_change_for_a_deleted_user_is_not_authenticated(
    client: TestClient, auth_header: Callable[..., dict[str, str]]
) -> None:
    response = _change(client, auth_header(uuid7()))

    assert response.status_code == 401


def test_adr006_a_request_cannot_name_another_user(
    client: TestClient, ana: User, make_user: Callable[..., User]
) -> None:
    other = make_user(email="bob@example.test")

    response = client.post(
        "/api/v1/auth/password",
        json={
            "current_password": PASSWORD,
            "new_password": NEW_PASSWORD,
            "user_id": str(other.id),
        },
        headers=_bearer(_log_in(client, ana)),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["errors"][0]["type"] == "extra_forbidden"


# Races


@pytest.mark.concurrency
def test_adr006_a_password_change_racing_a_refresh_also_revokes_the_token_it_issued(
    committing_settings: Settings,
    committing_engine: Engine,
    wait_for_a_lock_wait: Callable[[], None],
) -> None:
    at = datetime.now(UTC)
    key = committing_settings.jwt_secret
    with Session(committing_engine) as setup:
        user = User(
            email=f"{uuid7()}@example.test",
            display_name="Racer",
            password_hash=auth_service.hash_password(PASSWORD),
            language=Language.EN,
            created_at=at,
        )
        setup.add(user)
        setup.flush()
        user_id = user.id
        this_device = auth_service.start_session(
            setup, user_id=user_id, key=key, now=at
        )
        phone = auth_service.start_session(setup, user_id=user_id, key=key, now=at)
        setup.commit()
    keep = auth_service.read_access_token(this_device.access_token, key=key, now=at)

    with (
        Session(committing_engine) as refreshing,
        Session(committing_engine) as changing,
        TestClient(create_app(committing_settings)) as client,
    ):
        issued = auth_service.refresh_session(
            refreshing, refresh_token=phone.refresh_token, key=key, now=at
        )
        assert issued is not None

        def change_password() -> None:
            account_service.change_password(
                changing,
                user=changing.get_one(User, user_id),
                keep_family_id=keep.family_id,
                current_password=PASSWORD,
                new_password=NEW_PASSWORD,
                now=at,
            )
            changing.commit()

        change = threading.Thread(target=change_password)
        change.start()
        # The change waits for the refresh's locks on the phone's family and
        # cannot see the token the refresh added; only its second pass does.
        wait_for_a_lock_wait()
        refreshing.commit()
        change.join()
        client.cookies.clear()
        outcomes = [
            client.post(
                "/api/v1/auth/refresh",
                headers=CUSTOM_HEADER | {"Cookie": f"refresh_token={token}"},
            ).status_code
            for token in (
                issued.refresh_token,
                phone.refresh_token,
                this_device.refresh_token,
            )
        ]

    assert outcomes == [401, 401, 200]
    with Session(committing_engine) as reader:
        families = reader.scalars(
            select(RefreshToken.family_id).where(
                RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
            )
        ).all()
        assert UUID(str(keep.family_id)) in families
