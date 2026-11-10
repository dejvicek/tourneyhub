import threading
import time
from collections.abc import Callable, Iterator
from datetime import datetime
from uuid import uuid7

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from tourneyhub.api.schemas import ErrorResponse
from tourneyhub.app import create_app
from tourneyhub.db.models.accounts import User
from tourneyhub.db.models.leagues import League
from tourneyhub.engine.accounts import Language
from tourneyhub.services import leagues as league_service
from tourneyhub.settings import Settings


def test_post_creates_a_league_for_the_caller(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    owner = make_user()
    league_id = str(uuid7())

    response = client.post(
        "/api/v1/leagues",
        json={"id": league_id, "name": "  Thursday DYP "},
        headers={"X-User-Id": str(owner.id)},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == league_id
    assert body["name"] == "Thursday DYP"


def test_get_returns_the_callers_league(
    client: TestClient, make_league: Callable[..., League]
) -> None:
    league = make_league(name="Mine")

    response = client.get(
        f"/api/v1/leagues/{league.id}", headers={"X-User-Id": str(league.owner_user_id)}
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Mine"


def test_get_another_organizers_league_is_not_found(
    client: TestClient,
    make_league: Callable[..., League],
    make_user: Callable[..., User],
) -> None:
    league = make_league()
    stranger = make_user()

    response = client.get(
        f"/api/v1/leagues/{league.id}", headers={"X-User-Id": str(stranger.id)}
    )

    assert response.status_code == 404
    assert response.json() == {"code": "league_not_found", "detail": {}}


def test_missing_user_header_is_not_authenticated(client: TestClient) -> None:
    response = client.get(f"/api/v1/leagues/{uuid7()}")

    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"


def test_post_repeated_returns_the_same_league(
    client: TestClient, make_league: Callable[..., League]
) -> None:
    league = make_league(name="Thursday DYP")

    response = client.post(
        "/api/v1/leagues",
        json={"id": str(league.id), "name": "Thursday DYP"},
        headers={"X-User-Id": str(league.owner_user_id)},
    )

    assert response.status_code == 201
    assert response.json()["id"] == str(league.id)


def test_post_with_another_organizers_id_is_a_conflict(
    client: TestClient,
    make_league: Callable[..., League],
    make_user: Callable[..., User],
) -> None:
    league = make_league()
    stranger = make_user()

    response = client.post(
        "/api/v1/leagues",
        json={"id": str(league.id), "name": "Other"},
        headers={"X-User-Id": str(stranger.id)},
    )

    assert response.status_code == 409
    assert response.json() == {"code": "league_id_taken", "detail": {}}


def test_post_with_a_too_long_name_reports_loc_type_and_limit(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    owner = make_user()

    response = client.post(
        "/api/v1/leagues",
        json={"id": str(uuid7()), "name": "x" * 101, "is_admin": True},
        headers={"X-User-Id": str(owner.id)},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_failed"
    assert {"loc": ["body", "name"], "type": "string_too_long", "max_length": 100} in (
        body["detail"]["errors"]
    )
    assert {"loc": ["body", "is_admin"], "type": "extra_forbidden"} in (
        body["detail"]["errors"]
    )
    assert "input" not in str(body)


def test_validation_failed_lists_loc_type_and_numeric_limits(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    owner = make_user()

    response = client.post(
        "/api/v1/leagues",
        json={"id": str(uuid7()), "name": "x" * 101, "is_admin": True},
        headers={"X-User-Id": str(owner.id)},
    )

    assert response.status_code == 422
    assert response.json() == {
        "code": "validation_failed",
        "detail": {
            "errors": [
                {"loc": ["body", "name"], "type": "string_too_long", "max_length": 100},
                {"loc": ["body", "is_admin"], "type": "extra_forbidden"},
            ]
        },
    }
    ErrorResponse.model_validate(response.json())  # fits the schema in openapi.json


def test_unknown_path_and_wrong_method_use_framework_codes(
    client: TestClient,
) -> None:
    missing = client.get("/api/v1/nowhere")
    wrong_method = client.delete("/api/v1/leagues")

    assert missing.status_code == 404
    assert missing.json()["code"] == "not_found"
    assert wrong_method.status_code == 405
    assert wrong_method.json()["code"] == "method_not_allowed"
    assert "allow" in wrong_method.headers


def test_malformed_json_is_a_validation_failure(client: TestClient) -> None:
    response = client.post(
        "/api/v1/leagues",
        content=b"{",
        headers={"X-User-Id": str(uuid7()), "Content-Type": "application/json"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_failed"


@pytest.fixture
def committing_engine(engine: Engine) -> Iterator[Engine]:
    """The test database for tests that commit; emptied afterwards (§9)."""
    yield engine
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE leagues, users CASCADE"))


def _wait_until_another_connection_waits_for_a_lock(engine: Engine) -> None:
    query = text(
        "SELECT count(*) FROM pg_stat_activity"
        " WHERE datname = current_database() AND wait_event_type = 'Lock'"
    )
    for _ in range(500):
        with engine.connect() as connection:  # a new snapshot of pg_stat_activity
            if connection.scalar(query):
                return
        time.sleep(0.01)
    pytest.fail("the second request never waited for the first")


@pytest.mark.concurrency
def test_adr008_a_retry_racing_its_uncommitted_first_attempt_is_a_conflict(
    settings: Settings, committing_engine: Engine, now: datetime
) -> None:
    with Session(committing_engine) as setup:
        owner = User(
            email="racer@example.test",
            display_name="Racer",
            password_hash="!",
            language=Language.EN,
            created_at=now,
        )
        setup.add(owner)
        setup.commit()
        owner_id = owner.id
    league_id = uuid7()
    outcome: list[tuple[int, object]] = []

    with (
        Session(committing_engine) as first,
        TestClient(create_app(settings)) as client,
    ):
        league_service.create_league(
            first,
            league_id=league_id,
            owner_user_id=owner_id,
            name="Thursday DYP",
            now=now,
        )

        def post_second() -> None:
            response = client.post(
                "/api/v1/leagues",
                json={"id": str(league_id), "name": "Thursday DYP"},
                headers={"X-User-Id": str(owner_id)},
            )
            outcome.append((response.status_code, response.json()))

        second = threading.Thread(target=post_second)
        second.start()
        # Its checks saw nothing; its INSERT now waits on our uncommitted row.
        _wait_until_another_connection_waits_for_a_lock(committing_engine)
        first.commit()
        second.join()

    assert outcome == [(409, {"code": "league_id_taken", "detail": {}})]
