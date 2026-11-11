from collections.abc import Iterator

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from tourneyhub.app import create_app
from tourneyhub.errors import AppError, ErrorCode, ForbiddenError, RuleViolationError
from tourneyhub.settings import Settings


def _boom() -> None:
    raise RuntimeError("secret internals")


def _teapot() -> None:
    raise HTTPException(status_code=418)


def _forbidden() -> None:
    raise ForbiddenError(ErrorCode.PASSWORD_CHANGE_REQUIRED)


def _refused() -> None:
    raise RuleViolationError(ErrorCode.SEASON_CLOSED, minimum=4, given=3)


def _unknown_constraint() -> None:
    raise IntegrityError("INSERT ...", {}, Exception("not from psycopg"))


def _plain_app_error() -> None:
    raise AppError(ErrorCode.BAD_REQUEST)


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    app = create_app(settings)
    app.add_api_route("/boom", _boom)
    app.add_api_route("/teapot", _teapot)
    app.add_api_route("/forbidden", _forbidden)
    app.add_api_route("/refused", _refused)
    app.add_api_route("/unknown-constraint", _unknown_constraint)
    app.add_api_route("/plain", _plain_app_error)
    app.add_api_route("/api/v1/public/some-token/boom", _boom)
    app.add_api_route(
        "/api/v1/public/some-token/unknown-constraint", _unknown_constraint
    )
    return app


@pytest.fixture
def lenient_client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def test_an_unexpected_exception_is_a_500_without_details(
    lenient_client: TestClient,
) -> None:
    response = lenient_client.get("/boom")

    assert response.status_code == 500
    assert response.json() == {"code": "internal_error", "detail": {}}
    assert "secret internals" not in response.text


def test_an_unknown_constraint_violation_is_a_500(
    lenient_client: TestClient,
) -> None:
    response = lenient_client.get("/unknown-constraint")

    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"


def test_a_status_without_its_own_code_is_bad_request(
    lenient_client: TestClient,
) -> None:
    response = lenient_client.get("/teapot")

    assert response.status_code == 418
    assert response.json()["code"] == "bad_request"


def test_the_subclass_decides_the_status(lenient_client: TestClient) -> None:
    forbidden = lenient_client.get("/forbidden")
    refused = lenient_client.get("/refused")

    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "password_change_required"
    assert refused.status_code == 422
    assert refused.json() == {
        "code": "season_closed",
        "detail": {"minimum": 4, "given": 3},
    }


def test_a_bare_app_error_is_a_500(lenient_client: TestClient) -> None:
    response = lenient_client.get("/plain")

    assert response.status_code == 500
    assert response.json()["code"] == "bad_request"


@pytest.mark.parametrize("route", ["boom", "unknown-constraint"])
def test_adr005_a_500_under_public_keeps_the_public_headers(
    lenient_client: TestClient, route: str
) -> None:
    # Starlette sends the Exception handler's response outside every middleware.
    response = lenient_client.get(f"/api/v1/public/some-token/{route}")

    assert response.status_code == 500
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"


@pytest.mark.parametrize("route", ["boom", "unknown-constraint"])
def test_a_500_elsewhere_has_no_public_headers(
    lenient_client: TestClient, route: str
) -> None:
    response = lenient_client.get(f"/{route}")

    assert response.status_code == 500
    assert "Cache-Control" not in response.headers
    assert "Referrer-Policy" not in response.headers
