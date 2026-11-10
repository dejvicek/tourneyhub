import io
import threading
from collections.abc import Callable
from contextlib import redirect_stderr
from datetime import UTC, datetime, timedelta
from uuid import uuid7

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from tourneyhub.api.schemas import ErrorResponse
from tourneyhub.app import create_app
from tourneyhub.db.models.accounts import User
from tourneyhub.db.models.leagues import League, Season
from tourneyhub.engine.accounts import Language
from tourneyhub.engine.leagues import SeasonState
from tourneyhub.services import leagues as league_service
from tourneyhub.settings import Settings


def test_post_creates_a_league_for_the_caller(
    client: TestClient,
    make_user: Callable[..., User],
    auth_header: Callable[..., dict[str, str]],
) -> None:
    owner = make_user()
    league_id = str(uuid7())

    response = client.post(
        "/api/v1/leagues",
        json={"id": league_id, "name": "  Thursday DYP "},
        headers=auth_header(owner.id),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == league_id
    assert body["name"] == "Thursday DYP"


def test_get_returns_the_callers_league(
    client: TestClient,
    make_league: Callable[..., League],
    auth_header: Callable[..., dict[str, str]],
) -> None:
    league = make_league(name="Mine")

    response = client.get(
        f"/api/v1/leagues/{league.id}", headers=auth_header(league.owner_user_id)
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Mine"


def test_get_another_organizers_league_is_not_found(
    client: TestClient,
    make_league: Callable[..., League],
    make_user: Callable[..., User],
    auth_header: Callable[..., dict[str, str]],
) -> None:
    league = make_league()
    stranger = make_user()

    response = client.get(
        f"/api/v1/leagues/{league.id}", headers=auth_header(stranger.id)
    )

    assert response.status_code == 404
    assert response.json() == {"code": "league_not_found", "detail": {}}


def test_adr006_a_request_without_an_access_token_is_not_authenticated(
    client: TestClient,
) -> None:
    response = client.get(f"/api/v1/leagues/{uuid7()}")

    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"


def test_post_repeated_returns_the_same_league(
    client: TestClient,
    make_league: Callable[..., League],
    auth_header: Callable[..., dict[str, str]],
) -> None:
    league = make_league(name="Thursday DYP")

    response = client.post(
        "/api/v1/leagues",
        json={"id": str(league.id), "name": "Thursday DYP"},
        headers=auth_header(league.owner_user_id),
    )

    assert response.status_code == 201
    assert response.json()["id"] == str(league.id)


def test_post_with_another_organizers_id_is_a_conflict(
    client: TestClient,
    make_league: Callable[..., League],
    make_user: Callable[..., User],
    auth_header: Callable[..., dict[str, str]],
) -> None:
    league = make_league()
    stranger = make_user()

    response = client.post(
        "/api/v1/leagues",
        json={"id": str(league.id), "name": "Other"},
        headers=auth_header(stranger.id),
    )

    assert response.status_code == 409
    assert response.json() == {"code": "league_id_taken", "detail": {}}


def test_post_with_a_too_long_name_reports_loc_type_and_limit(
    client: TestClient,
    make_user: Callable[..., User],
    auth_header: Callable[..., dict[str, str]],
) -> None:
    owner = make_user()

    response = client.post(
        "/api/v1/leagues",
        json={"id": str(uuid7()), "name": "x" * 101, "is_admin": True},
        headers=auth_header(owner.id),
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
    client: TestClient,
    make_user: Callable[..., User],
    auth_header: Callable[..., dict[str, str]],
) -> None:
    owner = make_user()

    response = client.post(
        "/api/v1/leagues",
        json={"id": str(uuid7()), "name": "x" * 101, "is_admin": True},
        headers=auth_header(owner.id),
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


def test_malformed_json_is_a_validation_failure(
    client: TestClient,
    auth_header: Callable[..., dict[str, str]],
) -> None:
    response = client.post(
        "/api/v1/leagues",
        content=b"{",
        headers=auth_header(uuid7()) | {"Content-Type": "application/json"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_failed"


@pytest.mark.concurrency
def test_adr008_a_retry_racing_its_uncommitted_first_attempt_is_a_conflict(
    settings: Settings,
    committing_engine: Engine,
    now: datetime,
    auth_header: Callable[..., dict[str, str]],
    wait_for_a_lock_wait: Callable[[], None],
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
                # The app reads the system clock here, not the test's `now`.
                headers=auth_header(owner_id, issued_at=datetime.now(UTC)),
            )
            outcome.append((response.status_code, response.json()))

        second = threading.Thread(target=post_second)
        second.start()
        # Its checks saw nothing; its INSERT now waits on our uncommitted row.
        wait_for_a_lock_wait()
        first.commit()
        second.join()

    assert outcome == [(409, {"code": "league_id_taken", "detail": {}})]


def test_fr010_post_returns_the_league_with_season_1_and_its_settings(
    client: TestClient,
    make_user: Callable[..., User],
    auth_header: Callable[..., dict[str, str]],
    now: datetime,
) -> None:
    owner = make_user()

    response = client.post(
        "/api/v1/leagues",
        json={"id": str(uuid7()), "name": "Thursday DYP"},
        headers=auth_header(owner.id),
    )

    body = response.json()
    assert body["draws_allowed"] is False
    assert body["default_field_count"] == 1
    assert body["default_match_format"] == "bo1"
    assert body["default_goals_per_game"] == 10
    assert len(body["share_token"]) >= 22
    [season] = body["seasons"]
    assert season == {
        "id": season["id"],
        "number": 1,
        "name": None,
        "state": "active",
        "placement_points": [10, 8, 6, 4, 2],
        "started_at": now.isoformat().replace("+00:00", "Z"),
        "closed_at": None,
    }


def test_fr010_a_league_is_not_stored_when_its_season_1_fails(
    client: TestClient,
    session: Session,
    make_user: Callable[..., User],
    auth_header: Callable[..., dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = make_user()
    league_id = uuid7()
    # An increasing table fails the seasons CHECK at the flush.
    monkeypatch.setattr(league_service, "DEFAULT_PLACEMENT_POINTS", (1, 2))
    lenient = TestClient(client.app, raise_server_exceptions=False)

    with redirect_stderr(io.StringIO()):  # the handler logs the constraint
        response = lenient.post(
            "/api/v1/leagues",
            json={"id": str(league_id), "name": "Half"},
            headers=auth_header(owner.id),
        )

    assert response.status_code == 500
    assert session.get(League, league_id) is None


def test_fr007_get_lists_only_the_callers_leagues(
    client: TestClient,
    make_league: Callable[..., League],
    make_user: Callable[..., User],
    auth_header: Callable[..., dict[str, str]],
) -> None:
    owner = make_user()
    mine = make_league(owner_user_id=owner.id, name="Mine")
    make_league(name="Theirs")

    response = client.get("/api/v1/leagues", headers=auth_header(owner.id))

    assert response.status_code == 200
    assert response.json() == [{"id": str(mine.id), "name": "Mine"}]


def test_fr011_patch_sets_the_given_settings_only(
    client: TestClient,
    make_league: Callable[..., League],
    auth_header: Callable[..., dict[str, str]],
) -> None:
    league = make_league(name="Old")

    response = client.patch(
        f"/api/v1/leagues/{league.id}",
        json={
            "name": " New ",
            "draws_allowed": True,
            "default_field_count": 3,
            "default_match_format": "bo5",
            "default_goals_per_game": 7,
        },
        headers=auth_header(league.owner_user_id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "New"
    assert body["draws_allowed"] is True
    assert body["default_field_count"] == 3
    assert body["default_match_format"] == "bo5"
    assert body["default_goals_per_game"] == 7
    assert body["share_token"] == league.share_token


@pytest.mark.parametrize(
    ("field", "value", "error_type"),
    [
        pytest.param(
            "default_field_count", 0, "greater_than_equal", id="FR-011-0-fields"
        ),
        pytest.param(
            "default_goals_per_game", 0, "greater_than_equal", id="FR-011-0-goals"
        ),
        pytest.param(
            "default_field_count", 33, "less_than_equal", id="FR-011-33-fields"
        ),
        pytest.param(
            "default_goals_per_game", 100, "less_than_equal", id="FR-011-100-goals"
        ),
        pytest.param("default_match_format", "bo2", "enum", id="BR-121-no-bo2"),
        pytest.param("name", " ", "string_too_short", id="FR-011-blank-name"),
    ],
)
def test_fr011_patch_refuses_settings_the_database_would_refuse(
    client: TestClient,
    make_league: Callable[..., League],
    auth_header: Callable[..., dict[str, str]],
    field: str,
    value: object,
    error_type: str,
) -> None:
    league = make_league()

    response = client.patch(
        f"/api/v1/leagues/{league.id}",
        json={field: value},
        headers=auth_header(league.owner_user_id),
    )

    assert response.status_code == 422
    [error] = response.json()["detail"]["errors"]
    assert error["loc"] == ["body", field]
    assert error["type"] == error_type


def test_fr011_patch_accepts_the_largest_field_count_and_goals(
    client: TestClient,
    make_league: Callable[..., League],
    auth_header: Callable[..., dict[str, str]],
) -> None:
    league = make_league()

    response = client.patch(
        f"/api/v1/leagues/{league.id}",
        json={"default_field_count": 32, "default_goals_per_game": 99},
        headers=auth_header(league.owner_user_id),
    )

    assert response.status_code == 200
    assert response.json()["default_field_count"] == 32
    assert response.json()["default_goals_per_game"] == 99


def test_fr013_delete_removes_the_league_and_every_season(
    client: TestClient,
    session: Session,
    make_league: Callable[..., League],
    auth_header: Callable[..., dict[str, str]],
) -> None:
    league = make_league()
    headers = auth_header(league.owner_user_id)
    client.post(
        f"/api/v1/leagues/{league.id}/seasons",
        json={"expected_current_number": 1},
        headers=headers,
    )

    response = client.delete(f"/api/v1/leagues/{league.id}", headers=headers)

    assert response.status_code == 204
    session.expire_all()
    assert session.get(League, league.id) is None
    remaining = session.scalars(select(Season.id).where(Season.league_id == league.id))
    assert remaining.all() == []
    again = client.delete(f"/api/v1/leagues/{league.id}", headers=headers)
    assert again.status_code == 404


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        pytest.param("PATCH", "", {"name": "Taken"}, id="update"),
        pytest.param("DELETE", "", None, id="delete"),
        pytest.param(
            "POST", "/seasons", {"expected_current_number": 1}, id="start-season"
        ),
        pytest.param("PUT", "/seasons/{season}/name", {"name": "X"}, id="rename"),
        pytest.param(
            "PUT",
            "/seasons/{season}/placement-points",
            {"placement_points": [1]},
            id="placement-points",
        ),
    ],
)
def test_fr007_another_organizers_league_is_not_found_and_unchanged(
    client: TestClient,
    session: Session,
    make_league: Callable[..., League],
    make_user: Callable[..., User],
    auth_header: Callable[..., dict[str, str]],
    method: str,
    path: str,
    body: dict[str, object] | None,
) -> None:
    league = make_league(name="Theirs")
    [season] = league.seasons
    stranger = make_user()

    response = client.request(
        method,
        f"/api/v1/leagues/{league.id}" + path.format(season=season.id),
        json=body,
        headers=auth_header(stranger.id),
    )

    assert response.status_code == 404
    assert response.json() == {"code": "league_not_found", "detail": {}}
    session.expire_all()
    unchanged = session.get_one(League, league.id)
    assert unchanged.name == "Theirs"
    assert session.get_one(Season, season.id).name is None


def test_another_leagues_season_is_not_found(
    client: TestClient,
    make_league: Callable[..., League],
    auth_header: Callable[..., dict[str, str]],
) -> None:
    league = make_league()
    other = make_league(owner_user_id=league.owner_user_id)

    response = client.put(
        f"/api/v1/leagues/{league.id}/seasons/{other.seasons[0].id}/name",
        json={"name": "Mixed"},
        headers=auth_header(league.owner_user_id),
    )

    assert response.status_code == 404
    assert response.json() == {"code": "season_not_found", "detail": {}}


def test_fr021_post_season_closes_the_active_one_and_starts_the_next(
    client: TestClient,
    make_league: Callable[..., League],
    auth_header: Callable[..., dict[str, str]],
    travel: Callable[[timedelta], datetime],
) -> None:
    league = make_league()
    later = travel(timedelta(days=60))
    headers = auth_header(league.owner_user_id, issued_at=later)

    response = client.post(
        f"/api/v1/leagues/{league.id}/seasons",
        json={"expected_current_number": 1},
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["number"] == 2
    assert response.json()["state"] == "active"
    seasons = client.get(f"/api/v1/leagues/{league.id}", headers=headers).json()[
        "seasons"
    ]
    assert [(s["number"], s["state"]) for s in seasons] == [
        (1, "closed"),
        (2, "active"),
    ]
    assert seasons[0]["closed_at"] == later.isoformat().replace("+00:00", "Z")


def test_adr008_a_repeated_season_start_is_a_conflict(
    client: TestClient,
    make_league: Callable[..., League],
    auth_header: Callable[..., dict[str, str]],
) -> None:
    league = make_league()
    headers = auth_header(league.owner_user_id)
    start = {"expected_current_number": 1}
    client.post(f"/api/v1/leagues/{league.id}/seasons", json=start, headers=headers)

    response = client.post(
        f"/api/v1/leagues/{league.id}/seasons", json=start, headers=headers
    )

    assert response.status_code == 409
    assert response.json() == {
        "code": "season_number_changed",
        "detail": {"current_number": 2},
    }


def test_fr020_put_name_renames_a_season_and_null_restores_the_default(
    client: TestClient,
    make_league: Callable[..., League],
    auth_header: Callable[..., dict[str, str]],
) -> None:
    league = make_league()
    [season] = league.seasons
    url = f"/api/v1/leagues/{league.id}/seasons/{season.id}/name"
    headers = auth_header(league.owner_user_id)

    renamed = client.put(url, json={"name": " Autumn "}, headers=headers)
    restored = client.put(url, json={"name": None}, headers=headers)

    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Autumn"
    assert restored.json()["name"] is None


def test_br011_a_closed_season_and_its_league_can_still_be_renamed(
    client: TestClient,
    make_league: Callable[..., League],
    auth_header: Callable[..., dict[str, str]],
) -> None:
    league = make_league()
    [first] = league.seasons
    headers = auth_header(league.owner_user_id)
    client.post(
        f"/api/v1/leagues/{league.id}/seasons",
        json={"expected_current_number": 1},
        headers=headers,
    )

    season = client.put(
        f"/api/v1/leagues/{league.id}/seasons/{first.id}/name",
        json={"name": "Spring"},
        headers=headers,
    )
    renamed_league = client.patch(
        f"/api/v1/leagues/{league.id}", json={"name": "Renamed"}, headers=headers
    )

    assert season.status_code == 200
    assert season.json()["name"] == "Spring"
    assert renamed_league.status_code == 200


def test_br012_put_placement_points_replaces_the_active_seasons_table(
    client: TestClient,
    make_league: Callable[..., League],
    auth_header: Callable[..., dict[str, str]],
) -> None:
    league = make_league()
    [season] = league.seasons

    response = client.put(
        f"/api/v1/leagues/{league.id}/seasons/{season.id}/placement-points",
        json={"placement_points": [15, 10, 10, 0]},
        headers=auth_header(league.owner_user_id),
    )

    assert response.status_code == 200
    assert response.json()["placement_points"] == [15, 10, 10, 0]


def test_br011_a_closed_seasons_table_is_a_conflict_and_stays(
    client: TestClient,
    make_league: Callable[..., League],
    auth_header: Callable[..., dict[str, str]],
) -> None:
    league = make_league()
    [first] = league.seasons
    headers = auth_header(league.owner_user_id)
    client.post(
        f"/api/v1/leagues/{league.id}/seasons",
        json={"expected_current_number": 1},
        headers=headers,
    )

    response = client.put(
        f"/api/v1/leagues/{league.id}/seasons/{first.id}/placement-points",
        json={"placement_points": [1]},
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json() == {"code": "season_closed", "detail": {}}
    seasons = client.get(f"/api/v1/leagues/{league.id}", headers=headers).json()[
        "seasons"
    ]
    assert seasons[0]["placement_points"] == [10, 8, 6, 4, 2]


@pytest.mark.parametrize(
    ("points", "error"),
    [
        pytest.param(
            [],
            {"loc": ["body", "placement_points"], "type": "too_short"},
            id="FR-011-empty",
        ),
        pytest.param(
            [10, -1],
            {"loc": ["body", "placement_points", 1], "type": "greater_than_equal"},
            id="FR-011-negative",
        ),
        pytest.param(
            [10, 8, 9],
            {
                "loc": ["body", "placement_points"],
                "type": "placement_points_increase",
                "place": 3,
            },
            id="FR-011-increasing",
        ),
        pytest.param(
            [10, None],
            {"loc": ["body", "placement_points", 1], "type": "int_type"},
            id="FR-011-null",
        ),
        pytest.param(
            [[10], [8]],
            {"loc": ["body", "placement_points", 0], "type": "int_type"},
            id="FR-011-two-dimensional",
        ),
        pytest.param(
            [2.5],
            {"loc": ["body", "placement_points", 0], "type": "int_from_float"},
            id="FR-011-whole-numbers",
        ),
        pytest.param(
            [0] * 257,
            {"loc": ["body", "placement_points"], "type": "too_long"},
            id="ADR-009-at-most-256-places",
        ),
    ],
)
def test_fr011_put_placement_points_refuses_what_the_check_refuses(
    client: TestClient,
    make_league: Callable[..., League],
    auth_header: Callable[..., dict[str, str]],
    points: list[object],
    error: dict[str, object],
) -> None:
    league = make_league()
    [season] = league.seasons

    response = client.put(
        f"/api/v1/leagues/{league.id}/seasons/{season.id}/placement-points",
        json={"placement_points": points},
        headers=auth_header(league.owner_user_id),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_failed"
    problem = response.json()["detail"]["errors"][0]
    assert {key: problem[key] for key in error} == error


@pytest.mark.concurrency
def test_adr008_of_two_starts_of_season_2_exactly_one_wins(
    committing_settings: Settings,
    committing_engine: Engine,
    now: datetime,
    auth_header: Callable[..., dict[str, str]],
    wait_for_a_lock_wait: Callable[[], None],
) -> None:
    with Session(committing_engine) as setup:
        owner = User(
            email="seasons@example.test",
            display_name="Seasons",
            password_hash="!",
            language=Language.EN,
            created_at=now,
        )
        setup.add(owner)
        setup.flush()
        league = league_service.create_league(
            setup, league_id=uuid7(), owner_user_id=owner.id, name="Race", now=now
        )
        setup.commit()
        owner_id, league_id = owner.id, league.id
    outcome: list[tuple[int, object]] = []

    with (
        Session(committing_engine) as first,
        TestClient(create_app(committing_settings)) as client,
    ):
        league_service.start_season(
            first,
            league_id=league_id,
            user_id=owner_id,
            expected_current_number=1,
            now=now,
        )

        def start_second() -> None:
            response = client.post(
                f"/api/v1/leagues/{league_id}/seasons",
                json={"expected_current_number": 1},
                # The app reads the system clock here, not the test's `now`.
                headers=auth_header(owner_id, issued_at=datetime.now(UTC)),
            )
            outcome.append((response.status_code, response.json()))

        second = threading.Thread(target=start_second)
        second.start()
        wait_for_a_lock_wait()  # it waits for the league lock the first one holds
        first.commit()
        second.join()

    assert outcome == [
        (409, {"code": "season_number_changed", "detail": {"current_number": 2}})
    ]
    with Session(committing_engine) as check:
        seasons = check.execute(
            select(Season.number, Season.state)
            .where(Season.league_id == league_id)
            .order_by(Season.number)
        ).all()
    assert [tuple(row) for row in seasons] == [
        (1, SeasonState.CLOSED),
        (2, SeasonState.ACTIVE),
    ]
