from collections.abc import Callable
from typing import Any
from uuid import uuid7

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tourneyhub.db.models.leagues import League, Player

type Json = dict[str, Any]

ROUND_ROBIN: Json = {
    "name": "Thursday",
    "date": "2026-11-12",
    "type": "singles",
    "group_phase": "round_robin",
    "round_robin_legs": 1,
    "sit_out_points": 0,
    "group_match_format": "bo1",
    "knockout_match_format": None,
    "final_match_format": None,
    "third_place_match": None,
    "goals_per_game": 10,
    "field_count": 2,
}

UNKNOWN = {"code": "share_link_not_found", "detail": {}}


def _public(league: League | str, rest: str = "") -> str:
    token = league.share_token if isinstance(league, League) else league
    return f"/api/v1/public/{token}{rest}"


@pytest.fixture
def league(make_league: Callable[..., League]) -> League:
    return make_league(name="Thursday Foosball")


@pytest.fixture
def headers(
    league: League, auth_header: Callable[..., dict[str, str]]
) -> dict[str, str]:
    return auth_header(league.owner_user_id)


@pytest.fixture
def players(league: League, make_player: Callable[..., Player]) -> list[Player]:
    return [make_player(league=league, name=f"P{n}") for n in range(1, 6)]


@pytest.fixture
def make_started(client: TestClient, players: list[Player]) -> Callable[..., Json]:
    """A round robin of the league's players, started unless `start` is false."""

    def make_started(
        league: League, headers: dict[str, str], *, start: bool = True, **values: object
    ) -> Json:
        base = f"/api/v1/leagues/{league.id}/tournaments"
        body = {"id": str(uuid7()), **ROUND_ROBIN, **values}
        created = client.post(base, json=body, headers=headers)
        assert created.status_code == 201, created.text
        tournament_id = created.json()["tournament_id"]
        picked = client.put(
            f"{base}/{tournament_id}/setup/players",
            json={"player_ids": [str(p.id) for p in players]},
            headers=headers,
        )
        assert picked.status_code == 200, picked.text
        if not start:
            setup: Json = picked.json()
            return setup
        started = client.post(
            f"{base}/{tournament_id}/start",
            json={"expected_draw_counter": picked.json()["draw_counter"]},
            headers=headers,
        )
        assert started.status_code == 200, started.text
        result: Json = started.json()
        return result

    return make_started


def _season_id(league: League) -> str:
    """Read before the first request: its commit expires `league.seasons`."""
    return str(league.seasons[0].id)


@pytest.fixture
def season_id(league: League) -> str:
    return _season_id(league)


# ---------------------------------------------------------------- the league


def test_fr070_the_share_link_shows_the_league_without_an_account(
    client: TestClient,
    league: League,
    season_id: str,
    players: list[Player],
    session: Session,
) -> None:
    placement_points = league.seasons[0].placement_points
    players[1].removed_at = league.created_at
    session.flush()

    response = client.get(_public(league))

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "name": "Thursday Foosball",
        "seasons": [
            {
                "id": season_id,
                "number": 1,
                "name": None,
                "state": "active",
                "placement_points": placement_points,
                "started_at": body["seasons"][0]["started_at"],
                "closed_at": None,
            }
        ],
        # Removed players keep their names in past results.
        "players": [{"id": str(p.id), "name": p.name} for p in players],
    }


@pytest.mark.parametrize(
    "token",
    [
        pytest.param("unknown-token", id="unknown"),
        pytest.param("x" * 129, id="too-long"),
        pytest.param("%20", id="blank"),
    ],
)
@pytest.mark.usefixtures("league")
def test_fr071_an_unknown_share_token_is_404_with_nothing_in_it(
    client: TestClient, token: str
) -> None:
    response = client.get(_public(token))

    assert (response.status_code, response.json()) == (404, UNKNOWN)


def test_fr071_another_leagues_token_with_one_character_changed_is_unknown(
    client: TestClient, league: League
) -> None:
    token = league.share_token[:-1] + ("A" if league.share_token[-1] != "A" else "B")

    response = client.get(_public(token))

    assert (response.status_code, response.json()) == (404, UNKNOWN)


def test_fr013_a_deleted_leagues_share_link_stops_working(
    client: TestClient, league: League, headers: dict[str, str]
) -> None:
    token = league.share_token
    deleted = client.delete(f"/api/v1/leagues/{league.id}", headers=headers)
    assert deleted.status_code == 204

    for path in (
        _public(token),
        _public(token, f"/seasons/{uuid7()}/tournaments"),
        _public(token, f"/tournaments/{uuid7()}"),
        _public(token, f"/seasons/{uuid7()}/standings"),
        _public(token, f"/tournaments/{uuid7()}/standings"),
        _public(token, f"/tournaments/{uuid7()}/places"),
    ):
        response = client.get(path)
        assert (response.status_code, response.json()) == (404, UNKNOWN), path


@pytest.mark.parametrize(
    "rest",
    [
        pytest.param("", id="league"),
        pytest.param("/seasons/{season}/tournaments", id="tournaments"),
        pytest.param("/tournaments/{tournament}", id="tournament"),
        pytest.param("/seasons/{season}/standings", id="season-standings"),
        pytest.param("/tournaments/{tournament}/standings", id="standings"),
        pytest.param("/tournaments/{tournament}/places", id="places"),
    ],
)
def test_fr071_every_route_answers_an_unknown_token_alike(
    client: TestClient, season_id: str, rest: str
) -> None:
    path = rest.format(season=season_id, tournament=uuid7())

    response = client.get(_public("unknown-token", path))

    assert (response.status_code, response.json()) == (404, UNKNOWN)


def test_fr072_the_share_link_changes_nothing(
    client: TestClient, league: League
) -> None:
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        response = client.request(method, _public(league))
        assert response.status_code == 405, method
        assert response.json()["code"] == "method_not_allowed"


def test_fr070_an_access_token_is_not_needed_and_changes_nothing(
    client: TestClient, league: League, auth_header: Callable[..., dict[str, str]]
) -> None:
    other_owner = auth_header(uuid7())

    response = client.get(_public(league), headers=other_owner)

    assert response.status_code == 200
    assert response.json()["name"] == "Thursday Foosball"


# ---------------------------------------------------------------- tournaments


def test_fr070_a_seasons_tournaments_are_listed_without_those_in_setup(
    client: TestClient,
    league: League,
    season_id: str,
    headers: dict[str, str],
    make_started: Callable[..., Json],
) -> None:
    started = make_started(league, headers, name="Started")
    make_started(league, headers, start=False, name="In setup")
    organizer = client.get(
        f"/api/v1/leagues/{league.id}/seasons/{season_id}/tournaments",
        headers=headers,
    ).json()

    response = client.get(_public(league, f"/seasons/{season_id}/tournaments"))

    assert response.status_code == 200
    assert [t["id"] for t in response.json()] == [started["id"]]
    assert response.json() == [t for t in organizer if t["state"] != "setup"]


def test_fr070_another_leagues_season_is_not_found(
    client: TestClient, league: League, make_league: Callable[..., League]
) -> None:
    other = make_league()

    response = client.get(_public(league, f"/seasons/{_season_id(other)}/tournaments"))

    assert (response.status_code, response.json()) == (
        404,
        {"code": "season_not_found", "detail": {}},
    )


def test_fr070_the_tournament_reads_as_the_organizer_sees_it(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    make_started: Callable[..., Json],
) -> None:
    started = make_started(league, headers)

    response = client.get(_public(league, f"/tournaments/{started['id']}"))

    assert response.status_code == 200
    body = response.json()
    assert body == started
    assert body["state"] == "in_progress"
    assert len(body["rounds"]) == 5
    assert [f["match_id"] for f in body["fields"]] == [
        m["id"] for m in body["rounds"][0]["matches"]
    ]
    assert body["waiting"][0] == body["rounds"][1]["matches"][0]["id"]


def test_fr070_a_tournament_in_setup_is_not_found(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    make_started: Callable[..., Json],
) -> None:
    setup = make_started(league, headers, start=False)

    in_setup = client.get(_public(league, f"/tournaments/{setup['tournament_id']}"))
    unknown = client.get(_public(league, f"/tournaments/{uuid7()}"))

    assert (in_setup.status_code, in_setup.json()) == (
        unknown.status_code,
        unknown.json(),
    )
    assert unknown.json() == {"code": "tournament_not_found", "detail": {}}


def test_fr036_back_to_setup_hides_the_tournament_again(
    client: TestClient,
    league: League,
    season_id: str,
    headers: dict[str, str],
    make_started: Callable[..., Json],
) -> None:
    started = make_started(league, headers)
    back = client.post(
        f"/api/v1/leagues/{league.id}/tournaments/{started['id']}/back-to-setup",
        json={"expected_state": "in_progress"},
        headers=headers,
    )
    assert back.status_code == 200

    response = client.get(_public(league, f"/tournaments/{started['id']}"))
    listed = client.get(_public(league, f"/seasons/{season_id}/tournaments"))

    assert response.status_code == 404
    assert listed.json() == []


def test_owasp_api1_a_valid_token_does_not_open_another_leagues_tournament(
    client: TestClient,
    league: League,
    make_league: Callable[..., League],
    make_player: Callable[..., Player],
    auth_header: Callable[..., dict[str, str]],
) -> None:
    other = make_league()
    for n in range(4):
        make_player(league=other, name=f"Other {n}")
    other_headers = auth_header(other.owner_user_id)
    base = f"/api/v1/leagues/{other.id}/tournaments"
    created = client.post(
        base, json={"id": str(uuid7()), **ROUND_ROBIN}, headers=other_headers
    )
    tournament_id = created.json()["tournament_id"]
    other_players = client.get(
        f"/api/v1/leagues/{other.id}/players", headers=other_headers
    ).json()
    picked = client.put(
        f"{base}/{tournament_id}/setup/players",
        json={"player_ids": [p["id"] for p in other_players]},
        headers=other_headers,
    )
    started = client.post(
        f"{base}/{tournament_id}/start",
        json={"expected_draw_counter": picked.json()["draw_counter"]},
        headers=other_headers,
    )
    assert started.status_code == 200
    assert (
        client.get(_public(other, f"/tournaments/{tournament_id}")).status_code == 200
    )

    response = client.get(_public(league, f"/tournaments/{tournament_id}"))

    assert (response.status_code, response.json()) == (
        404,
        {"code": "tournament_not_found", "detail": {}},
    )


# ---------------------------------------------------------------- headers


@pytest.mark.parametrize(
    "rest",
    [
        pytest.param("", id="league"),
        pytest.param("/seasons/{season}/tournaments", id="tournaments"),
        pytest.param("/tournaments/{tournament}", id="unknown-tournament"),
        pytest.param("/seasons/{season}/standings", id="season-standings"),
        pytest.param("/seasons/not-a-uuid/standings", id="season-standings-422"),
        pytest.param("/tournaments/{tournament}/standings", id="standings"),
        pytest.param("/tournaments/{tournament}/places", id="places"),
        pytest.param("/tournaments/not-a-uuid/places", id="places-422"),
        pytest.param("/tournaments/not-a-uuid", id="validation-error"),
        pytest.param("/seasons/not-a-uuid/tournaments", id="invalid-season-422"),
        pytest.param("/no-such-route", id="router-404"),
    ],
)
@pytest.mark.parametrize("known", [True, False], ids=["known", "unknown"])
def test_adr005_public_answers_are_not_cached_and_send_no_referrer(
    client: TestClient, league: League, season_id: str, rest: str, *, known: bool
) -> None:
    token = league.share_token if known else "unknown-token"
    path = rest.format(season=season_id, tournament=uuid7())

    response = client.get(_public(token, path))

    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"


def test_adr005_organizer_answers_keep_their_headers(
    client: TestClient, league: League, headers: dict[str, str]
) -> None:
    response = client.get(f"/api/v1/leagues/{league.id}", headers=headers)

    assert "Cache-Control" not in response.headers
    assert "Referrer-Policy" not in response.headers


# ---------------------------------------------------------------- schemas


_ORGANIZER_ONLY = {
    "share_token",
    "owner_user_id",
    "email",
    "user_id",
    "is_admin",
    "draw_counter",
    "rng_seed",
    "seeding_method",
    "halves_method",
    "ranking",
    "created_at",
    "updated_at",
}


def _properties(schemas: Json, node: object, seen: set[str]) -> set[str]:
    """Every property name reachable from a schema node, through its refs."""
    found: set[str] = set()
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            name = ref.rsplit("/", 1)[-1]
            if name not in seen:
                seen.add(name)
                found |= _properties(schemas, schemas[name], seen)
        properties = node.get("properties")
        if isinstance(properties, dict):
            found |= set(properties)
        for value in node.values():
            found |= _properties(schemas, value, seen)
    elif isinstance(node, list):
        for value in node:
            found |= _properties(schemas, value, seen)
    return found


def test_fr071_public_schemas_carry_nothing_only_the_organizer_sees(
    client: TestClient,
) -> None:
    schema: Json = client.get("/openapi.json").json()
    public = {
        path: item
        for path, item in schema["paths"].items()
        if path.startswith("/api/v1/public/")
    }

    names = _properties(
        schema["components"]["schemas"],
        [item["get"]["responses"]["200"] for item in public.values()],
        set(),
    )

    assert len(public) == 6
    assert all(set(item) == {"get"} for item in public.values())  # FR-072
    assert {"name", "players", "rounds", "fields", "waiting"} <= names
    assert {"tournaments_played", "points_per_player", "score_difference"} <= names
    assert not names & _ORGANIZER_ONLY
