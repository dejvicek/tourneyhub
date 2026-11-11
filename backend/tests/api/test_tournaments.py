import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4, uuid7

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from tourneyhub.app import create_app
from tourneyhub.db.models.accounts import User
from tourneyhub.db.models.entries import EntryMember
from tourneyhub.db.models.leagues import League, Player, Season
from tourneyhub.db.models.tournaments import (
    Tournament,
    TournamentPhase,
    TournamentPlayer,
)
from tourneyhub.engine.accounts import Language
from tourneyhub.engine.leagues import SeasonState
from tourneyhub.engine.tournaments import (
    GroupPhase,
    SeedingMethod,
    TournamentState,
    TournamentType,
)
from tourneyhub.services import leagues as league_service
from tourneyhub.services import players as player_service
from tourneyhub.services import tournaments as tournament_service
from tourneyhub.settings import Settings

type Json = dict[str, Any]

SINGLES_ROUND_ROBIN: Json = {
    "name": "Thursday",
    "date": "2026-11-12",
    "type": "singles",
    "group_phase": "round_robin",
    "round_robin_legs": 1,
    "sit_out_points": None,
    "group_match_format": "bo1",
    "knockout_match_format": None,
    "final_match_format": None,
    "third_place_match": None,
    "goals_per_game": 10,
    "field_count": 2,
}


def _url(league: League | UUID, rest: str = "") -> str:
    league_id = league.id if isinstance(league, League) else league
    return f"/api/v1/leagues/{league_id}{rest}"


def _tournament_url(league: League | UUID, tournament_id: str, rest: str = "") -> str:
    return _url(league, f"/tournaments/{tournament_id}{rest}")


def _create(
    client: TestClient, league: League, headers: dict[str, str], **values: object
) -> Json:
    body = {"id": str(uuid7()), **SINGLES_ROUND_ROBIN, **values}
    response = client.post(_url(league, "/tournaments"), json=body, headers=headers)
    assert response.status_code == 201, response.text
    created: Json = response.json()
    return created


def _write(
    client: TestClient,
    league: League | UUID,
    tournament_id: str,
    what: str,
    body: Json,
    headers: dict[str, str],
    *,
    method: str = "PUT",
) -> tuple[int, Json]:
    response = client.request(
        method, _tournament_url(league, tournament_id, what), json=body, headers=headers
    )
    result: Json = response.json()
    return response.status_code, result


def _ok(status_and_body: tuple[int, Json]) -> Json:
    status, body = status_and_body
    assert status == 200, body
    return body


@pytest.fixture
def league(make_league: Callable[..., League]) -> League:
    return make_league()


@pytest.fixture
def draws_league(league: League, session: Session) -> League:
    """The league with draws allowed: a sit-out can default to a draw (BR-071)."""
    league.draws_allowed = True
    session.flush()
    return league


@pytest.fixture
def season_id(league: League) -> UUID:
    """The active season's id, read before a request expires the league."""
    return league.seasons[0].id


@pytest.fixture
def headers(
    league: League, auth_header: Callable[..., dict[str, str]]
) -> dict[str, str]:
    return auth_header(league.owner_user_id)


@pytest.fixture
def players(league: League, make_player: Callable[..., Player]) -> list[str]:
    return [str(make_player(league=league, name=f"P{n}").id) for n in range(1, 10)]


# ---------------------------------------------------------------- create


def test_fr030_post_creates_a_tournament_in_setup_in_the_active_season(
    client: TestClient,
    league: League,
    season_id: UUID,
    headers: dict[str, str],
    session: Session,
) -> None:
    tournament_id = str(uuid7())

    response = client.post(
        _url(league, "/tournaments"),
        json={"id": tournament_id, **SINGLES_ROUND_ROBIN},
        headers=headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["tournament_id"] == tournament_id
    assert body["state"] == "setup"
    assert body["format"] == {
        **SINGLES_ROUND_ROBIN,
        "sit_out_points_set_by_hand": False,
    }
    assert body["draw_counter"] == 0
    assert body["seeding_method"] == "ranking"
    assert body["player_ids"] == body["entries"] == body["halves"] == []
    stored = session.get_one(Tournament, UUID(tournament_id))
    assert stored.season_id == season_id
    assert len(stored.rng_seed) == 16


def test_fr011_a_create_without_settings_takes_the_league_defaults(
    client: TestClient, league: League, headers: dict[str, str], session: Session
) -> None:
    league.default_field_count = 3
    league.default_goals_per_game = 7
    league.default_match_format = "bo3"  # type: ignore[assignment]
    session.flush()
    body = {
        "id": str(uuid7()),
        "name": "Knockout",
        "date": "2026-11-12",
        "type": "doubles",
        "group_phase": "none",
    }

    response = client.post(_url(league, "/tournaments"), json=body, headers=headers)

    assert response.status_code == 201
    assert response.json()["format"] == {
        "name": "Knockout",
        "date": "2026-11-12",
        "type": "doubles",
        "group_phase": "none",
        "round_robin_legs": None,
        "sit_out_points": None,
        "sit_out_points_set_by_hand": None,
        "group_match_format": None,
        "knockout_match_format": "bo3",
        "final_match_format": None,
        "third_place_match": False,
        "goals_per_game": 7,
        "field_count": 3,
    }


@pytest.mark.usefixtures("draws_league")
def test_fr030_a_group_phase_takes_the_league_format_and_one_leg(
    client: TestClient, league: League, headers: dict[str, str]
) -> None:
    body = {
        "id": str(uuid7()),
        "name": "Swiss",
        "date": "2026-11-12",
        "type": "singles",
        "group_phase": "swiss",
    }

    response = client.post(_url(league, "/tournaments"), json=body, headers=headers)

    fmt = response.json()["format"]
    assert (fmt["round_robin_legs"], fmt["sit_out_points"]) == (None, 1)
    assert fmt["sit_out_points_set_by_hand"] is False
    assert fmt["group_match_format"] == "bo1"


def test_adr008_a_repeated_create_returns_the_same_tournament(
    client: TestClient, league: League, headers: dict[str, str]
) -> None:
    created = _create(client, league, headers)
    body = {"id": created["tournament_id"], **SINGLES_ROUND_ROBIN, "name": "Other"}

    response = client.post(_url(league, "/tournaments"), json=body, headers=headers)

    assert response.status_code == 201
    assert response.json() == created


@pytest.mark.parametrize(
    "other",
    [
        pytest.param("type", id="ADR-008-other-type"),
        pytest.param("league", id="ADR-008-other-league"),
    ],
)
def test_adr008_an_id_of_another_tournament_is_a_conflict(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    make_league: Callable[..., League],
    auth_header: Callable[..., dict[str, str]],
    other: str,
) -> None:
    created = _create(client, league, headers)
    body: Json = {"id": created["tournament_id"], **SINGLES_ROUND_ROBIN}
    target, target_headers = league, headers
    if other == "type":
        body |= {"type": "doubles"}
    else:
        target = make_league()
        target_headers = auth_header(target.owner_user_id)

    response = client.post(
        _url(target, "/tournaments"), json=body, headers=target_headers
    )

    assert response.status_code == 409
    assert response.json() == {"code": "tournament_id_taken", "detail": {}}


def test_br121_bo2_needs_a_league_that_allows_draws(
    client: TestClient, league: League, headers: dict[str, str], session: Session
) -> None:
    body = {"id": str(uuid7()), **SINGLES_ROUND_ROBIN, "group_match_format": "bo2"}

    refused = client.post(_url(league, "/tournaments"), json=body, headers=headers)
    league.draws_allowed = True
    session.flush()
    allowed = client.post(_url(league, "/tournaments"), json=body, headers=headers)

    assert refused.status_code == 422
    assert refused.json() == {"code": "draws_not_allowed", "detail": {}}
    assert allowed.status_code == 201


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        pytest.param(
            {"type": "monster_dyp"}, "group_phase_mismatch", id="FR-031-monster-in-rr"
        ),
        pytest.param(
            {"group_phase": "monster_dyp"},
            "group_phase_mismatch",
            id="FR-031-singles-in-monster-rounds",
        ),
        pytest.param(
            {"knockout_match_format": "bo3"},
            "setting_not_applicable",
            id="FR-045-knockout-format-with-a-group-phase",
        ),
        pytest.param(
            {"group_phase": "swiss", "round_robin_legs": 2},
            "setting_not_applicable",
            id="BR-050-legs-in-swiss",
        ),
        pytest.param(
            {"group_phase": "none", "sit_out_points": 1, "round_robin_legs": None},
            "setting_not_applicable",
            id="FR-039-sit-out-without-a-group-phase",
        ),
        pytest.param({"id": str(uuid4())}, "uuid_version", id="ADR-008-not-uuid7"),
        pytest.param({"goals_per_game": 100}, "less_than_equal", id="BR-123-goals"),
        pytest.param({"field_count": 33}, "less_than_equal", id="FR-090-fields"),
        pytest.param({"name": "  "}, "string_too_short", id="FR-030-blank-name"),
    ],
)
def test_fr031_a_create_whose_settings_do_not_fit_is_refused(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    changes: Json,
    error: str,
) -> None:
    body = {"id": str(uuid7()), **SINGLES_ROUND_ROBIN, **changes}

    response = client.post(_url(league, "/tournaments"), json=body, headers=headers)

    assert response.status_code == 422
    assert response.json()["code"] == "validation_failed"
    assert [e["type"] for e in response.json()["detail"]["errors"]] == [error]


# ---------------------------------------------------------------- read and list


def test_fr032_get_setup_ranks_every_player_on_the_list(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    players: list[str],
    session: Session,
) -> None:
    created = _create(client, league, headers)
    session.get_one(Player, UUID(players[0])).removed_at = datetime.now(UTC)
    session.flush()

    response = client.get(
        _tournament_url(league, created["tournament_id"], "/setup"), headers=headers
    )

    assert response.status_code == 200
    ranking = response.json()["ranking"]
    assert [row["rank"] for row in ranking] == list(range(1, 9))
    assert {row["player_id"] for row in ranking} == set(players[1:])
    assert {row["points"] for row in ranking} == {0}


def test_adr010_the_ranking_lot_is_the_same_on_every_read(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    created = _create(client, league, headers)
    url = _tournament_url(league, created["tournament_id"], "/setup")

    first = client.get(url, headers=headers).json()["ranking"]
    second = client.get(url, headers=headers).json()["ranking"]

    assert first == second
    assert len(first) == len(players)


def test_fr022_get_lists_the_seasons_tournaments_newest_first(
    client: TestClient,
    league: League,
    season_id: UUID,
    headers: dict[str, str],
    players: list[str],
) -> None:
    older = _create(client, league, headers, date="2026-11-05")
    newer = _create(client, league, headers, date="2026-11-12")
    _ok(
        _write(
            client,
            league,
            older["tournament_id"],
            "/setup/players",
            {"player_ids": players[:3]},
            headers,
        )
    )

    response = client.get(
        _url(league, f"/seasons/{season_id}/tournaments"), headers=headers
    )

    assert response.status_code == 200
    listed = response.json()
    assert [t["id"] for t in listed] == [newer["tournament_id"], older["tournament_id"]]
    assert listed[1] == {
        "id": older["tournament_id"],
        "season_id": str(season_id),
        "name": "Thursday",
        "date": "2026-11-05",
        "type": "singles",
        "state": "setup",
        "phases": [
            {
                "id": listed[1]["phases"][0]["id"],
                "position": 1,
                "kind": "group",
                "format": "round_robin",
            }
        ],
        "current_phase_id": None,
        "current_phase_done": False,
        "player_count": 3,
        "progress": None,
        "winner_player_ids": None,
    }


def test_fr022_another_leagues_season_is_not_found(
    client: TestClient,
    headers: dict[str, str],
    league: League,
    make_league: Callable[..., League],
) -> None:
    other = make_league(owner_user_id=league.owner_user_id)

    response = client.get(
        _url(league, f"/seasons/{other.seasons[0].id}/tournaments"), headers=headers
    )

    assert response.status_code == 404
    assert response.json() == {"code": "season_not_found", "detail": {}}


def test_owasp_api1_a_tournament_of_another_league_is_not_found(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    make_league: Callable[..., League],
) -> None:
    other = make_league(owner_user_id=league.owner_user_id)
    created = _create(client, other, headers)

    read = client.get(
        _tournament_url(league, created["tournament_id"], "/setup"), headers=headers
    )
    status, body = _write(
        client,
        league,
        created["tournament_id"],
        "/setup/seeding",
        {"method": "random"},
        headers,
    )

    assert read.status_code == status == 404
    assert read.json() == body == {"code": "tournament_not_found", "detail": {}}


_ROUTES: list[tuple[str, str, Json | None]] = [
    ("GET", "/seasons/{season}/tournaments", None),
    ("POST", "/tournaments", {"id": "{new}", **SINGLES_ROUND_ROBIN}),
    ("DELETE", "/tournaments/{t}", None),
    ("GET", "/tournaments/{t}", None),
    ("POST", "/tournaments/{t}/start", {"expected_draw_counter": 0}),
    ("POST", "/tournaments/{t}/back-to-setup", {"expected_state": "in_progress"}),
    ("PUT", "/tournaments/{t}/format", SINGLES_ROUND_ROBIN),
    ("GET", "/tournaments/{t}/setup", None),
    ("PUT", "/tournaments/{t}/setup/players", {"player_ids": []}),
    ("PUT", "/tournaments/{t}/setup/pairs", {"pairs": []}),
    ("PUT", "/tournaments/{t}/setup/halves", {"method": "ranking", "halves": []}),
    ("PUT", "/tournaments/{t}/setup/seeding", {"method": "random"}),
    ("PUT", "/tournaments/{t}/setup/seed-order", {"entry_ids": []}),
    (
        "POST",
        "/tournaments/{t}/setup/draw",
        {"expected_draw_counter": 0, "target": "seeds"},
    ),
    (
        "PUT",
        "/tournaments/{t}/matches/{m}/result",
        {"walkover_winner": None, "games": []},
    ),
    ("GET", "/tournaments/{t}/play", None),
    ("POST", "/tournaments/{t}/finish", {"expected_state": "in_progress"}),
    ("GET", "/tournaments/{t}/places", None),
]


@pytest.mark.parametrize(("method", "path", "body"), _ROUTES)
def test_owasp_api1_another_organizers_league_is_not_found_on_every_route(
    client: TestClient,
    league: League,
    season_id: UUID,
    headers: dict[str, str],
    make_league: Callable[..., League],
    auth_header: Callable[..., dict[str, str]],
    session: Session,
    method: str,
    path: str,
    body: Json | None,
) -> None:
    created = _create(client, league, headers)
    intruder = auth_header(make_league().owner_user_id)
    url = _url(
        league,
        path.format(
            season=season_id, t=created["tournament_id"], new=uuid7(), m=uuid7()
        ),
    )
    if body is not None:
        body = {k: str(uuid7()) if v == "{new}" else v for k, v in body.items()}

    response = client.request(method, url, json=body, headers=intruder)

    assert response.status_code == 404
    assert response.json() == {"code": "league_not_found", "detail": {}}
    tournament = session.get_one(Tournament, UUID(created["tournament_id"]))
    session.refresh(tournament)
    assert tournament.draw_counter == 0


# ---------------------------------------------------------------- format


def test_fr030_put_format_sets_the_whole_format(
    client: TestClient, league: League, season_id: UUID, headers: dict[str, str]
) -> None:
    created = _create(client, league, headers)
    knockout = {
        **SINGLES_ROUND_ROBIN,
        "name": "Cup",
        "group_phase": "none",
        "round_robin_legs": None,
        "sit_out_points": None,
        "group_match_format": None,
        "knockout_match_format": "bo3",
        "final_match_format": "bo5",
        "third_place_match": True,
        "field_count": 1,
    }

    body = _ok(
        _write(client, league, created["tournament_id"], "/format", knockout, headers)
    )

    assert body["format"] == {**knockout, "sit_out_points_set_by_hand": None}
    listed = client.get(
        _url(league, f"/seasons/{season_id}/tournaments"), headers=headers
    ).json()
    assert [(p["kind"], p["format"]) for p in listed[0]["phases"]] == [
        ("knockout", "single_elimination")
    ]


def _swiss_format(**changes: object) -> Json:
    return {
        **SINGLES_ROUND_ROBIN,
        "group_phase": "swiss",
        "round_robin_legs": None,
        **changes,
    }


def _create_swiss(
    client: TestClient, league: League, headers: dict[str, str], **values: object
) -> Json:
    """A Swiss tournament: the sit-out points apply to it, not to a round robin."""
    return _create(
        client, league, headers, group_phase="swiss", round_robin_legs=None, **values
    )


def _put_format(
    client: TestClient,
    league: League,
    tournament_id: str,
    headers: dict[str, str],
    **changes: object,
) -> Json:
    fmt: Json = _ok(
        _write(
            client,
            league,
            tournament_id,
            "/format",
            _swiss_format(**changes),
            headers,
        )
    )["format"]
    return fmt


@pytest.mark.parametrize(
    ("draws_allowed", "match_format"),
    # BO2 needs a league with draws (BR-121), so that pair is not creatable.
    [
        (True, "bo1"),
        (True, "bo2"),
        (True, "bo3"),
        (True, "bo5"),
        (False, "bo1"),
        (False, "bo3"),
        (False, "bo5"),
    ],
)
def test_br071_a_create_without_sit_out_points_takes_the_default(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    session: Session,
    draws_allowed: bool,
    match_format: str,
) -> None:
    league.draws_allowed = draws_allowed
    session.flush()
    expected = 1 if draws_allowed and match_format in {"bo1", "bo2"} else 2

    created = _create_swiss(
        client,
        league,
        headers,
        sit_out_points=None,
        group_match_format=match_format,
    )

    assert created["format"]["sit_out_points"] == expected
    assert created["format"]["sit_out_points_set_by_hand"] is False


def _set_draws(
    client: TestClient, league: League, headers: dict[str, str], *, allowed: bool
) -> None:
    response = client.patch(
        _url(league), json={"draws_allowed": allowed}, headers=headers
    )
    assert response.status_code == 200, response.text


def _format_read(
    client: TestClient, league: League, headers: dict[str, str], tid: str
) -> tuple[int | None, bool]:
    response = client.get(_tournament_url(league, tid, "/setup"), headers=headers)
    assert response.status_code == 200, response.text
    fmt = response.json()["format"]
    return fmt["sit_out_points"], fmt["sit_out_points_set_by_hand"]


def test_br071_the_league_draw_setting_moves_the_default_during_setup(
    client: TestClient, league: League, headers: dict[str, str]
) -> None:
    following = _create_swiss(client, league, headers, sit_out_points=None)[
        "tournament_id"
    ]
    by_hand = _create_swiss(client, league, headers, sit_out_points=2)["tournament_id"]
    bo3 = _create_swiss(
        client, league, headers, sit_out_points=None, group_match_format="bo3"
    )["tournament_id"]
    assert _format_read(client, league, headers, following) == (2, False)

    _set_draws(client, league, headers, allowed=True)

    assert _format_read(client, league, headers, following) == (1, False)
    assert _format_read(client, league, headers, by_hand) == (2, True)
    assert _format_read(client, league, headers, bo3) == (2, False)

    _set_draws(client, league, headers, allowed=False)

    assert _format_read(client, league, headers, following) == (2, False)


def test_br071_the_league_draw_setting_leaves_other_leagues_alone(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    make_league: Callable[..., League],
    auth_header: Callable[..., dict[str, str]],
) -> None:
    other = make_league()
    other_headers = auth_header(other.owner_user_id)
    kept = _create_swiss(client, other, other_headers, sit_out_points=None)[
        "tournament_id"
    ]

    _set_draws(client, league, headers, allowed=True)

    assert _format_read(client, other, other_headers, kept) == (2, False)


@pytest.mark.usefixtures("draws_league")
def test_br071_the_default_follows_a_format_change_until_the_organizer_picks(
    client: TestClient, league: League, headers: dict[str, str]
) -> None:
    created = _create_swiss(client, league, headers, sit_out_points=None)
    tid = created["tournament_id"]
    assert created["format"]["sit_out_points"] == 1

    bo3 = _put_format(
        client, league, tid, headers, group_match_format="bo3", sit_out_points=None
    )
    back = _put_format(
        client, league, tid, headers, group_match_format="bo1", sit_out_points=None
    )

    assert (bo3["sit_out_points"], bo3["sit_out_points_set_by_hand"]) == (2, False)
    assert (back["sit_out_points"], back["sit_out_points_set_by_hand"]) == (1, False)


def test_br071_a_value_the_organizer_picks_stays_through_a_format_change(
    client: TestClient, league: League, headers: dict[str, str], session: Session
) -> None:
    created = _create_swiss(client, league, headers, sit_out_points=None)
    tid = created["tournament_id"]

    picked = _put_format(
        client, league, tid, headers, group_match_format="bo1", sit_out_points=0
    )
    changed = _put_format(
        client, league, tid, headers, group_match_format="bo5", sit_out_points=0
    )

    assert (picked["sit_out_points"], picked["sit_out_points_set_by_hand"]) == (0, True)
    assert (changed["sit_out_points"], changed["sit_out_points_set_by_hand"]) == (
        0,
        True,
    )
    [phase] = session.scalars(
        select(TournamentPhase)
        .where(TournamentPhase.tournament_id == UUID(tid))
        .execution_options(populate_existing=True)
    ).all()
    assert phase.sit_out_points_set_by_hand is True


def test_br071_a_pick_equal_to_the_default_still_counts_as_picked(
    client: TestClient, league: League, headers: dict[str, str]
) -> None:
    created = _create_swiss(client, league, headers, sit_out_points=None)

    picked = _put_format(
        client,
        league,
        created["tournament_id"],
        headers,
        group_match_format="bo3",
        sit_out_points=2,
    )

    assert (picked["sit_out_points"], picked["sit_out_points_set_by_hand"]) == (2, True)


@pytest.mark.usefixtures("draws_league")
def test_br071_sending_the_read_value_back_pins_it_and_null_keeps_following(
    client: TestClient, league: League, headers: dict[str, str]
) -> None:
    created = _create_swiss(client, league, headers, sit_out_points=None)
    tid = created["tournament_id"]
    read = created["format"]
    assert (read["sit_out_points"], read["sit_out_points_set_by_hand"]) == (1, False)

    following = _put_format(
        client, league, tid, headers, group_match_format="bo3", sit_out_points=None
    )
    pinned = _put_format(
        client,
        league,
        tid,
        headers,
        group_match_format="bo5",
        sit_out_points=following["sit_out_points"],
    )
    stays = _put_format(
        client, league, tid, headers, group_match_format="bo1", sit_out_points=None
    )

    assert (following["sit_out_points"], following["sit_out_points_set_by_hand"]) == (
        2,
        False,
    )
    assert (pinned["sit_out_points"], pinned["sit_out_points_set_by_hand"]) == (2, True)
    assert (stays["sit_out_points"], stays["sit_out_points_set_by_hand"]) == (1, False)


def test_br071_null_takes_the_default_back_after_a_pick(
    client: TestClient, league: League, headers: dict[str, str]
) -> None:
    created = _create_swiss(client, league, headers, sit_out_points=0)
    tid = created["tournament_id"]
    assert created["format"]["sit_out_points_set_by_hand"] is True

    reset = _put_format(
        client, league, tid, headers, group_match_format="bo3", sit_out_points=None
    )

    assert (reset["sit_out_points"], reset["sit_out_points_set_by_hand"]) == (2, False)


@pytest.mark.usefixtures("draws_league")
def test_br071_changing_to_no_group_phase_forgets_the_pick(
    client: TestClient, league: League, headers: dict[str, str]
) -> None:
    created = _create_swiss(client, league, headers, sit_out_points=0)
    tid = created["tournament_id"]
    knockout = {
        **SINGLES_ROUND_ROBIN,
        "group_phase": "none",
        "round_robin_legs": None,
        "sit_out_points": None,
        "group_match_format": None,
        "knockout_match_format": "bo1",
        "third_place_match": False,
    }
    _ok(_write(client, league, tid, "/format", knockout, headers))

    back = _put_format(client, league, tid, headers, sit_out_points=None)

    assert (back["sit_out_points"], back["sit_out_points_set_by_hand"]) == (1, False)


def _round_robin_format(**changes: object) -> Json:
    return {**SINGLES_ROUND_ROBIN, **changes}


@pytest.mark.parametrize("points", [0, 1, 2])
def test_br071_a_round_robin_refuses_sit_out_points(
    client: TestClient, league: League, headers: dict[str, str], points: int
) -> None:
    """In a round robin every entry sits out equally often; a late entry (BR-054)
    would make the points distort the order, so the value does not exist there."""
    created = _create(client, league, headers)

    status, body = _write(
        client,
        league,
        created["tournament_id"],
        "/format",
        _round_robin_format(sit_out_points=points),
        headers,
    )
    post = client.post(
        _url(league, "/tournaments"),
        json={"id": str(uuid7()), **_round_robin_format(sit_out_points=points)},
        headers=headers,
    )

    assert status == post.status_code == 422
    assert body["code"] == post.json()["code"] == "validation_failed"
    assert [e["type"] for e in body["detail"]["errors"]] == [
        "sit_out_points_not_applicable"
    ]
    assert [e["type"] for e in post.json()["detail"]["errors"]] == [
        "sit_out_points_not_applicable"
    ]


def test_br071_a_round_robin_has_no_sit_out_points_and_no_pick(
    client: TestClient, league: League, headers: dict[str, str], session: Session
) -> None:
    created = _create(client, league, headers, sit_out_points=None)

    fmt = created["format"]
    assert (fmt["sit_out_points"], fmt["sit_out_points_set_by_hand"]) == (None, False)
    [phase] = session.scalars(
        select(TournamentPhase)
        .where(TournamentPhase.tournament_id == UUID(created["tournament_id"]))
        .execution_options(populate_existing=True)
    ).all()
    assert phase.sit_out_points is None


@pytest.mark.usefixtures("draws_league")
def test_br071_swiss_to_round_robin_clears_the_value_and_back_sets_the_default(
    client: TestClient, league: League, headers: dict[str, str]
) -> None:
    created = _create_swiss(client, league, headers, sit_out_points=0)
    tid = created["tournament_id"]
    assert created["format"]["sit_out_points_set_by_hand"] is True

    round_robin = _ok(
        _write(client, league, tid, "/format", _round_robin_format(), headers)
    )["format"]
    swiss = _put_format(client, league, tid, headers, sit_out_points=None)

    assert (
        round_robin["sit_out_points"],
        round_robin["sit_out_points_set_by_hand"],
    ) == (None, False)
    assert (swiss["sit_out_points"], swiss["sit_out_points_set_by_hand"]) == (1, False)


def test_br071_a_monster_dyp_group_phase_takes_the_default(
    client: TestClient, league: League, headers: dict[str, str]
) -> None:
    created = _create(
        client,
        league,
        headers,
        type="monster_dyp",
        group_phase="monster_dyp",
        round_robin_legs=None,
        sit_out_points=None,
    )

    fmt = created["format"]
    assert (fmt["sit_out_points"], fmt["sit_out_points_set_by_hand"]) == (2, False)


def test_br071_the_league_draw_setting_leaves_a_round_robin_without_a_value(
    client: TestClient, league: League, headers: dict[str, str]
) -> None:
    round_robin = _create(client, league, headers)["tournament_id"]

    _set_draws(client, league, headers, allowed=True)

    assert _format_read(client, league, headers, round_robin) == (None, False)


@pytest.mark.parametrize("points", [0, 1, 2])
def test_fr039_a_sit_out_is_worth_0_1_or_2_points(
    client: TestClient, league: League, headers: dict[str, str], points: int
) -> None:
    created = _create_swiss(client, league, headers)

    fmt = _put_format(
        client, league, created["tournament_id"], headers, sit_out_points=points
    )

    assert fmt["sit_out_points"] == points


def test_fr039_a_sit_out_worth_3_points_is_refused(
    client: TestClient, league: League, headers: dict[str, str]
) -> None:
    created = _create_swiss(client, league, headers)

    status, body = _write(
        client,
        league,
        created["tournament_id"],
        "/format",
        _swiss_format(sit_out_points=3),
        headers,
    )
    post = client.post(
        _url(league, "/tournaments"),
        json={"id": str(uuid7()), **_swiss_format(sit_out_points=3)},
        headers=headers,
    )

    assert status == post.status_code == 422
    assert body["code"] == post.json()["code"] == "validation_failed"
    assert [e["type"] for e in body["detail"]["errors"]] == ["literal_error"]


def test_fr043_a_swiss_phase_keeps_its_tiebreakers_while_it_stays_swiss(
    client: TestClient, league: League, headers: dict[str, str], session: Session
) -> None:
    created = _create(
        client, league, headers, group_phase="swiss", round_robin_legs=None
    )
    tournament = session.get_one(Tournament, UUID(created["tournament_id"]))
    swiss = {**SINGLES_ROUND_ROBIN, "group_phase": "swiss", "round_robin_legs": None}

    _ok(
        _write(
            client,
            league,
            created["tournament_id"],
            "/format",
            {**swiss, "sit_out_points": 1},
            headers,
        )
    )
    [phase] = session.scalars(
        select(TournamentPhase)
        .where(TournamentPhase.tournament_id == tournament.id)
        .execution_options(populate_existing=True)
    ).all()

    assert phase.tiebreakers == ["bh1", "bh2", "score_difference"]
    assert phase.sit_out_points == 1


def test_fr043_the_tiebreakers_start_again_when_swiss_becomes_monster_dyp(
    client: TestClient, league: League, headers: dict[str, str], session: Session
) -> None:
    created = _create(
        client, league, headers, group_phase="swiss", round_robin_legs=None
    )
    tid = created["tournament_id"]
    phase = session.scalars(
        select(TournamentPhase).where(TournamentPhase.tournament_id == UUID(tid))
    ).one()
    phase.tiebreakers = ["bh2"]  # what a later screen will let the organizer choose
    session.flush()
    monster = {
        **SINGLES_ROUND_ROBIN,
        "type": "monster_dyp",
        "group_phase": "monster_dyp",
        "round_robin_legs": None,
    }

    _ok(_write(client, league, tid, "/format", monster, headers))
    session.refresh(phase)

    assert phase.format.value == "monster_dyp"
    assert phase.tiebreakers == ["bh1", "bh2", "score_difference"]


def test_adr008_a_repeated_format_changes_nothing(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    session: Session,
    travel: Callable[[timedelta], datetime],
) -> None:
    created = _create(client, league, headers)
    travel(timedelta(minutes=5))

    body = _ok(
        _write(
            client,
            league,
            created["tournament_id"],
            "/format",
            SINGLES_ROUND_ROBIN,
            headers,
        )
    )

    assert body == created
    tournament = session.get_one(Tournament, UUID(created["tournament_id"]))
    session.refresh(tournament)
    assert tournament.updated_at is None


def test_fr033_a_new_type_keeps_the_players_and_makes_the_entries_again(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    created = _create(client, league, headers)
    tid = created["tournament_id"]
    _ok(
        _write(
            client, league, tid, "/setup/players", {"player_ids": players[:4]}, headers
        )
    )

    body = _ok(
        _write(
            client,
            league,
            tid,
            "/format",
            {**SINGLES_ROUND_ROBIN, "type": "dyp"},
            headers,
        )
    )

    assert set(body["player_ids"]) == set(players[:4])
    assert [e["kind"] for e in body["entries"]] == ["pair", "pair"]
    assert body["draw_counter"] == 2


def test_fr031_put_format_needs_every_setting_that_applies(
    client: TestClient, league: League, headers: dict[str, str]
) -> None:
    created = _create(client, league, headers)

    status, body = _write(
        client,
        league,
        created["tournament_id"],
        "/format",
        {**SINGLES_ROUND_ROBIN, "round_robin_legs": None},
        headers,
    )

    assert status == 422
    assert [e["type"] for e in body["detail"]["errors"]] == ["setting_missing"]


def test_fr036_a_started_tournament_refuses_setup_writes(
    client: TestClient, league: League, headers: dict[str, str], session: Session
) -> None:
    created = _create(client, league, headers)
    session.get_one(
        Tournament, UUID(created["tournament_id"])
    ).state = TournamentState.IN_PROGRESS
    session.flush()

    status, body = _write(
        client,
        league,
        created["tournament_id"],
        "/format",
        SINGLES_ROUND_ROBIN,
        headers,
    )

    assert status == 409
    assert body == {
        "code": "tournament_not_in_setup",
        "detail": {"state": "in_progress"},
    }


# ---------------------------------------------------------------- players


def test_br021_picked_singles_are_seeded_by_the_league_ranking(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    created = _create(client, league, headers)

    body = _ok(
        _write(
            client,
            league,
            created["tournament_id"],
            "/setup/players",
            {"player_ids": players[:5]},
            headers,
        )
    )

    rank = {row["player_id"]: row["rank"] for row in body["ranking"]}
    assert body["player_ids"] == sorted(players[:5], key=rank.__getitem__)
    assert [e["seed"] for e in body["entries"]] == [1, 2, 3, 4, 5]
    assert [e["player_ids"][0] for e in body["entries"]] == body["player_ids"]
    assert body["draw_counter"] == 1


def test_adr008_a_repeated_pick_changes_nothing(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    created = _create(client, league, headers)
    tid = created["tournament_id"]
    first = _ok(
        _write(
            client, league, tid, "/setup/players", {"player_ids": players[:3]}, headers
        )
    )

    again = _ok(
        _write(
            client,
            league,
            tid,
            "/setup/players",
            {"player_ids": players[2::-1]},
            headers,
        )
    )

    assert again == first


def test_br002_a_removed_player_cannot_be_picked(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    players: list[str],
    session: Session,
) -> None:
    created = _create(client, league, headers)
    session.get_one(Player, UUID(players[1])).removed_at = datetime.now(UTC)
    session.flush()

    status, body = _write(
        client,
        league,
        created["tournament_id"],
        "/setup/players",
        {"player_ids": players[:3]},
        headers,
    )

    assert status == 409
    assert body == {"code": "player_removed", "detail": {"player_id": players[1]}}


def test_owasp_api1_a_player_of_another_league_cannot_be_picked(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    make_league: Callable[..., League],
    make_player: Callable[..., Player],
) -> None:
    created = _create(client, league, headers)
    stranger = make_player(league=make_league(owner_user_id=league.owner_user_id))

    status, body = _write(
        client,
        league,
        created["tournament_id"],
        "/setup/players",
        {"player_ids": [str(stranger.id)]},
        headers,
    )

    assert status == 404
    assert body == {"code": "player_not_found", "detail": {}}


def test_br003_a_player_given_twice_is_refused(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    created = _create(client, league, headers)

    status, body = _write(
        client,
        league,
        created["tournament_id"],
        "/setup/players",
        {"player_ids": [players[0], players[0]]},
        headers,
    )

    assert status == 422
    assert [e["type"] for e in body["detail"]["errors"]] == ["given_twice"]


def test_fr041_monster_dyp_enters_players_without_seeds(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    created = _create(
        client,
        league,
        headers,
        type="monster_dyp",
        group_phase="monster_dyp",
        round_robin_legs=None,
    )

    body = _ok(
        _write(
            client,
            league,
            created["tournament_id"],
            "/setup/players",
            {"player_ids": players[:5]},
            headers,
        )
    )

    assert [(e["kind"], e["seed"]) for e in body["entries"]] == [("player", None)] * 5
    assert body["top_player_ids"] == []


# ---------------------------------------------------------------- doubles


def _doubles(
    client: TestClient, league: League, headers: dict[str, str], picked: list[str]
) -> str:
    created = _create(client, league, headers, type="doubles")
    tid: str = created["tournament_id"]
    _ok(_write(client, league, tid, "/setup/players", {"player_ids": picked}, headers))
    return tid


def test_fr033_doubles_pairs_are_set_by_hand_and_seeded(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    tid = _doubles(client, league, headers, players[:5])

    body = _ok(
        _write(
            client,
            league,
            tid,
            "/setup/pairs",
            {"pairs": [[players[0], players[3]], [players[1], players[2]]]},
            headers,
        )
    )

    assert sorted(sorted(e["player_ids"]) for e in body["entries"]) == sorted(
        [sorted([players[0], players[3]]), sorted([players[1], players[2]])]
    )
    assert sorted(e["seed"] for e in body["entries"]) == [1, 2]
    assert body["draw_counter"] == 2


def test_adr010_unpicking_a_player_breaks_their_pair_and_keeps_the_others(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    tid = _doubles(client, league, headers, players[:4])
    paired = _ok(
        _write(
            client,
            league,
            tid,
            "/setup/pairs",
            {"pairs": [[players[0], players[1]], [players[2], players[3]]]},
            headers,
        )
    )
    kept = next(e for e in paired["entries"] if players[2] in e["player_ids"])

    body = _ok(
        _write(
            client, league, tid, "/setup/players", {"player_ids": players[1:4]}, headers
        )
    )

    assert [e["id"] for e in body["entries"]] == [kept["id"]]
    assert body["entries"][0]["seed"] == 1


@pytest.mark.parametrize(
    ("pairs", "status", "code"),
    [
        pytest.param([[0, 5]], 409, "player_not_picked", id="ADR-008-not-picked"),
        pytest.param([[0, 1], [1, 2]], 422, "validation_failed", id="BR-003-twice"),
        pytest.param([[0, 0]], 422, "validation_failed", id="BR-030-same-player"),
    ],
)
def test_br003_pairs_need_picked_players_each_once(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    players: list[str],
    pairs: list[list[int]],
    status: int,
    code: str,
) -> None:
    tid = _doubles(client, league, headers, players[:4])

    got, body = _write(
        client,
        league,
        tid,
        "/setup/pairs",
        {"pairs": [[players[a], players[b]] for a, b in pairs]},
        headers,
    )

    assert (got, body["code"]) == (status, code)


def test_fr033_pairs_of_a_tournament_of_another_type_are_stale(
    client: TestClient, league: League, headers: dict[str, str]
) -> None:
    created = _create(client, league, headers)

    status, body = _write(
        client, league, created["tournament_id"], "/setup/pairs", {"pairs": []}, headers
    )

    assert status == 409
    assert body == {"code": "tournament_type_changed", "detail": {"type": "singles"}}


def test_fr033_the_rest_of_doubles_is_paired_by_lot(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    tid = _doubles(client, league, headers, players[:7])
    paired = _ok(
        _write(
            client,
            league,
            tid,
            "/setup/pairs",
            {"pairs": [[players[0], players[1]]]},
            headers,
        )
    )
    [by_hand] = [
        e for e in paired["entries"] if set(e["player_ids"]) == set(players[:2])
    ]

    body = _ok(
        _write(
            client,
            league,
            tid,
            "/setup/draw",
            {"expected_draw_counter": paired["draw_counter"], "target": "pairs"},
            headers,
            method="POST",
        )
    )
    [by_hand] = [
        e for e in paired["entries"] if set(e["player_ids"]) == set(players[:2])
    ]

    assert len(body["entries"]) == 3
    in_pairs = [p for e in body["entries"] for p in e["player_ids"]]
    assert len(set(in_pairs)) == 6
    assert body["draw_counter"] == paired["draw_counter"] + 1
    kept = [e for e in body["entries"] if set(e["player_ids"]) == set(players[:2])]
    assert [e["id"] for e in kept] == [by_hand["id"]]


@pytest.mark.parametrize(
    ("picked", "unpaired"),
    [
        pytest.param(4, 0, id="FR-033-everyone-is-paired"),
        pytest.param(5, 1, id="FR-033-one-player-is-left"),
    ],
)
def test_fr033_pairing_the_rest_with_fewer_than_two_left_changes_nothing(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    players: list[str],
    picked: int,
    unpaired: int,
) -> None:
    tid = _doubles(client, league, headers, players[:picked])
    paired = _ok(
        _write(
            client,
            league,
            tid,
            "/setup/pairs",
            {"pairs": [[players[0], players[1]], [players[2], players[3]]]},
            headers,
        )
    )

    status, body = _write(
        client,
        league,
        tid,
        "/setup/draw",
        {"expected_draw_counter": paired["draw_counter"], "target": "pairs"},
        headers,
        method="POST",
    )
    read = client.get(_tournament_url(league, tid, "/setup"), headers=headers)

    assert status == 422
    assert body == {"code": "nothing_to_pair", "detail": {"unpaired": unpaired}}
    assert read.json()["draw_counter"] == paired["draw_counter"]
    assert read.json()["entries"] == paired["entries"]


# ---------------------------------------------------------------- DYP


def _dyp(
    client: TestClient, league: League, headers: dict[str, str], picked: list[str]
) -> Json:
    created = _create(client, league, headers, type="dyp")
    return _ok(
        _write(
            client,
            league,
            created["tournament_id"],
            "/setup/players",
            {"player_ids": picked},
            headers,
        )
    )


def test_br032_ranking_halves_leave_one_out_and_draw_partners(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    body = _dyp(client, league, headers, players[:9])

    halves = {row["player_id"]: row["half"] for row in body["halves"]}
    assert sorted(halves.values()).count("left_out") == 1
    rank = {row["player_id"]: row["rank"] for row in body["ranking"]}
    top = [p for p, h in halves.items() if h == "top"]
    bottom = [p for p, h in halves.items() if h == "bottom"]
    assert len(top) == len(bottom) == 4
    assert max(rank[p] for p in top) < min(rank[p] for p in bottom)
    assert len(body["entries"]) == 4
    for entry in body["entries"]:
        assert halves[entry["player_ids"][0]] == "top"
        assert halves[entry["player_ids"][1]] == "bottom"


def test_br031_fewer_than_four_dyp_players_have_no_halves_yet(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    body = _dyp(client, league, headers, players[:3])

    assert body["halves"] == body["entries"] == []


def test_br032_hand_halves_draw_pairs_once_they_are_complete(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    tid = _dyp(client, league, headers, players[:4])["tournament_id"]
    halves = [
        {"player_id": players[0], "half": "bottom"},
        {"player_id": players[1], "half": "top"},
        {"player_id": players[2], "half": "bottom"},
    ]

    partial = _ok(
        _write(
            client,
            league,
            tid,
            "/setup/halves",
            {"method": "by_hand", "halves": halves},
            headers,
        )
    )
    complete = _ok(
        _write(
            client,
            league,
            tid,
            "/setup/halves",
            {
                "method": "by_hand",
                "halves": [*halves, {"player_id": players[3], "half": "top"}],
            },
            headers,
        )
    )

    assert partial["halves_method"] == "by_hand"
    assert partial["entries"] == []
    tops = {e["player_ids"][0] for e in complete["entries"]}
    assert tops == {players[1], players[3]}


@pytest.mark.parametrize(
    ("halves", "code", "detail"),
    [
        pytest.param(
            ["top", "bottom", "top"],
            "dyp_halves_incomplete",
            {"missing": 1},
            id="BR-032-incomplete",
        ),
        pytest.param(
            ["top", "top", "top", "bottom"],
            "dyp_halves_unequal",
            {"top": 3, "bottom": 1},
            id="BR-032-unequal",
        ),
        pytest.param(
            ["top", "bottom", "left_out", "left_out"],
            "too_many_left_out",
            {"maximum": 1, "given": 2},
            id="BR-032-two-left-out",
        ),
    ],
)
def test_br032_a_new_draw_needs_complete_valid_hand_halves(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    players: list[str],
    halves: list[str],
    code: str,
    detail: Json,
) -> None:
    tid = _dyp(client, league, headers, players[:4])["tournament_id"]
    rows = [{"player_id": players[n], "half": h} for n, h in enumerate(halves)]
    setup = _ok(
        _write(
            client,
            league,
            tid,
            "/setup/halves",
            {"method": "by_hand", "halves": rows},
            headers,
        )
    )

    status, body = _write(
        client,
        league,
        tid,
        "/setup/draw",
        {"expected_draw_counter": setup["draw_counter"], "target": "pairs"},
        headers,
        method="POST",
    )

    assert status == 422
    assert body == {"code": code, "detail": detail}


def test_br031_a_new_ranking_draw_needs_four_players(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    setup = _dyp(client, league, headers, players[:3])

    status, body = _write(
        client,
        league,
        setup["tournament_id"],
        "/setup/draw",
        {"expected_draw_counter": setup["draw_counter"], "target": "pairs"},
        headers,
        method="POST",
    )

    assert status == 422
    assert body == {"code": "not_enough_players", "detail": {"minimum": 4, "given": 3}}


def test_br033_a_new_dyp_draw_draws_again_with_the_next_counter(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    setup = _dyp(client, league, headers, players[:8])
    draws = [setup]

    for _ in range(4):
        draws.append(
            _ok(
                _write(
                    client,
                    league,
                    setup["tournament_id"],
                    "/setup/draw",
                    {
                        "expected_draw_counter": draws[-1]["draw_counter"],
                        "target": "pairs",
                    },
                    headers,
                    method="POST",
                )
            )
        )

    assert [d["draw_counter"] for d in draws] == [1, 2, 3, 4, 5]
    pairings = {
        frozenset(frozenset(e["player_ids"]) for e in d["entries"]) for d in draws
    }
    assert len(pairings) > 1


def test_br032_halves_of_another_type_are_stale(
    client: TestClient, league: League, headers: dict[str, str]
) -> None:
    created = _create(client, league, headers)

    status, body = _write(
        client,
        league,
        created["tournament_id"],
        "/setup/halves",
        {"method": "ranking", "halves": []},
        headers,
    )

    assert status == 409
    assert body["code"] == "tournament_type_changed"


def test_br032_a_hand_half_for_a_player_not_picked_is_stale(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    tid = _dyp(client, league, headers, players[:4])["tournament_id"]

    status, body = _write(
        client,
        league,
        tid,
        "/setup/halves",
        {"method": "by_hand", "halves": [{"player_id": players[8], "half": "top"}]},
        headers,
    )

    assert status == 409
    assert body == {"code": "player_not_picked", "detail": {"player_id": players[8]}}


def test_adr008_repeated_halves_change_nothing(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    setup = _dyp(client, league, headers, players[:4])
    tid = setup["tournament_id"]
    rows = {"method": "by_hand", "halves": [{"player_id": players[0], "half": "top"}]}

    by_ranking = _ok(
        _write(
            client,
            league,
            tid,
            "/setup/halves",
            {"method": "ranking", "halves": []},
            headers,
        )
    )
    first = _ok(_write(client, league, tid, "/setup/halves", rows, headers))
    again = _ok(_write(client, league, tid, "/setup/halves", rows, headers))

    assert by_ranking == setup
    assert again == first


# ---------------------------------------------------------------- seeds


def test_br022_random_seeding_shuffles_and_shuffle_again_draws_anew(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    created = _create(client, league, headers)
    tid = created["tournament_id"]
    _ok(_write(client, league, tid, "/setup/players", {"player_ids": players}, headers))

    random = _ok(
        _write(client, league, tid, "/setup/seeding", {"method": "random"}, headers)
    )
    orders = [random]
    for _ in range(3):
        orders.append(
            _ok(
                _write(
                    client,
                    league,
                    tid,
                    "/setup/draw",
                    {
                        "expected_draw_counter": orders[-1]["draw_counter"],
                        "target": "seeds",
                    },
                    headers,
                    method="POST",
                )
            )
        )

    assert random["seeding_method"] == "random"
    assert [o["draw_counter"] for o in orders] == [2, 3, 4, 5]
    assert len({tuple(e["id"] for e in o["entries"]) for o in orders}) > 1


def test_adr008_a_stale_draw_counter_is_a_conflict(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    created = _create(client, league, headers)
    tid = created["tournament_id"]
    _ok(
        _write(
            client, league, tid, "/setup/players", {"player_ids": players[:4]}, headers
        )
    )
    _ok(_write(client, league, tid, "/setup/seeding", {"method": "random"}, headers))

    status, body = _write(
        client,
        league,
        tid,
        "/setup/draw",
        {"expected_draw_counter": 1, "target": "seeds"},
        headers,
        method="POST",
    )

    assert status == 409
    assert body == {"code": "draw_counter_changed", "detail": {"draw_counter": 2}}


def test_br021_shuffling_seeds_by_ranking_is_stale(
    client: TestClient, league: League, headers: dict[str, str]
) -> None:
    created = _create(client, league, headers)

    status, body = _write(
        client,
        league,
        created["tournament_id"],
        "/setup/draw",
        {"expected_draw_counter": 0, "target": "seeds"},
        headers,
        method="POST",
    )

    assert status == 409
    assert body == {
        "code": "seeding_method_changed",
        "detail": {"seeding_method": "ranking"},
    }


def test_fr034_monster_dyp_has_no_seeding(
    client: TestClient, league: League, headers: dict[str, str]
) -> None:
    created = _create(
        client,
        league,
        headers,
        type="monster_dyp",
        group_phase="monster_dyp",
        round_robin_legs=None,
    )
    tid = created["tournament_id"]

    seeding = _write(
        client, league, tid, "/setup/seeding", {"method": "random"}, headers
    )
    order = _write(client, league, tid, "/setup/seed-order", {"entry_ids": []}, headers)

    assert seeding[0] == order[0] == 409
    assert seeding[1]["code"] == order[1]["code"] == "tournament_type_changed"


def test_fr034_seeds_are_reordered_by_hand_until_the_entries_change(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    created = _create(client, league, headers)
    tid = created["tournament_id"]
    picked = _ok(
        _write(
            client, league, tid, "/setup/players", {"player_ids": players[:3]}, headers
        )
    )
    reversed_ids = [e["id"] for e in reversed(picked["entries"])]

    reordered = _ok(
        _write(
            client,
            league,
            tid,
            "/setup/seed-order",
            {"entry_ids": reversed_ids},
            headers,
        )
    )
    again = _ok(
        _write(
            client,
            league,
            tid,
            "/setup/seed-order",
            {"entry_ids": reversed_ids},
            headers,
        )
    )
    changed = _ok(
        _write(
            client, league, tid, "/setup/players", {"player_ids": players[:4]}, headers
        )
    )

    assert [e["id"] for e in reordered["entries"]] == reversed_ids
    assert reordered["draw_counter"] == picked["draw_counter"]
    assert again == reordered
    # The hand order is gone; the entries that stay keep their ids (ADR-010).
    assert [e["player_ids"][0] for e in changed["entries"]] == changed["player_ids"]
    assert {e["id"] for e in picked["entries"]} < {e["id"] for e in changed["entries"]}


@pytest.mark.parametrize(
    "order",
    [
        pytest.param("missing", id="ADR-008-missing-entry"),
        pytest.param("stranger", id="ADR-008-unknown-entry"),
    ],
)
def test_adr008_a_seed_order_that_is_not_the_entries_is_stale(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    players: list[str],
    order: str,
) -> None:
    created = _create(client, league, headers)
    tid = created["tournament_id"]
    picked = _ok(
        _write(
            client, league, tid, "/setup/players", {"player_ids": players[:3]}, headers
        )
    )
    ids = [e["id"] for e in picked["entries"]]
    ids = ids[:2] if order == "missing" else [*ids[:2], str(uuid7())]

    status, body = _write(
        client, league, tid, "/setup/seed-order", {"entry_ids": ids}, headers
    )

    assert status == 409
    assert body == {"code": "seed_order_changed", "detail": {}}


# ---------------------------------------------------------------- delete


def test_fr038_delete_removes_the_tournament_and_a_repeat_is_not_found(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    players: list[str],
    session: Session,
) -> None:
    created = _create(client, league, headers)
    tid = created["tournament_id"]
    _ok(
        _write(
            client, league, tid, "/setup/players", {"player_ids": players[:3]}, headers
        )
    )

    first = client.delete(_tournament_url(league, tid), headers=headers)
    again = client.delete(_tournament_url(league, tid), headers=headers)

    assert first.status_code == 204
    assert again.status_code == 404
    assert again.json() == {"code": "tournament_not_found", "detail": {}}
    assert session.scalar(select(Tournament).where(Tournament.id == UUID(tid))) is None
    assert (
        len(session.scalars(select(Player).where(Player.league_id == league.id)).all())
        == 9
    )


def test_fr038_a_dyp_tournament_goes_with_its_picks_halves_and_pairs(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    players: list[str],
    session: Session,
) -> None:
    setup = _dyp(client, league, headers, players[:5])

    response = client.delete(
        _tournament_url(league, setup["tournament_id"]), headers=headers
    )

    assert response.status_code == 204
    for table in ("tournament_players", "dyp_halves", "entries", "entry_members"):
        assert session.scalar(text(f"SELECT count(*) FROM {table}")) == 0  # noqa: S608


def test_br011_a_tournament_of_a_closed_season_cannot_be_deleted(
    client: TestClient,
    league: League,
    season_id: UUID,
    headers: dict[str, str],
    session: Session,
    now: datetime,
) -> None:
    created = _create(client, league, headers)
    season = session.get_one(Season, season_id)
    session.get_one(
        Tournament, UUID(created["tournament_id"])
    ).state = TournamentState.FINISHED
    season.state = SeasonState.CLOSED
    season.closed_at = now
    session.flush()
    session.add(
        Season(
            league_id=league.id,
            number=2,
            state=SeasonState.ACTIVE,
            placement_points=[1],
            started_at=now,
            created_at=now,
        )
    )
    session.flush()

    response = client.delete(
        _tournament_url(league, created["tournament_id"]), headers=headers
    )

    assert response.status_code == 409
    assert response.json() == {"code": "season_closed", "detail": {}}


# ---------------------------------------------------------------- BR-010, BR-002


def test_br010_a_new_season_waits_for_unfinished_tournaments(
    client: TestClient, league: League, headers: dict[str, str], session: Session
) -> None:
    created = _create(client, league, headers)

    refused = client.post(
        _url(league, "/seasons"), json={"expected_current_number": 1}, headers=headers
    )
    session.get_one(
        Tournament, UUID(created["tournament_id"])
    ).state = TournamentState.FINISHED
    session.flush()
    started = client.post(
        _url(league, "/seasons"), json={"expected_current_number": 1}, headers=headers
    )

    assert refused.status_code == 422
    assert refused.json() == {
        "code": "season_has_unfinished_tournaments",
        "detail": {"tournament_ids": [created["tournament_id"]]},
    }
    assert started.status_code == 201


def test_br010_a_stale_season_start_is_a_conflict_before_the_rule(
    client: TestClient, league: League, headers: dict[str, str]
) -> None:
    _create(client, league, headers)

    response = client.post(
        _url(league, "/seasons"), json={"expected_current_number": 7}, headers=headers
    )

    assert response.status_code == 409


def test_br002_a_picked_player_cannot_be_removed_until_the_tournament_goes(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    created = _create(client, league, headers)
    tid = created["tournament_id"]
    _ok(
        _write(
            client, league, tid, "/setup/players", {"player_ids": players[:2]}, headers
        )
    )
    remove_url = _url(league, f"/players/{players[0]}/removed")

    refused = client.put(remove_url, json={"removed": True}, headers=headers)
    other = client.put(
        _url(league, f"/players/{players[5]}/removed"),
        json={"removed": True},
        headers=headers,
    )
    client.delete(_tournament_url(league, tid), headers=headers)
    removed = client.put(remove_url, json={"removed": True}, headers=headers)

    assert refused.status_code == 422
    assert refused.json() == {
        "code": "player_in_unfinished_tournament",
        "detail": {"tournament_ids": [tid]},
    }
    assert other.status_code == removed.status_code == 200


# ---------------------------------------------------------------- races


def _commit_league_with_players(
    engine: Engine, now: datetime, email: str, count: int
) -> tuple[UUID, UUID, list[UUID]]:
    with Session(engine) as setup:
        owner = User(
            email=email,
            display_name="Racer",
            password_hash="!",
            language=Language.EN,
            created_at=now,
        )
        setup.add(owner)
        setup.flush()
        league = league_service.create_league(
            setup, league_id=uuid7(), owner_user_id=owner.id, name="Race", now=now
        )
        ids = [
            player_service.add_player(
                setup,
                league_id=league.id,
                user_id=owner.id,
                name=f"P{n}",
                clock=lambda: now,
            ).id
            for n in range(count)
        ]
        setup.commit()
        return owner.id, league.id, ids


@pytest.mark.concurrency
def test_adr008_one_client_id_sent_to_two_leagues_at_once_is_a_conflict(
    committing_settings: Settings,
    committing_engine: Engine,
    now: datetime,
    committed_auth_header: Callable[..., dict[str, str]],
    wait_for_a_lock_wait: Callable[[], None],
) -> None:
    owner_id, first_league_id, _ = _commit_league_with_players(
        committing_engine, now, "twice@example.test", 0
    )
    with Session(committing_engine) as setup:
        second_league_id = league_service.create_league(
            setup, league_id=uuid7(), owner_user_id=owner_id, name="Other", now=now
        ).id
        setup.commit()
    tournament_id = uuid7()
    request = tournament_service.FormatRequest(
        name="Race",
        date=now.date(),
        type=TournamentType.SINGLES,
        group_phase=GroupPhase.NONE,
    )
    outcome: list[tuple[int, object]] = []

    with (
        Session(committing_engine) as first,
        TestClient(create_app(committing_settings)) as client,
    ):
        # The league lock of the first league does not stop the second league's
        # request, and its lookup of the id sees nothing yet.
        tournament_service.create_tournament(
            first,
            league_id=first_league_id,
            user_id=owner_id,
            tournament_id=tournament_id,
            request=request,
            clock=lambda: now,
        )

        def create_second() -> None:
            response = client.post(
                _url(second_league_id, "/tournaments"),
                json={"id": str(tournament_id), **SINGLES_ROUND_ROBIN},
                headers=committed_auth_header(owner_id, issued_at=datetime.now(UTC)),
            )
            outcome.append((response.status_code, response.json()))

        second = threading.Thread(target=create_second)
        second.start()
        wait_for_a_lock_wait()  # its INSERT waits on the first one's row
        first.commit()
        second.join()

    assert outcome == [(409, {"code": "tournament_id_taken", "detail": {}})]
    with Session(committing_engine) as check:
        assert check.scalars(select(Tournament.id)).all() == [tournament_id]


def _commit_tournament(
    engine: Engine, now: datetime, owner_id: UUID, league_id: UUID
) -> UUID:
    tournament_id = uuid7()
    with Session(engine) as setup:
        tournament_service.create_tournament(
            setup,
            league_id=league_id,
            user_id=owner_id,
            tournament_id=tournament_id,
            request=tournament_service.FormatRequest(
                name="Race",
                date=now.date(),
                type=TournamentType.SINGLES,
                group_phase=GroupPhase.NONE,
            ),
            clock=lambda: now,
        )
        setup.commit()
    return tournament_id


@pytest.mark.concurrency
def test_br010_a_season_start_racing_a_create_is_refused_after_the_create(
    committing_settings: Settings,
    committing_engine: Engine,
    now: datetime,
    committed_auth_header: Callable[..., dict[str, str]],
    wait_for_a_lock_wait: Callable[[], None],
) -> None:
    owner_id, league_id, _ = _commit_league_with_players(
        committing_engine, now, "create-first@example.test", 0
    )
    tournament_id = uuid7()
    outcome: list[tuple[int, object]] = []

    with (
        Session(committing_engine) as first,
        TestClient(create_app(committing_settings)) as client,
    ):
        tournament_service.create_tournament(
            first,
            league_id=league_id,
            user_id=owner_id,
            tournament_id=tournament_id,
            request=tournament_service.FormatRequest(
                name="Race",
                date=now.date(),
                type=TournamentType.SINGLES,
                group_phase=GroupPhase.NONE,
            ),
            clock=lambda: now,
        )

        def start_second() -> None:
            response = client.post(
                _url(league_id, "/seasons"),
                json={"expected_current_number": 1},
                headers=committed_auth_header(owner_id, issued_at=datetime.now(UTC)),
            )
            outcome.append((response.status_code, response.json()))

        second = threading.Thread(target=start_second)
        second.start()
        wait_for_a_lock_wait()  # it waits for the league lock the create holds
        first.commit()
        second.join()

    assert outcome == [
        (
            422,
            {
                "code": "season_has_unfinished_tournaments",
                "detail": {"tournament_ids": [str(tournament_id)]},
            },
        )
    ]
    with Session(committing_engine) as check:
        assert check.scalars(select(Season.number)).all() == [1]


@pytest.mark.concurrency
def test_br010_a_create_racing_a_season_start_lands_in_the_new_season(
    committing_settings: Settings,
    committing_engine: Engine,
    now: datetime,
    committed_auth_header: Callable[..., dict[str, str]],
    wait_for_a_lock_wait: Callable[[], None],
) -> None:
    owner_id, league_id, _ = _commit_league_with_players(
        committing_engine, now, "season-first@example.test", 0
    )
    tournament_id = uuid7()
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

        def create_second() -> None:
            response = client.post(
                _url(league_id, "/tournaments"),
                json={"id": str(tournament_id), **SINGLES_ROUND_ROBIN},
                headers=committed_auth_header(owner_id, issued_at=datetime.now(UTC)),
            )
            outcome.append((response.status_code, response.json()))

        second = threading.Thread(target=create_second)
        second.start()
        wait_for_a_lock_wait()  # it waits for the league lock the start holds
        first.commit()
        second.join()

    assert [status for status, _ in outcome] == [201]
    with Session(committing_engine) as check:
        season_number = check.scalar(
            select(Season.number)
            .join(Tournament, Tournament.season_id == Season.id)
            .where(Tournament.id == tournament_id)
        )
        assert season_number == 2


@pytest.mark.concurrency
def test_adr008_two_pick_writes_on_one_tournament_apply_one_after_the_other(
    committing_settings: Settings,
    committing_engine: Engine,
    now: datetime,
    committed_auth_header: Callable[..., dict[str, str]],
    wait_for_a_lock_wait: Callable[[], None],
) -> None:
    owner_id, league_id, player_ids = _commit_league_with_players(
        committing_engine, now, "picks@example.test", 3
    )
    tournament_id = _commit_tournament(committing_engine, now, owner_id, league_id)
    outcome: list[tuple[int, object]] = []

    with (
        Session(committing_engine) as first,
        TestClient(create_app(committing_settings)) as client,
    ):
        tournament_service.set_tournament_players(
            first,
            league_id=league_id,
            tournament_id=tournament_id,
            user_id=owner_id,
            player_ids=player_ids[:2],
            clock=lambda: now,
        )

        def pick_second() -> None:
            response = client.put(
                _tournament_url(league_id, str(tournament_id), "/setup/players"),
                json={"player_ids": [str(p) for p in player_ids[1:]]},
                headers=committed_auth_header(owner_id, issued_at=datetime.now(UTC)),
            )
            outcome.append((response.status_code, response.json()))

        second = threading.Thread(target=pick_second)
        second.start()
        wait_for_a_lock_wait()  # it waits for the league lock the first one holds
        first.commit()
        second.join()

    assert [status for status, _ in outcome] == [200]
    with Session(committing_engine) as check:
        picked = set(check.scalars(select(TournamentPlayer.player_id)))
        members = set(check.scalars(select(EntryMember.player_id)))
        counter = check.scalar(select(Tournament.draw_counter))
    assert picked == members == set(player_ids[1:])  # the later write is the target
    assert counter == 2  # each write drew once


@pytest.mark.concurrency
def test_adr008_of_two_shuffles_with_one_counter_exactly_one_draws(
    committing_settings: Settings,
    committing_engine: Engine,
    now: datetime,
    committed_auth_header: Callable[..., dict[str, str]],
    wait_for_a_lock_wait: Callable[[], None],
) -> None:
    owner_id, league_id, player_ids = _commit_league_with_players(
        committing_engine, now, "shuffle@example.test", 4
    )
    tournament_id = uuid7()
    with Session(committing_engine) as setup:
        request = tournament_service.FormatRequest(
            name="Race",
            date=now.date(),
            type=TournamentType.SINGLES,
            group_phase=GroupPhase.NONE,
        )
        tournament_service.create_tournament(
            setup,
            league_id=league_id,
            user_id=owner_id,
            tournament_id=tournament_id,
            request=request,
            clock=lambda: now,
        )
        tournament_service.set_tournament_players(
            setup,
            league_id=league_id,
            tournament_id=tournament_id,
            user_id=owner_id,
            player_ids=player_ids,
            clock=lambda: now,
        )
        counter = tournament_service.set_seeding_method(
            setup,
            league_id=league_id,
            tournament_id=tournament_id,
            user_id=owner_id,
            method=SeedingMethod.RANDOM,
            clock=lambda: now,
        ).draw_counter
        setup.commit()
    outcome: list[tuple[int, object]] = []

    with (
        Session(committing_engine) as first,
        TestClient(create_app(committing_settings)) as client,
    ):
        tournament_service.draw_again(
            first,
            league_id=league_id,
            tournament_id=tournament_id,
            user_id=owner_id,
            target=tournament_service.DrawTarget.SEEDS,
            expected_draw_counter=counter,
            clock=lambda: now,
        )

        def shuffle_second() -> None:
            response = client.post(
                _tournament_url(league_id, str(tournament_id), "/setup/draw"),
                json={"expected_draw_counter": counter, "target": "seeds"},
                headers=committed_auth_header(owner_id, issued_at=datetime.now(UTC)),
            )
            outcome.append((response.status_code, response.json()))

        second = threading.Thread(target=shuffle_second)
        second.start()
        wait_for_a_lock_wait()  # it waits for the league lock the first one holds
        first.commit()
        second.join()

    assert outcome == [
        (409, {"code": "draw_counter_changed", "detail": {"draw_counter": counter + 1}})
    ]


@pytest.mark.concurrency
def test_br002_a_removal_racing_the_pick_is_refused_after_the_pick(
    committing_settings: Settings,
    committing_engine: Engine,
    now: datetime,
    committed_auth_header: Callable[..., dict[str, str]],
    wait_for_a_lock_wait: Callable[[], None],
) -> None:
    owner_id, league_id, player_ids = _commit_league_with_players(
        committing_engine, now, "pick@example.test", 2
    )
    tournament_id = uuid7()
    with Session(committing_engine) as setup:
        tournament_service.create_tournament(
            setup,
            league_id=league_id,
            user_id=owner_id,
            tournament_id=tournament_id,
            request=tournament_service.FormatRequest(
                name="Race",
                date=now.date(),
                type=TournamentType.SINGLES,
                group_phase=GroupPhase.NONE,
            ),
            clock=lambda: now,
        )
        setup.commit()
    outcome: list[tuple[int, object]] = []

    with (
        Session(committing_engine) as first,
        TestClient(create_app(committing_settings)) as client,
    ):
        tournament_service.set_tournament_players(
            first,
            league_id=league_id,
            tournament_id=tournament_id,
            user_id=owner_id,
            player_ids=player_ids,
            clock=lambda: now,
        )

        def remove_second() -> None:
            response = client.put(
                _url(league_id, f"/players/{player_ids[0]}/removed"),
                json={"removed": True},
                headers=committed_auth_header(owner_id, issued_at=datetime.now(UTC)),
            )
            outcome.append((response.status_code, response.json()))

        second = threading.Thread(target=remove_second)
        second.start()
        wait_for_a_lock_wait()  # it waits for the league lock the first one holds
        first.commit()
        second.join()

    assert outcome == [
        (
            422,
            {
                "code": "player_in_unfinished_tournament",
                "detail": {"tournament_ids": [str(tournament_id)]},
            },
        )
    ]
    with Session(committing_engine) as check:
        removed = check.scalar(
            select(Player.removed_at).where(Player.id == player_ids[0])
        )
        assert removed is None


# ---------------------------------------------------------------- repeats and edges


def test_adr008_repeated_pairs_and_seeding_change_nothing(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    tid = _doubles(client, league, headers, players[:4])
    pairs = {"pairs": [[players[0], players[1]]]}
    first = _ok(_write(client, league, tid, "/setup/pairs", pairs, headers))
    seeding = {"method": "ranking"}

    again = _ok(_write(client, league, tid, "/setup/pairs", pairs, headers))
    same_seeding = _ok(_write(client, league, tid, "/setup/seeding", seeding, headers))

    assert again == same_seeding == first


def test_br032_a_dyp_player_unpicked_loses_their_half_and_their_pair(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    tid = _dyp(client, league, headers, players[:4])["tournament_id"]
    rows = [
        {"player_id": p, "half": h}
        for p, h in zip(players[:4], ["top", "bottom", "top", "bottom"], strict=True)
    ]
    _ok(
        _write(
            client,
            league,
            tid,
            "/setup/halves",
            {"method": "by_hand", "halves": rows},
            headers,
        )
    )

    body = _ok(
        _write(
            client, league, tid, "/setup/players", {"player_ids": players[1:4]}, headers
        )
    )

    assert {row["player_id"] for row in body["halves"]} == set(players[1:4])
    assert body["entries"] == []
    by_ranking = _ok(
        _write(
            client,
            league,
            tid,
            "/setup/halves",
            {"method": "ranking", "halves": []},
            headers,
        )
    )
    assert by_ranking["halves_method"] == "ranking"
    assert by_ranking["halves"] == []  # three players: none yet (BR-031)


def test_fr030_a_dyp_that_becomes_singles_drops_its_halves(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    tid = _dyp(client, league, headers, players[:4])["tournament_id"]

    body = _ok(_write(client, league, tid, "/format", SINGLES_ROUND_ROBIN, headers))

    assert body["halves"] == []
    assert [e["kind"] for e in body["entries"]] == ["player"] * 4


def test_fr033_pairs_drawn_for_singles_are_stale(
    client: TestClient, league: League, headers: dict[str, str]
) -> None:
    created = _create(client, league, headers)

    status, body = _write(
        client,
        league,
        created["tournament_id"],
        "/setup/draw",
        {"expected_draw_counter": 0, "target": "pairs"},
        headers,
        method="POST",
    )

    assert (status, body["code"]) == (409, "tournament_type_changed")


def test_fr022_a_started_tournament_counts_the_players_of_its_entries(
    client: TestClient,
    league: League,
    season_id: UUID,
    headers: dict[str, str],
    players: list[str],
    session: Session,
) -> None:
    setup = _dyp(client, league, headers, players[:5])
    session.get_one(
        Tournament, UUID(setup["tournament_id"])
    ).state = TournamentState.IN_PROGRESS
    session.flush()

    listed = client.get(
        _url(league, f"/seasons/{season_id}/tournaments"), headers=headers
    ).json()

    assert listed[0]["player_count"] == 4  # the left-out player does not play
