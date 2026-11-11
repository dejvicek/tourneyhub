import re
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid7

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from tourneyhub.app import create_app
from tourneyhub.db.models.accounts import (
    AdminAction,
    InstanceSettings,
    RefreshToken,
    User,
)
from tourneyhub.engine.accounts import Language
from tourneyhub.engine.admin import AdminActionKind, AdminActionSource
from tourneyhub.services import auth as auth_service
from tourneyhub.services.instance import (
    SIGNUP_CODE_MAX_LENGTH,
    SIGNUP_CODE_MIN_LENGTH,
)
from tourneyhub.settings import Settings

PASSWORD = "correct horse battery staple"
TEMPORARY = "a temporary passphrase"
CODE = "Žluťoučký-kůň-2026"
ADMIN_ROUTES = [
    ("GET", "/api/v1/admin/signup-code"),
    ("PUT", "/api/v1/admin/signup-code"),
    ("POST", "/api/v1/admin/signup-code/generate"),
    ("GET", "/api/v1/admin/organizers"),
    ("POST", "/api/v1/admin/organizers/{user_id}/password-reset"),
]
_BODIES: dict[str, dict[str, object]] = {
    "PUT": {"signup_code": CODE},
    "POST": {},
}


@pytest.fixture
def admin(make_user: Callable[..., User]) -> User:
    return make_user(email="boss@example.test", is_admin=True)


@pytest.fixture
def admin_headers(
    admin: User, auth_header: Callable[..., dict[str, str]]
) -> dict[str, str]:
    return auth_header(admin.id)


def _actions(session: Session) -> list[AdminAction]:
    session.flush()
    return list(session.scalars(select(AdminAction).order_by(AdminAction.id)).all())


def _stored_code(session: Session) -> str | None:
    session.expire_all()
    return session.get_one(InstanceSettings, 1).signup_code


def _reset(
    client: TestClient,
    headers: dict[str, str],
    user: User,
    **body: object,
) -> httpx2.Response:
    return client.post(
        f"/api/v1/admin/organizers/{user.id}/password-reset",
        json=body,
        headers=headers,
    )


def _log_in(client: TestClient, user: User, password: str) -> httpx2.Response:
    client.cookies.clear()
    return client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": password}
    )


# --- who may call ---------------------------------------------------------


@pytest.mark.parametrize(("method", "path"), ADMIN_ROUTES)
def test_adr007_an_admin_route_needs_a_token(
    client: TestClient, method: str, path: str
) -> None:
    response = client.request(
        method, path.format(user_id=uuid7()), json=_BODIES.get(method)
    )

    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"


@pytest.mark.parametrize(("method", "path"), ADMIN_ROUTES)
def test_adr007_an_organizer_gets_403_on_every_admin_route(
    client: TestClient,
    make_user: Callable[..., User],
    auth_header: Callable[..., dict[str, str]],
    session: Session,
    method: str,
    path: str,
) -> None:
    organizer = make_user()

    response = client.request(
        method,
        path.format(user_id=uuid7()),
        json=_BODIES.get(method),
        headers=auth_header(organizer.id),
    )

    assert response.status_code == 403
    assert response.json() == {"code": "forbidden", "detail": {}}
    assert _actions(session) == []
    assert _stored_code(session) is None


@pytest.mark.parametrize(("method", "path"), ADMIN_ROUTES)
def test_adr006_an_admin_with_a_required_new_password_gets_403_on_admin_routes(
    client: TestClient,
    make_user: Callable[..., User],
    auth_header: Callable[..., dict[str, str]],
    method: str,
    path: str,
) -> None:
    admin = make_user(is_admin=True, must_change_password=True)

    response = client.request(
        method,
        path.format(user_id=uuid7()),
        json=_BODIES.get(method),
        headers=auth_header(admin.id),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "password_change_required"


def test_adr007_every_route_under_admin_is_in_the_list_the_tests_cover(
    client: TestClient,
) -> None:
    app = client.app
    assert isinstance(app, FastAPI)
    routes = {
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        if path.startswith("/api/v1/admin")
        for method in operations
    }

    assert routes == set(ADMIN_ROUTES)


def test_adr007_the_admin_flag_is_read_from_the_row_not_the_token(
    client: TestClient,
    admin: User,
    admin_headers: dict[str, str],
    session: Session,
) -> None:
    assert client.get("/api/v1/admin/signup-code", headers=admin_headers).is_success
    admin.is_admin = False
    session.flush()

    response = client.get("/api/v1/admin/signup-code", headers=admin_headers)

    assert response.status_code == 403


# --- the sign-up code -----------------------------------------------------


def test_adr007_the_admin_reads_the_code_and_it_is_not_cached(
    client: TestClient,
    admin_headers: dict[str, str],
    set_signup_code: Callable[[str | None], None],
) -> None:
    closed = client.get("/api/v1/admin/signup-code", headers=admin_headers)
    set_signup_code(CODE)
    open_ = client.get("/api/v1/admin/signup-code", headers=admin_headers)

    assert closed.json() == {"signup_code": None, "updated_at": None}
    assert open_.json()["signup_code"] == CODE
    assert open_.headers["Cache-Control"] == "no-store"


def test_fr005_the_admin_sets_the_code_and_the_action_is_recorded_without_it(
    client: TestClient,
    admin: User,
    admin_headers: dict[str, str],
    session: Session,
    now: datetime,
) -> None:
    response = client.put(
        "/api/v1/admin/signup-code",
        json={"signup_code": f"  {CODE}\n"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json() == {
        "signup_code": CODE,
        "updated_at": now.isoformat().replace("+00:00", "Z"),
    }
    assert _stored_code(session) == CODE
    [action] = _actions(session)
    assert (
        action.source,
        action.action,
        action.admin_user_id,
        action.target_user_id,
        action.created_at,
    ) == (
        AdminActionSource.WEB,
        AdminActionKind.SET_SIGNUP_CODE,
        admin.id,
        None,
        now,
    )
    assert CODE not in repr(vars(action))


def test_fr005_a_new_code_signs_people_up_and_the_old_one_stops_working(
    client: TestClient,
    admin_headers: dict[str, str],
    set_signup_code: Callable[[str | None], None],
) -> None:
    set_signup_code("the-old-code-123")
    client.put(
        "/api/v1/admin/signup-code",
        json={"signup_code": CODE},
        headers=admin_headers,
    )

    def sign_up(code: str, email: str) -> int:
        return client.post(
            "/api/v1/auth/signup",
            json={
                "signup_code": code,
                "email": email,
                "display_name": "New",
                "password": PASSWORD,
            },
        ).status_code

    assert sign_up("the-old-code-123", "a@example.test") == 422
    assert sign_up(CODE, "b@example.test") == 201


def test_fr005_changing_the_code_leaves_existing_accounts_alone(
    client: TestClient,
    admin_headers: dict[str, str],
    make_user: Callable[..., User],
    session: Session,
) -> None:
    organizer = make_user()
    before = organizer.password_hash

    client.put(
        "/api/v1/admin/signup-code",
        json={"signup_code": CODE},
        headers=admin_headers,
    )

    session.refresh(organizer)
    assert organizer.password_hash == before
    assert organizer.must_change_password is False


def test_fr005_null_closes_sign_up_and_is_recorded(
    client: TestClient,
    admin_headers: dict[str, str],
    set_signup_code: Callable[[str | None], None],
    session: Session,
) -> None:
    set_signup_code(CODE)

    response = client.put(
        "/api/v1/admin/signup-code", json={"signup_code": None}, headers=admin_headers
    )

    assert response.json()["signup_code"] is None
    assert _stored_code(session) is None
    [action] = _actions(session)
    assert action.action == AdminActionKind.SET_SIGNUP_CODE
    assert action.target_user_id is None


def test_fr005_closing_a_closed_sign_up_records_nothing(
    client: TestClient, admin_headers: dict[str, str], session: Session
) -> None:
    response = client.put(
        "/api/v1/admin/signup-code", json={"signup_code": None}, headers=admin_headers
    )

    assert response.status_code == 200
    assert response.json() == {"signup_code": None, "updated_at": None}
    assert _actions(session) == []


def test_fr005_setting_the_same_code_records_nothing_and_keeps_the_time(
    client: TestClient,
    admin_headers: dict[str, str],
    session: Session,
    travel: Callable[[timedelta], datetime],
    now: datetime,
) -> None:
    first = client.put(
        "/api/v1/admin/signup-code", json={"signup_code": CODE}, headers=admin_headers
    )
    travel(timedelta(minutes=5))

    again = client.put(
        "/api/v1/admin/signup-code",
        json={"signup_code": f" {CODE} "},  # the same once stripped
        headers=admin_headers,
    )

    assert again.status_code == 200
    assert again.json() == first.json()
    assert again.json()["updated_at"] == now.isoformat().replace("+00:00", "Z")
    assert len(_actions(session)) == 1


def test_fr005_a_changed_code_after_a_no_op_is_recorded_again(
    client: TestClient,
    admin_headers: dict[str, str],
    set_signup_code: Callable[[str | None], None],
    session: Session,
) -> None:
    set_signup_code(CODE)

    for code in (CODE, CODE + "2", None, None):
        client.put(
            "/api/v1/admin/signup-code",
            json={"signup_code": code},
            headers=admin_headers,
        )

    assert len(_actions(session)) == 2  # CODE2, then null


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({}, id="missing"),
        pytest.param({"signup_code": "x" * (SIGNUP_CODE_MIN_LENGTH - 1)}, id="short"),
        pytest.param(
            {"signup_code": f"  {'x' * (SIGNUP_CODE_MIN_LENGTH - 1)}  "},
            id="short-after-stripping",
        ),
        pytest.param({"signup_code": "x" * (SIGNUP_CODE_MAX_LENGTH + 1)}, id="long"),
        pytest.param({"signup_code": ""}, id="empty"),
        pytest.param({"signup_code": CODE, "extra": 1}, id="extra-field"),
    ],
)
def test_adr007_a_bad_code_is_refused_and_nothing_is_recorded(
    client: TestClient,
    admin_headers: dict[str, str],
    set_signup_code: Callable[[str | None], None],
    session: Session,
    body: dict[str, object],
) -> None:
    set_signup_code("kept-code-12345")

    response = client.put("/api/v1/admin/signup-code", json=body, headers=admin_headers)

    assert response.status_code == 422
    assert response.json()["code"] == "validation_failed"
    assert "x" * SIGNUP_CODE_MIN_LENGTH not in response.text
    assert _stored_code(session) == "kept-code-12345"
    assert _actions(session) == []


@pytest.mark.parametrize("length", [SIGNUP_CODE_MIN_LENGTH, SIGNUP_CODE_MAX_LENGTH])
def test_adr007_a_code_of_the_limit_lengths_is_accepted(
    client: TestClient, admin_headers: dict[str, str], length: int
) -> None:
    response = client.put(
        "/api/v1/admin/signup-code",
        json={"signup_code": "x" * length},
        headers=admin_headers,
    )

    assert response.status_code == 200


def test_adr007_generate_stores_a_random_code_and_records_it(
    client: TestClient,
    admin: User,
    admin_headers: dict[str, str],
    session: Session,
) -> None:
    first = client.post("/api/v1/admin/signup-code/generate", headers=admin_headers)
    second = client.post("/api/v1/admin/signup-code/generate", headers=admin_headers)

    code = second.json()["signup_code"]
    assert first.status_code == 200
    assert first.json()["signup_code"] != code  # random
    assert len(code) == 22
    assert code.isascii()
    assert _stored_code(session) == code
    assert first.headers["Cache-Control"] == "no-store"
    actions = _actions(session)
    assert [(a.source, a.action, a.admin_user_id) for a in actions] == [
        (AdminActionSource.WEB, AdminActionKind.SET_SIGNUP_CODE, admin.id)
    ] * 2
    assert code not in repr([vars(action) for action in actions])


# --- the organizer list -----------------------------------------------------


def test_fr006_the_list_has_every_account_by_email_without_secrets(
    client: TestClient,
    admin: User,
    admin_headers: dict[str, str],
    make_user: Callable[..., User],
    now: datetime,
) -> None:
    zed = make_user(email="Zed@example.test")
    amy = make_user(email="amy@example.test", must_change_password=True)

    response = client.get("/api/v1/admin/organizers", headers=admin_headers)

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": str(user.id),
            "email": user.email,
            "display_name": "Ana",
            "is_admin": user.is_admin,
            "must_change_password": user.must_change_password,
            "created_at": now.isoformat().replace("+00:00", "Z"),
        }
        for user in (amy, admin, zed)
    ]
    assert "password" not in response.text.replace("must_change_password", "")
    assert response.headers["cache-control"] == "no-store"


# --- the password reset -----------------------------------------------------


def test_fr006_a_reset_without_a_password_generates_one_shown_once(
    client: TestClient,
    admin: User,
    admin_headers: dict[str, str],
    make_user: Callable[..., User],
    session: Session,
    now: datetime,
) -> None:
    organizer = make_user(email="ola@example.test", password=PASSWORD)

    response = _reset(client, admin_headers, organizer)

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    generated = response.json()["temporary_password"]
    assert len(generated) >= 15
    session.refresh(organizer)
    assert organizer.must_change_password is True
    assert organizer.updated_at == now
    assert auth_service.verify_password(organizer.password_hash, generated)
    [action] = _actions(session)
    assert (
        action.source,
        action.action,
        action.admin_user_id,
        action.target_user_id,
    ) == (
        AdminActionSource.WEB,
        AdminActionKind.RESET_PASSWORD,
        admin.id,
        organizer.id,
    )
    assert generated not in repr(vars(action))


def test_fr006_two_generated_passwords_differ(
    client: TestClient,
    admin_headers: dict[str, str],
    make_user: Callable[..., User],
) -> None:
    organizer = make_user()

    first = _reset(client, admin_headers, organizer).json()["temporary_password"]
    second = _reset(client, admin_headers, organizer).json()["temporary_password"]

    assert first != second


def test_fr006_a_chosen_password_is_set_and_not_returned(
    client: TestClient,
    admin_headers: dict[str, str],
    make_user: Callable[..., User],
    session: Session,
) -> None:
    organizer = make_user(password=PASSWORD)

    response = _reset(client, admin_headers, organizer, temporary_password=TEMPORARY)

    assert response.json() == {"temporary_password": None}
    assert TEMPORARY not in response.text
    session.refresh(organizer)
    assert auth_service.verify_password(organizer.password_hash, TEMPORARY)
    assert not auth_service.verify_password(organizer.password_hash, PASSWORD)


def test_adr006_a_short_temporary_password_is_refused_and_changes_nothing(
    client: TestClient,
    admin_headers: dict[str, str],
    make_user: Callable[..., User],
    session: Session,
) -> None:
    organizer = make_user(password=PASSWORD)
    before = organizer.password_hash

    response = _reset(client, admin_headers, organizer, temporary_password="tooShort1")

    assert response.status_code == 422
    assert "tooShort1" not in response.text
    session.refresh(organizer)
    assert organizer.password_hash == before
    assert organizer.must_change_password is False
    assert _actions(session) == []


def test_adr006_after_a_reset_the_organizer_logs_in_with_the_temporary_password_only(
    client: TestClient,
    admin_headers: dict[str, str],
    make_user: Callable[..., User],
) -> None:
    organizer = make_user(password=PASSWORD)
    temporary = _reset(client, admin_headers, organizer).json()["temporary_password"]

    old = _log_in(client, organizer, PASSWORD)
    new = _log_in(client, organizer, temporary)

    assert old.status_code == 401
    assert new.status_code == 200
    me = client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {new.json()['access_token']}"},
    )
    assert me.json()["must_change_password"] is True


def test_adr006_a_reset_revokes_every_login_of_the_organizer(
    client: TestClient,
    admin_headers: dict[str, str],
    make_user: Callable[..., User],
    settings: Settings,
    session: Session,
    now: datetime,
) -> None:
    organizer, other = make_user(), make_user()
    for _ in range(2):  # two devices
        auth_service.start_session(
            session, user_id=organizer.id, key=settings.jwt_secret, now=now
        )
    auth_service.start_session(
        session, user_id=other.id, key=settings.jwt_secret, now=now
    )

    _reset(client, admin_headers, organizer)

    tokens = session.scalars(select(RefreshToken)).all()
    revoked = {t.user_id: t.revoked_at for t in tokens}
    assert {t.revoked_at for t in tokens if t.user_id == organizer.id} == {now}
    assert revoked[other.id] is None


def test_adr006_the_revoked_login_cannot_refresh(
    client: TestClient,
    admin_headers: dict[str, str],
    make_user: Callable[..., User],
) -> None:
    organizer = make_user(password=PASSWORD)
    login = _log_in(client, organizer, PASSWORD)
    cookie = login.cookies["refresh_token"]
    _reset(client, admin_headers, organizer)

    client.cookies.clear()
    refreshed = client.post(
        "/api/v1/auth/refresh",
        headers={"X-Requested-With": "t", "Cookie": f"refresh_token={cookie}"},
    )

    assert refreshed.status_code == 401


def _token_of(response: httpx2.Response) -> dict[str, str]:
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_adr006_an_access_token_issued_before_the_reset_is_refused_at_once_as_expired(
    client: TestClient,
    admin_headers: dict[str, str],
    make_user: Callable[..., User],
) -> None:
    organizer = make_user(password=PASSWORD)
    old = _token_of(_log_in(client, organizer, PASSWORD))
    assert client.get("/api/v1/leagues", headers=old).status_code == 200

    _reset(client, admin_headers, organizer)

    # The revoked family refuses the token, not the required password change: the
    # SPA refreshes once, fails and logs out.
    for path in ("/api/v1/leagues", "/api/v1/me"):
        refused = client.get(path, headers=old)
        assert refused.status_code == 401
        assert refused.json() == {"code": "token_expired", "detail": {}}


def test_adr006_the_old_access_token_stays_refused_after_the_organizer_changes_the_password(
    client: TestClient,
    admin_headers: dict[str, str],
    make_user: Callable[..., User],
) -> None:
    organizer = make_user(password=PASSWORD)
    old = _token_of(_log_in(client, organizer, PASSWORD))
    temporary = _reset(client, admin_headers, organizer).json()["temporary_password"]
    fresh = _token_of(_log_in(client, organizer, temporary))

    changed = client.post(
        "/api/v1/auth/password",
        json={"current_password": temporary, "new_password": "my own new passphrase"},
        headers=fresh,
    )

    assert changed.status_code == 204
    assert client.get("/api/v1/leagues", headers=fresh).status_code == 200
    refused = client.get("/api/v1/leagues", headers=old)
    assert (refused.status_code, refused.json()["code"]) == (401, "token_expired")
    assert client.get("/api/v1/me", headers=old).status_code == 401


def test_adr006_a_password_change_after_a_reset_ends_the_requirement(
    client: TestClient,
    admin_headers: dict[str, str],
    make_user: Callable[..., User],
) -> None:
    organizer = make_user(password=PASSWORD)
    temporary = _reset(client, admin_headers, organizer).json()["temporary_password"]
    login = _log_in(client, organizer, temporary)
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    changed = client.post(
        "/api/v1/auth/password",
        json={"current_password": temporary, "new_password": "my own new passphrase"},
        headers=headers,
    )

    assert changed.status_code == 204
    assert client.get("/api/v1/leagues", headers=headers).status_code == 200


def test_adr006_a_chosen_temporary_password_must_still_be_changed_to_a_new_one(
    client: TestClient,
    admin_headers: dict[str, str],
    make_user: Callable[..., User],
) -> None:
    organizer = make_user(password=PASSWORD)
    _reset(client, admin_headers, organizer, temporary_password=TEMPORARY)
    login = _log_in(client, organizer, TEMPORARY)

    same = client.post(
        "/api/v1/auth/password",
        json={"current_password": TEMPORARY, "new_password": TEMPORARY},
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )

    assert same.status_code == 422
    assert same.json()["code"] == "password_unchanged"


def test_adr007_an_admin_cannot_reset_their_own_password(
    client: TestClient,
    admin: User,
    admin_headers: dict[str, str],
    session: Session,
) -> None:
    before = admin.password_hash

    response = _reset(client, admin_headers, admin)

    assert response.status_code == 422
    assert response.json() == {"code": "own_account", "detail": {}}
    session.refresh(admin)
    assert (admin.password_hash, admin.must_change_password) == (before, False)
    assert _actions(session) == []


def test_adr007_another_admins_password_is_not_reset_by_the_web(
    client: TestClient,
    admin_headers: dict[str, str],
    make_user: Callable[..., User],
    session: Session,
) -> None:
    other = make_user(is_admin=True, password=PASSWORD)
    login = _log_in(client, other, PASSWORD)
    before = other.password_hash

    response = _reset(client, admin_headers, other)
    chosen = _reset(client, admin_headers, other, temporary_password=TEMPORARY)

    for refused in (response, chosen):
        assert refused.status_code == 422
        assert refused.json() == {"code": "admin_target", "detail": {}}
        assert "temporary_password" not in refused.text
    session.expire_all()
    assert (other.password_hash, other.must_change_password) == (before, False)
    assert _actions(session) == []
    # Nothing was revoked: the admin's own login still works.
    assert client.get("/api/v1/me", headers=_token_of(login)).status_code == 200


def test_adr007_an_admin_who_lost_the_flag_can_be_reset(
    client: TestClient,
    admin_headers: dict[str, str],
    make_user: Callable[..., User],
    session: Session,
) -> None:
    former = make_user(is_admin=True)
    former.is_admin = False  # `revoke-admin` from the CLI
    session.flush()

    assert _reset(client, admin_headers, former).status_code == 200


def test_adr007_an_unknown_account_is_404_and_records_nothing(
    client: TestClient, admin_headers: dict[str, str], session: Session
) -> None:
    response = client.post(
        f"/api/v1/admin/organizers/{uuid7()}/password-reset",
        json={},
        headers=admin_headers,
    )

    assert response.status_code == 404
    assert response.json()["code"] == "user_not_found"
    assert _actions(session) == []


def test_adr007_a_malformed_account_id_is_a_validation_error(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    response = client.post(
        "/api/v1/admin/organizers/not-a-uuid/password-reset",
        json={},
        headers=admin_headers,
    )

    assert response.status_code == 422


def test_adr007_every_reset_is_recorded(
    client: TestClient,
    admin_headers: dict[str, str],
    make_user: Callable[..., User],
    session: Session,
) -> None:
    organizer = make_user()

    _reset(client, admin_headers, organizer)
    _reset(client, admin_headers, organizer, temporary_password=TEMPORARY)

    assert len(_actions(session)) == 2


def test_adr006_a_reset_does_not_touch_other_accounts(
    client: TestClient,
    admin_headers: dict[str, str],
    make_user: Callable[..., User],
    session: Session,
) -> None:
    organizer, bystander = make_user(), make_user()
    before = bystander.password_hash

    _reset(client, admin_headers, organizer)

    session.refresh(bystander)
    assert bystander.password_hash == before
    assert bystander.must_change_password is False


def test_adr006_a_deleted_target_leaves_the_record_with_no_target(
    client: TestClient,
    admin: User,
    admin_headers: dict[str, str],
    make_user: Callable[..., User],
    session: Session,
) -> None:
    organizer = make_user()
    _reset(client, admin_headers, organizer)

    session.delete(organizer)
    session.flush()
    session.expire_all()

    [action] = _actions(session)
    assert (action.admin_user_id, action.target_user_id) == (admin.id, None)


# --- the new-password requirement blocks everything else ---------------------

_ALLOWED_WITH_A_REQUIRED_PASSWORD = {
    ("GET", "/api/v1/me"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/signup"),
    ("POST", "/api/v1/auth/refresh"),
    ("POST", "/api/v1/auth/logout"),
    ("POST", "/api/v1/auth/password"),
}


def test_adr006_while_a_new_password_is_required_every_other_route_answers_403(
    client: TestClient,
    make_user: Callable[..., User],
    auth_header: Callable[..., dict[str, str]],
) -> None:
    user = make_user(must_change_password=True, is_admin=True)
    app = client.app
    assert isinstance(app, FastAPI)
    seen: set[tuple[str, str]] = set()
    refused = 0

    for template, operations in app.openapi()["paths"].items():
        if template.startswith("/api/v1/public/"):
            continue  # the share-link routes take no account, so no password rule applies
        path = re.sub(r"\{[^}]+\}", lambda _: str(uuid7()), template)
        for method in operations:
            seen.add((method.upper(), template))
            if (method.upper(), template) in _ALLOWED_WITH_A_REQUIRED_PASSWORD:
                continue
            response = client.request(
                method, path, json={}, headers=auth_header(user.id)
            )
            assert response.status_code == 403, (method, template)
            assert response.json()["code"] == "password_change_required", (
                method,
                template,
            )
            refused += 1

    assert seen >= _ALLOWED_WITH_A_REQUIRED_PASSWORD  # the allow-list names real routes
    assert refused >= 15


# --- a reset racing a refresh ---------------------------------------------


@pytest.mark.concurrency
def test_adr006_a_reset_also_revokes_the_token_a_racing_refresh_issued(
    committing_settings: Settings,
    committing_engine: Engine,
    wait_for_a_lock_wait: Callable[[], None],
) -> None:
    at = datetime.now(UTC)
    with Session(committing_engine) as setup:
        admin = User(
            email=f"{uuid7()}@example.test",
            display_name="Boss",
            password_hash="!",
            is_admin=True,
            language=Language.EN,
            created_at=at,
        )
        organizer = User(
            email=f"{uuid7()}@example.test",
            display_name="Ola",
            password_hash="!",
            language=Language.EN,
            created_at=at,
        )
        setup.add_all([admin, organizer])
        setup.flush()
        first = auth_service.start_session(
            setup, user_id=organizer.id, key=committing_settings.jwt_secret, now=at
        )
        boss = auth_service.start_session(
            setup, user_id=admin.id, key=committing_settings.jwt_secret, now=at
        )
        setup.commit()
        organizer_id = organizer.id
    headers = {"Authorization": f"Bearer {boss.access_token}"}
    outcome: list[int] = []

    with (
        Session(committing_engine) as refreshing,
        TestClient(create_app(committing_settings)) as client,
    ):
        issued = auth_service.refresh_session(
            refreshing,
            refresh_token=first.refresh_token,
            key=committing_settings.jwt_secret,
            now=at,
        )
        assert issued is not None

        def reset() -> None:
            outcome.append(
                client.post(
                    f"/api/v1/admin/organizers/{organizer_id}/password-reset",
                    json={},
                    headers=headers,
                ).status_code
            )

        resetting = threading.Thread(target=reset)
        resetting.start()
        wait_for_a_lock_wait()
        refreshing.commit()
        resetting.join()

    assert outcome == [200]
    with Session(committing_engine) as reader:
        tokens = reader.scalars(
            select(RefreshToken).where(RefreshToken.user_id == UUID(str(organizer_id)))
        ).all()
    assert len(tokens) == 2
    assert all(token.revoked_at is not None for token in tokens)
