from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import uuid7

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tourneyhub.db.models.accounts import User
from tourneyhub.engine.accounts import Language


@pytest.fixture
def ana(make_user: Callable[..., User]) -> User:
    return make_user(email="ana@example.test", is_admin=True)


@pytest.fixture
def headers(ana: User, auth_header: Callable[..., dict[str, str]]) -> dict[str, str]:
    return auth_header(ana.id)


def test_fr081_get_me_returns_the_account_without_secrets(
    client: TestClient, ana: User, headers: dict[str, str]
) -> None:
    response = client.get("/api/v1/me", headers=headers)

    assert response.status_code == 200
    assert response.json() == {
        "id": str(ana.id),
        "email": "ana@example.test",
        "display_name": "Ana",
        "language": "en",
        "is_admin": True,
        "must_change_password": False,
    }


def test_adr006_get_me_works_while_a_new_password_is_required(
    client: TestClient,
    make_user: Callable[..., User],
    auth_header: Callable[..., dict[str, str]],
) -> None:
    user = make_user(must_change_password=True)

    response = client.get("/api/v1/me", headers=auth_header(user.id))

    assert response.status_code == 200
    assert response.json()["must_change_password"] is True


def test_adr006_patch_me_is_refused_while_a_new_password_is_required(
    client: TestClient,
    make_user: Callable[..., User],
    auth_header: Callable[..., dict[str, str]],
    session: Session,
) -> None:
    user = make_user(must_change_password=True)

    response = client.patch(
        "/api/v1/me", json={"language": "cs"}, headers=auth_header(user.id)
    )

    assert response.status_code == 403
    assert response.json()["code"] == "password_change_required"
    session.refresh(user)
    assert user.language == Language.EN


@pytest.mark.parametrize("method", ["get", "patch"])
def test_adr008_me_needs_an_access_token(client: TestClient, method: str) -> None:
    response = client.request(
        method, "/api/v1/me", json={} if method == "patch" else None
    )

    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"


def test_adr006_me_of_a_deleted_user_is_not_authenticated(
    client: TestClient, auth_header: Callable[..., dict[str, str]]
) -> None:
    response = client.get("/api/v1/me", headers=auth_header(uuid7()))

    assert response.status_code == 401


def test_fr081_patch_me_changes_the_language_and_it_is_remembered(
    client: TestClient, ana: User, headers: dict[str, str], now: datetime
) -> None:
    response = client.patch("/api/v1/me", json={"language": "cs"}, headers=headers)

    assert response.status_code == 200
    assert response.json()["language"] == "cs"
    assert response.json()["display_name"] == "Ana"
    assert ana.updated_at == now
    assert client.get("/api/v1/me", headers=headers).json()["language"] == "cs"


def test_fr001_patch_me_changes_the_display_name_and_strips_it(
    client: TestClient, ana: User, headers: dict[str, str]
) -> None:
    response = client.patch(
        "/api/v1/me", json={"display_name": "  Anežka  "}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["display_name"] == "Anežka"
    assert ana.display_name == "Anežka"
    assert ana.language == Language.EN


def test_fr081_patch_me_changes_both_at_once(
    client: TestClient, ana: User, headers: dict[str, str]
) -> None:
    response = client.patch(
        "/api/v1/me", json={"display_name": "Anna", "language": "cs"}, headers=headers
    )

    assert response.status_code == 200
    assert (ana.display_name, ana.language) == ("Anna", Language.CS)


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({}, id="empty"),
        pytest.param({"display_name": None, "language": None}, id="nulls"),
        pytest.param({"display_name": "Ana", "language": "en"}, id="same-values"),
    ],
)
def test_fr081_patch_me_with_nothing_to_change_changes_nothing(
    client: TestClient, ana: User, headers: dict[str, str], body: dict[str, str | None]
) -> None:
    response = client.patch("/api/v1/me", json=body, headers=headers)

    assert response.status_code == 200
    assert response.json()["display_name"] == "Ana"
    assert ana.updated_at is None


def test_fr081_patch_me_twice_with_the_same_body_is_harmless(
    client: TestClient,
    ana: User,
    headers: dict[str, str],
    travel: Callable[[timedelta], datetime],
    now: datetime,
) -> None:
    client.patch("/api/v1/me", json={"language": "cs"}, headers=headers)
    later = travel(timedelta(minutes=1))

    response = client.patch("/api/v1/me", json={"language": "cs"}, headers=headers)

    assert response.status_code == 200
    assert ana.updated_at == now  # not touched again
    assert later > now


@pytest.mark.parametrize(
    ("body", "loc", "error_type"),
    [
        pytest.param(
            {"display_name": ""}, "display_name", "string_too_short", id="empty-name"
        ),
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
            {"display_name": 7}, "display_name", "string_type", id="number-name"
        ),
        pytest.param({"language": "de"}, "language", "enum", id="unknown-language"),
        pytest.param({"language": "EN"}, "language", "enum", id="upper-case-language"),
        pytest.param({"is_admin": False}, "is_admin", "extra_forbidden", id="is_admin"),
        pytest.param(
            {"email": "x@example.test"}, "email", "extra_forbidden", id="email"
        ),
        pytest.param(
            {"must_change_password": False},
            "must_change_password",
            "extra_forbidden",
            id="must_change_password",
        ),
    ],
)
def test_fr081_patch_me_validates_its_fields(
    client: TestClient,
    ana: User,
    headers: dict[str, str],
    body: dict[str, object],
    loc: str,
    error_type: str,
) -> None:
    response = client.patch("/api/v1/me", json=body, headers=headers)

    assert response.status_code == 422
    errors = response.json()["detail"]["errors"]
    assert response.json()["code"] == "validation_failed"
    assert [(e["loc"], e["type"]) for e in errors] == [(["body", loc], error_type)]
    assert (ana.display_name, ana.language, ana.is_admin) == ("Ana", Language.EN, True)


def test_fr081_a_valid_field_is_not_applied_when_another_is_invalid(
    client: TestClient, ana: User, headers: dict[str, str]
) -> None:
    client.patch(
        "/api/v1/me", json={"display_name": "Anna", "language": "de"}, headers=headers
    )

    assert ana.display_name == "Ana"
