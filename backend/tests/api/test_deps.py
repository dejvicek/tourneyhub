from collections.abc import Callable
from uuid import UUID, uuid7

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

from tourneyhub.api.deps import AdminDep, CurrentUserDep
from tourneyhub.db.models.accounts import User


def _whoami(user: CurrentUserDep) -> str:
    return str(user.id)


def _admin_only(admin: AdminDep) -> str:
    return str(admin.id)


@pytest.fixture
def routes(
    client: TestClient, auth_header: Callable[..., dict[str, str]]
) -> Callable[[str, UUID], tuple[int, object]]:
    app = client.app
    assert isinstance(app, FastAPI)
    app.add_api_route("/whoami", _whoami)
    app.add_api_route("/admin", _admin_only)

    def get(path: str, user_id: UUID) -> tuple[int, object]:
        response = client.get(path, headers=auth_header(user_id))
        return response.status_code, response.json()

    return get


def test_current_user_dep_loads_the_users_row(
    routes: Callable[[str, UUID], tuple[int, object]], make_user: Callable[..., User]
) -> None:
    user = make_user()

    assert routes("/whoami", user.id) == (200, str(user.id))


def test_adr006_password_change_required_blocks_other_routes(
    routes: Callable[[str, UUID], tuple[int, object]], make_user: Callable[..., User]
) -> None:
    user = make_user(must_change_password=True)

    assert routes("/whoami", user.id) == (
        403,
        {"code": "password_change_required", "detail": {}},
    )


def test_an_unknown_user_is_not_authenticated(
    routes: Callable[[str, UUID], tuple[int, object]],
) -> None:
    assert routes("/whoami", uuid7()) == (
        401,
        {"code": "not_authenticated", "detail": {}},
    )


def test_adr007_admin_dep_reads_the_flag_from_the_row(
    routes: Callable[[str, UUID], tuple[int, object]], make_user: Callable[..., User]
) -> None:
    organizer = make_user()
    admin = make_user(is_admin=True)

    assert routes("/admin", organizer.id) == (403, {"code": "forbidden", "detail": {}})
    assert routes("/admin", admin.id) == (200, str(admin.id))


def test_adr006_an_admin_request_reads_the_users_row_once(
    routes: Callable[[str, UUID], tuple[int, object]],
    make_user: Callable[..., User],
    session: Session,
) -> None:
    admin = make_user(is_admin=True)
    session.expunge_all()  # the request must load the row itself
    statements: list[str] = []
    event.listen(
        session.get_bind(),
        "before_cursor_execute",
        lambda *args: statements.append(args[2]),
    )

    routes("/admin", admin.id)

    assert sum("FROM users" in statement for statement in statements) == 1
