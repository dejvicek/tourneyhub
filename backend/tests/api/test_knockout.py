"""The knockout after a round robin (FR-037, FR-045, FR-046, FR-054, BR-040 to
BR-044, BR-053, BR-080, BR-085 to BR-087, BR-090, BR-094, BR-102, BR-103, BR-120,
BR-130).
"""

import threading
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid7

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from tourneyhub.app import create_app
from tourneyhub.db.models.accounts import User
from tourneyhub.db.models.entries import Entry
from tourneyhub.db.models.leagues import League, Player, Season
from tourneyhub.db.models.tournaments import Tournament, TournamentPhase
from tourneyhub.engine.accounts import Language
from tourneyhub.engine.leagues import SeasonState
from tourneyhub.engine.results import Game
from tourneyhub.engine.tournaments import (
    GroupPhase,
    Outcome,
    SeedingMethod,
    TournamentType,
)
from tourneyhub.errors import NotFoundError
from tourneyhub.services import knockout as knockout_service
from tourneyhub.services import leagues as league_service
from tourneyhub.services import players as player_service
from tourneyhub.services import tournaments as tournament_service
from tourneyhub.settings import Settings

type Json = dict[str, Any]

ROUND_ROBIN: Json = {
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
EMPTY: Json = {"walkover_winner": None, "games": []}


def _seed_order(setup: Json) -> list[str]:
    """The entries of a setup in seed order, as the review's start carries them."""
    return [e["id"] for e in sorted(setup["entries"], key=lambda e: e["seed"] or 0)]


def win(side: str, score: tuple[int, int] = (10, 5)) -> Json:
    winner, loser = score
    scores = (winner, loser) if side == "side_1" else (loser, winner)
    return {
        "walkover_winner": None,
        "games": [{"winner": side, "score_1": scores[0], "score_2": scores[1]}],
    }


def bo3(side: str) -> Json:
    game = {"winner": side, "score_1": None, "score_2": None}
    return {"walkover_winner": None, "games": [game, game]}


def _url(league_id: UUID, rest: str = "") -> str:
    return f"/api/v1/leagues/{league_id}{rest}"


def _t_url(league_id: UUID, tournament_id: str, rest: str = "") -> str:
    return _url(league_id, f"/tournaments/{tournament_id}{rest}")


def _public(token: str, tournament_id: str, rest: str = "") -> str:
    return f"/api/v1/public/{token}/tournaments/{tournament_id}{rest}"


def seeds_of(tournament: Json) -> dict[str, int]:
    return {e["id"]: e["seed"] for e in tournament["entries"]}


def group_of(tournament: Json) -> Json:
    return next(p for p in tournament["phases"] if p["kind"] == "group")


def knockout_of(tournament: Json) -> Json:
    return next(p for p in tournament["phases"] if p["kind"] == "knockout")


def matches_of(tournament: Json, phase: Json) -> list[Json]:
    return [
        match
        for round_ in tournament["rounds"]
        if round_["phase_id"] == phase["id"]
        for match in round_["matches"]
    ]


def better_seed_wins(tournament: Json, match: Json) -> Json:
    """The side whose entry has the better seed wins: standings follow the seeds."""
    seed = seeds_of(tournament)
    one, two = (side["entry_id"] for side in match["sides"])
    return win("side_1" if seed[one] < seed[two] else "side_2")


@pytest.fixture
def league(make_league: Callable[..., League]) -> League:
    return make_league()


@pytest.fixture
def league_id(league: League) -> UUID:
    return league.id


@pytest.fixture
def token(league: League) -> str:
    return league.share_token


@pytest.fixture
def headers(
    league: League, auth_header: Callable[..., dict[str, str]]
) -> dict[str, str]:
    return auth_header(league.owner_user_id)


@pytest.fixture
def players(league: League, make_player: Callable[..., Player]) -> list[str]:
    return [str(make_player(league=league, name=f"P{n}").id) for n in range(1, 9)]


@pytest.fixture
def put_result(
    client: TestClient, league_id: UUID, headers: dict[str, str]
) -> Callable[[str, str, Json], tuple[int, Json]]:
    def put_result(tournament_id: str, match_id: str, body: Json) -> tuple[int, Json]:
        """Send a result; a bracket match with both sides known names them (BR-094)."""
        if "expected_sides" not in body:
            shown = client.get(
                _t_url(league_id, tournament_id, "/bracket"), headers=headers
            )
            if shown.status_code == 200:
                sides = next(
                    (
                        [side["entry_id"] for side in m["sides"]]
                        for r in shown.json()["rounds"]
                        for m in r["matches"]
                        if m["match_id"] == match_id
                    ),
                    None,
                )
                if sides is not None and None not in sides:
                    body = {**body, "expected_sides": sides}
        response = client.put(
            _t_url(league_id, tournament_id, f"/matches/{match_id}/result"),
            json=body,
            headers=headers,
        )
        result: Json = response.json()
        return response.status_code, result

    return put_result


@pytest.fixture
def read(
    client: TestClient, league_id: UUID, headers: dict[str, str]
) -> Callable[[str, str], Json]:
    def read(tournament_id: str, rest: str = "") -> Json:
        response = client.get(_t_url(league_id, tournament_id, rest), headers=headers)
        assert response.status_code == 200, response.text
        result: Json = response.json()
        return result

    return read


@pytest.fixture
def played_group(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    players: list[str],
    put_result: Callable[[str, str, Json], tuple[int, Json]],
    read: Callable[[str, str], Json],
) -> Callable[..., Json]:
    """A round robin of `count` players, every match won by the better seed."""

    def played_group(count: int = 6, *, finish: bool = True, **values: object) -> Json:
        body = {"id": str(uuid7()), **ROUND_ROBIN, **values}
        created = client.post(
            _url(league_id, "/tournaments"), json=body, headers=headers
        )
        assert created.status_code == 201, created.text
        tournament_id = created.json()["tournament_id"]
        picked = client.put(
            _t_url(league_id, tournament_id, "/setup/players"),
            json={"player_ids": players[:count]},
            headers=headers,
        )
        assert picked.status_code == 200, picked.text
        started = client.post(
            _t_url(league_id, tournament_id, "/start"),
            json={
                "expected_draw_counter": picked.json()["draw_counter"],
                "expected_seed_order": _seed_order(picked.json()),
            },
            headers=headers,
        )
        assert started.status_code == 200, started.text
        tournament: Json = started.json()
        matches = matches_of(tournament, group_of(tournament))
        for match in matches if finish else matches[:-1]:
            status, _ = put_result(
                tournament_id, match["id"], better_seed_wins(tournament, match)
            )
            assert status == 200
        return read(tournament_id, "")

    return played_group


@pytest.fixture
def start_knockout(
    client: TestClient, league_id: UUID, headers: dict[str, str]
) -> Callable[..., tuple[int, Json]]:
    def start_knockout(tournament: Json, **values: object) -> tuple[int, Json]:
        """Start as the screen does: it names the qualifiers its preview showed."""
        qualifiers = values.get("qualifiers", 6)
        third = str(values.get("third_place_match", True)).lower()
        shown = client.get(
            _t_url(
                league_id,
                tournament["id"],
                f"/knockout/preview?qualifiers={qualifiers}&third_place_match={third}",
            ),
            headers=headers,
        ).json()
        body = {
            "expected_current_phase_id": tournament["current_phase_id"],
            "expected_draw_counter": shown["draw_counter"],
            "expected_qualifier_ids": [
                e["members"][0]["entry_id"] for e in shown["entries"]
            ],
            "qualifiers": 6,
            "third_place_match": True,
            "match_format": None,
            "final_match_format": None,
            "mode": None,
            **values,
        }
        response = client.put(
            _t_url(league_id, tournament["id"], "/knockout"), json=body, headers=headers
        )
        result: Json = response.json()
        return response.status_code, result

    return start_knockout


@pytest.fixture
def drawn(
    played_group: Callable[..., Json],
    start_knockout: Callable[..., tuple[int, Json]],
) -> Json:
    """Six players after their round robin, with a knockout of six and 3rd place."""
    status, tournament = start_knockout(played_group(6))
    assert status == 200, tournament
    return tournament


def bracket_matches(bracket: Json) -> dict[tuple[int, str, int], Json]:
    return {
        (m["round_no"], m["kind"], m["position"]): m
        for round_ in bracket["rounds"]
        for m in round_["matches"]
    }


# ---------------------------------------------------------------- preview


def test_fr045_the_preview_shows_the_cut_seeds_and_byes(
    played_group: Callable[..., Json], read: Callable[[str, str], Json]
) -> None:
    tournament = played_group(6)

    preview = read(
        tournament["id"], "/knockout/preview?qualifiers=6&third_place_match=true"
    )

    assert preview["can_start"] is True
    assert preview["problem"] is None
    assert preview["bracket_size"] == 8
    assert preview["first_round"] == [[1, None], [4, 5], [2, None], [3, 6]]
    seed = seeds_of(tournament)
    assert [
        (
            entry["seed"],
            seed[entry["members"][0]["entry_id"]],
            entry["members"][0]["place"],
        )
        for entry in preview["entries"]
    ] == [(n, n, n) for n in range(1, 7)]
    assert preview["locks_round_no"] == 5
    assert preview["max_qualifiers"] == 6
    assert preview["is_cut_by_lot"] is False


def test_br080_the_preview_keeps_the_number_within_what_a_knockout_takes(
    played_group: Callable[..., Json], read: Callable[[str, str], Json]
) -> None:
    tournament = played_group(5)

    many = read(
        tournament["id"], "/knockout/preview?qualifiers=8&third_place_match=false"
    )
    few = read(
        tournament["id"], "/knockout/preview?qualifiers=2&third_place_match=true"
    )

    assert many["qualifiers"] == 5
    assert few["qualifiers"] == 4
    assert few["first_round"] == [[1, 4], [2, 3]]


def test_fr040_the_preview_of_an_unfinished_group_phase_names_the_problem(
    played_group: Callable[..., Json], read: Callable[[str, str], Json]
) -> None:
    tournament = played_group(4, finish=False)

    preview = read(
        tournament["id"], "/knockout/preview?qualifiers=4&third_place_match=false"
    )

    assert preview["can_start"] is False
    assert preview["problem"] == {
        "code": "group_phase_not_done",
        "detail": {"matches_left": 1},
    }


def test_br080_three_entries_cannot_have_a_third_place_match(
    played_group: Callable[..., Json], read: Callable[[str, str], Json]
) -> None:
    tournament = played_group(3)

    preview = read(
        tournament["id"], "/knockout/preview?qualifiers=4&third_place_match=true"
    )

    assert preview["entries"] == []
    assert preview["max_qualifiers"] == 3


# ---------------------------------------------------------------- start


def test_fr045_the_knockout_starts_with_entries_that_continue_the_group(
    played_group: Callable[..., Json],
    start_knockout: Callable[..., tuple[int, Json]],
) -> None:
    tournament = played_group(6)

    status, started = start_knockout(tournament, final_match_format="bo3")

    assert status == 200, started
    knockout = knockout_of(started)
    assert started["current_phase_id"] == knockout["id"]
    assert (knockout["position"], knockout["qualifiers"]) == (2, 6)
    assert knockout["third_place_match"] is True
    assert (knockout["match_format"], knockout["final_match_format"]) == ("bo1", "bo3")
    main = {
        tuple(e["player_ids"]): e["seed"]
        for e in started["entries"]
        if e["stage"] == "main"
    }
    entries = [e for e in started["entries"] if e["stage"] == "knockout"]
    assert sorted(e["seed"] for e in entries) == list(range(1, 7))
    assert all(e["seed"] == main[tuple(e["player_ids"])] for e in entries)
    rounds = [r for r in started["rounds"] if r["phase_id"] == knockout["id"]]
    assert [len(r["matches"]) for r in rounds] == [4, 2, 2]  # final and 3rd place


def test_br130_the_first_playable_knockout_matches_take_the_fields(drawn: Json) -> None:
    knockout = knockout_of(drawn)
    first = matches_of(drawn, knockout)[:4]
    playable = [m["id"] for m in first if not any(s["is_bye"] for s in m["sides"])]

    on_fields = [
        f["match_id"] for f in sorted(drawn["fields"], key=lambda f: f["number"])
    ]

    assert on_fields == playable


def test_br120_the_knockout_takes_the_league_default_format(
    played_group: Callable[..., Json],
    start_knockout: Callable[..., tuple[int, Json]],
    session: Session,
    league: League,
) -> None:
    league.default_match_format = league.default_match_format.__class__("bo3")
    session.flush()

    _, started = start_knockout(played_group(4), qualifiers=4, third_place_match=False)

    assert knockout_of(started)["match_format"] == "bo3"
    assert knockout_of(started)["final_match_format"] is None


def test_adr008_a_repeated_start_is_409(
    drawn: Json, start_knockout: Callable[..., tuple[int, Json]]
) -> None:
    group = group_of(drawn)
    status, body = start_knockout({**drawn, "current_phase_id": group["id"]})

    assert status == 409
    assert body == {
        "code": "current_phase_changed",
        "detail": {"current_phase_id": knockout_of(drawn)["id"]},
    }


def test_fr040_a_knockout_before_the_group_phase_ends_is_422(
    played_group: Callable[..., Json],
    start_knockout: Callable[..., tuple[int, Json]],
) -> None:
    status, body = start_knockout(played_group(4, finish=False), qualifiers=4)

    assert status == 422
    assert body == {"code": "group_phase_not_done", "detail": {"matches_left": 1}}


@pytest.mark.parametrize(
    ("qualifiers", "third_place", "detail"),
    [
        pytest.param(5, False, {"minimum": 2, "maximum": 4, "given": 5}, id="too-many"),
        pytest.param(3, True, {"minimum": 4, "maximum": 4, "given": 3}, id="3rd-place"),
    ],
)
def test_br080_a_qualifier_count_out_of_range_is_422(
    played_group: Callable[..., Json],
    start_knockout: Callable[..., tuple[int, Json]],
    *,
    qualifiers: int,
    third_place: bool,
    detail: Json,
) -> None:
    status, body = start_knockout(
        played_group(4), qualifiers=qualifiers, third_place_match=third_place
    )

    assert status == 422
    assert body == {"code": "qualifiers_out_of_range", "detail": detail}


def test_fr045_a_group_result_changed_since_the_preview_is_409(
    played_group: Callable[..., Json],
    start_knockout: Callable[..., tuple[int, Json]],
    read: Callable[[str, str], Json],
    put_result: Callable[[str, str, Json], tuple[int, Json]],
) -> None:
    tournament = played_group(4)
    query = "/knockout/preview?qualifiers=4&third_place_match=false"
    previewed = [
        e["members"][0]["entry_id"] for e in read(tournament["id"], query)["entries"]
    ]
    seed = seeds_of(tournament)
    top_two = {previewed[0], previewed[1]}
    match = next(
        m
        for m in matches_of(tournament, group_of(tournament))
        if {side["entry_id"] for side in m["sides"]} == top_two
    )
    second_wins = (
        "side_1" if match["sides"][0]["entry_id"] == previewed[1] else "side_2"
    )
    assert put_result(tournament["id"], match["id"], win(second_wins))[0] == 200
    current = [
        e["members"][0]["entry_id"] for e in read(tournament["id"], query)["entries"]
    ]
    assert current != previewed
    assert seed[previewed[0]] == 1

    status, body = start_knockout(
        tournament,
        qualifiers=4,
        third_place_match=False,
        expected_qualifier_ids=previewed,
    )

    assert (status, body) == (
        409,
        {"code": "qualifiers_changed", "detail": {"entry_ids": current}},
    )
    assert (
        read(tournament["id"], "")["current_phase_id"] == tournament["current_phase_id"]
    )


def test_fr045_the_previewed_qualifiers_start_the_knockout(
    played_group: Callable[..., Json],
    start_knockout: Callable[..., tuple[int, Json]],
) -> None:
    status, started = start_knockout(
        played_group(4), qualifiers=4, third_place_match=False
    )

    assert status == 200
    assert len(started["phases"]) == 2


def test_br011_a_closed_season_is_the_previews_problem_and_the_starts_409(
    played_group: Callable[..., Json],
    start_knockout: Callable[..., tuple[int, Json]],
    read: Callable[[str, str], Json],
    session: Session,
    now: datetime,
) -> None:
    tournament = played_group(4)
    season = session.get_one(Season, UUID(tournament["season_id"]))
    season.state, season.closed_at = SeasonState.CLOSED, now
    session.flush()  # season 1 closes before season 2 becomes the active one
    session.add(
        Season(
            league_id=season.league_id,
            number=2,
            state=SeasonState.ACTIVE,
            placement_points=season.placement_points,
            started_at=now,
            created_at=now,
        )
    )
    session.flush()

    preview = read(
        tournament["id"], "/knockout/preview?qualifiers=4&third_place_match=false"
    )
    status, body = start_knockout(tournament, qualifiers=4, third_place_match=False)

    assert preview["can_start"] is False
    assert preview["problem"] == {"code": "season_closed", "detail": {}}
    assert (status, body) == (409, {"code": "season_closed", "detail": {}})


def test_adr008_a_knockout_of_a_tournament_in_setup_is_409(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    start_knockout: Callable[..., tuple[int, Json]],
) -> None:
    body = {"id": str(uuid7()), **ROUND_ROBIN}
    created = client.post(_url(league_id, "/tournaments"), json=body, headers=headers)
    tournament_id = created.json()["tournament_id"]

    status, result = start_knockout(
        {"id": tournament_id, "current_phase_id": str(uuid7())}
    )

    assert status == 409
    assert result == {
        "code": "tournament_not_in_progress",
        "detail": {"state": "setup"},
    }


def test_fr045_a_team_mode_after_a_round_robin_is_422(
    played_group: Callable[..., Json],
    start_knockout: Callable[..., tuple[int, Json]],
    read: Callable[[str, str], Json],
) -> None:
    tournament = played_group(4)

    status, body = start_knockout(tournament, qualifiers=4, mode="seeded_pairs")
    preview = read(
        tournament["id"],
        "/knockout/preview?qualifiers=4&third_place_match=false&mode=singles",
    )

    refusal = {
        "code": "knockout_mode_not_applicable",
        "detail": {"format": "round_robin"},
    }
    assert (status, body) == (422, refusal)
    assert preview["problem"] == refusal


def test_br121_bo2_is_never_a_knockouts(
    played_group: Callable[..., Json],
    start_knockout: Callable[..., tuple[int, Json]],
) -> None:
    status, body = start_knockout(played_group(4), qualifiers=4, match_format="bo2")

    assert status == 422
    assert body["code"] == "validation_failed"


# ---------------------------------------------------------------- results


def test_br053_the_round_robin_locks_once_the_knockout_is_drawn(
    drawn: Json, put_result: Callable[[str, str, Json], tuple[int, Json]]
) -> None:
    match = matches_of(drawn, group_of(drawn))[0]

    status, body = put_result(drawn["id"], match["id"], EMPTY)

    assert status == 422
    assert body == {
        "code": "group_phase_locked",
        "detail": {"phase_id": knockout_of(drawn)["id"]},
    }


def test_br091_a_bye_and_a_side_still_to_come_take_no_result(
    drawn: Json,
    read: Callable[[str, str], Json],
    put_result: Callable[[str, str, Json], tuple[int, Json]],
) -> None:
    bracket = bracket_matches(read(drawn["id"], "/bracket"))

    bye = put_result(drawn["id"], bracket[1, "standard", 1]["match_id"], win("side_1"))
    final = put_result(
        drawn["id"], bracket[3, "standard", 1]["match_id"], win("side_1")
    )

    assert bye == (422, {"code": "match_sides_unknown", "detail": {}})
    assert final == (422, {"code": "match_sides_unknown", "detail": {}})


def test_br090_a_knockout_has_no_draws(
    drawn: Json,
    read: Callable[[str, str], Json],
    put_result: Callable[[str, str, Json], tuple[int, Json]],
    league: League,
    session: Session,
) -> None:
    league.draws_allowed = True
    session.flush()
    match_id = bracket_matches(read(drawn["id"], "/bracket"))[1, "standard", 2][
        "match_id"
    ]

    status, body = put_result(
        drawn["id"],
        match_id,
        {
            "walkover_winner": None,
            "games": [{"winner": "draw", "score_1": 5, "score_2": 5}],
        },
    )

    assert (status, body["code"]) == (422, "draws_not_allowed")


def test_d4_a_winner_takes_the_side_of_the_next_match(
    drawn: Json,
    read: Callable[[str, str], Json],
    put_result: Callable[[str, str, Json], tuple[int, Json]],
) -> None:
    bracket = bracket_matches(read(drawn["id"], "/bracket"))
    quarter = bracket[1, "standard", 2]  # seeds 4 and 5

    status, _ = put_result(drawn["id"], quarter["match_id"], win("side_2"))

    after = bracket_matches(read(drawn["id"], "/bracket"))
    semi = after[2, "standard", 1]
    assert status == 200
    assert [side["seed"] for side in semi["sides"]] == [1, 5]
    assert semi["state"] in {"ready", "on_field"}
    view = read(drawn["id"], "")
    shown = next(
        m for m in matches_of(view, knockout_of(view)) if m["id"] == semi["match_id"]
    )
    assert [s["entry_id"] for s in shown["sides"]] == [
        s["entry_id"] for s in semi["sides"]
    ]
    assert all(s["player_ids"] for s in shown["sides"])


def _play_to_the_semifinals(
    drawn: Json,
    read: Callable[[str, str], Json],
    put_result: Callable[[str, str, Json], tuple[int, Json]],
) -> dict[tuple[int, str, int], Json]:
    bracket = bracket_matches(read(drawn["id"], "/bracket"))
    for position in (2, 4):  # seeds 4 v 5 and 3 v 6; the better seeds win
        status, _ = put_result(
            drawn["id"], bracket[1, "standard", position]["match_id"], win("side_1")
        )
        assert status == 200
    return bracket_matches(read(drawn["id"], "/bracket"))


def _play_out(
    drawn: Json,
    read: Callable[[str, str], Json],
    put_result: Callable[[str, str, Json], tuple[int, Json]],
    *,
    third_last: bool = True,
) -> dict[tuple[int, str, int], Json]:
    bracket = _play_to_the_semifinals(drawn, read, put_result)
    for position in (1, 2):
        status, _ = put_result(
            drawn["id"], bracket[2, "standard", position]["match_id"], win("side_1")
        )
        assert status == 200
    order = [("third_place", win("side_2")), ("standard", win("side_1"))]
    for kind, result in order if third_last is False else reversed(order):
        status, _ = put_result(drawn["id"], bracket[3, kind, 1]["match_id"], result)
        assert status == 200
    return bracket_matches(read(drawn["id"], "/bracket"))


@pytest.mark.parametrize("third_last", [True, False], ids=["third-last", "final-last"])
def test_fr037_the_last_knockout_result_finishes_the_tournament(
    drawn: Json,
    read: Callable[[str, str], Json],
    put_result: Callable[[str, str, Json], tuple[int, Json]],
    *,
    third_last: bool,
) -> None:
    bracket = _play_to_the_semifinals(drawn, read, put_result)
    for position in (1, 2):
        put_result(
            drawn["id"], bracket[2, "standard", position]["match_id"], win("side_1")
        )
    first, last = (
        ("standard", "third_place") if third_last else ("third_place", "standard")
    )

    put_result(drawn["id"], bracket[3, first, 1]["match_id"], win("side_1"))
    before = read(drawn["id"], "")["state"]
    put_result(drawn["id"], bracket[3, last, 1]["match_id"], win("side_1"))

    assert before == "in_progress"
    assert read(drawn["id"], "")["state"] == "finished"


def test_br095_clearing_the_final_puts_the_tournament_back_in_progress(
    drawn: Json,
    read: Callable[[str, str], Json],
    put_result: Callable[[str, str, Json], tuple[int, Json]],
) -> None:
    bracket = _play_out(drawn, read, put_result)

    status, _ = put_result(drawn["id"], bracket[3, "standard", 1]["match_id"], EMPTY)

    assert status == 200
    assert read(drawn["id"], "")["state"] == "in_progress"


def test_br094_a_semifinal_is_locked_once_the_final_has_a_result(
    drawn: Json,
    read: Callable[[str, str], Json],
    put_result: Callable[[str, str, Json], tuple[int, Json]],
) -> None:
    bracket = _play_out(drawn, read, put_result)
    semi = bracket[2, "standard", 1]

    changed = put_result(drawn["id"], semi["match_id"], win("side_2"))
    cleared = put_result(drawn["id"], semi["match_id"], EMPTY)
    repeated = put_result(drawn["id"], semi["match_id"], win("side_1"))

    locked_by = sorted(
        [
            bracket[3, "standard", 1]["match_id"],
            bracket[3, "third_place", 1]["match_id"],
        ]
    )
    for status, body in (changed, cleared):
        assert status == 422
        assert body["code"] == "result_locked"
        assert sorted(body["detail"]["match_ids"]) == locked_by
    assert repeated[0] == 200
    assert semi["result_locked"] is True


def test_br094_the_third_place_match_alone_locks_the_semifinals(
    drawn: Json,
    read: Callable[[str, str], Json],
    put_result: Callable[[str, str, Json], tuple[int, Json]],
) -> None:
    bracket = _play_to_the_semifinals(drawn, read, put_result)
    for position in (1, 2):
        put_result(
            drawn["id"], bracket[2, "standard", position]["match_id"], win("side_1")
        )
    third = bracket[3, "third_place", 1]["match_id"]
    put_result(drawn["id"], third, win("side_1"))

    status, body = put_result(drawn["id"], bracket[2, "standard", 2]["match_id"], EMPTY)

    assert status == 422
    assert body == {"code": "result_locked", "detail": {"match_ids": [third]}}


def test_br094_a_changed_winner_changes_the_later_sides(
    drawn: Json,
    read: Callable[[str, str], Json],
    put_result: Callable[[str, str, Json], tuple[int, Json]],
) -> None:
    bracket = _play_to_the_semifinals(drawn, read, put_result)
    semi = bracket[2, "standard", 1]["match_id"]
    put_result(drawn["id"], semi, win("side_1"))

    status, _ = put_result(drawn["id"], semi, win("side_2"))

    after = bracket_matches(read(drawn["id"], "/bracket"))
    assert status == 200
    assert after[3, "standard", 1]["sides"][0]["seed"] == 4
    assert after[3, "third_place", 1]["sides"][0]["seed"] == 1


def _entry_ids(match: Json) -> list[str]:
    return [side["entry_id"] for side in match["sides"]]


def test_br094_a_result_of_a_derived_match_names_the_entries_it_saw(
    drawn: Json,
    read: Callable[[str, str], Json],
    put_result: Callable[[str, str, Json], tuple[int, Json]],
) -> None:
    bracket = _play_to_the_semifinals(drawn, read, put_result)
    semi = bracket[2, "standard", 1]
    seen = _entry_ids(semi)

    without = put_result(
        drawn["id"], semi["match_id"], {**win("side_1"), "expected_sides": None}
    )
    stale = put_result(
        drawn["id"], semi["match_id"], {**win("side_1"), "expected_sides": seen[::-1]}
    )
    right = put_result(
        drawn["id"], semi["match_id"], {**win("side_1"), "expected_sides": seen}
    )

    assert without == (422, {"code": "expected_sides_required", "detail": {}})
    assert stale == (
        409,
        {"code": "match_sides_changed", "detail": {"entry_ids": seen}},
    )
    assert right[0] == 200
    after = bracket_matches(read(drawn["id"], "/bracket"))
    assert after[2, "standard", 1]["outcome"] == "side_1"


def test_br094_a_stale_screen_cannot_decide_a_match_whose_sides_changed(
    drawn: Json,
    read: Callable[[str, str], Json],
    put_result: Callable[[str, str, Json], tuple[int, Json]],
) -> None:
    bracket = _play_to_the_semifinals(drawn, read, put_result)
    for position in (1, 2):
        put_result(
            drawn["id"], bracket[2, "standard", position]["match_id"], win("side_1")
        )
    final = bracket_matches(read(drawn["id"], "/bracket"))[3, "standard", 1]
    seen = _entry_ids(final)
    put_result(drawn["id"], bracket[2, "standard", 1]["match_id"], EMPTY)

    status, body = put_result(
        drawn["id"], final["match_id"], {**win("side_1"), "expected_sides": seen}
    )

    after = bracket_matches(read(drawn["id"], "/bracket"))[3, "standard", 1]
    assert (status, body["code"]) == (409, "match_sides_changed")
    assert body["detail"]["entry_ids"] == [None, seen[1]]
    assert after["outcome"] is None


def test_br094_the_sides_of_a_first_round_match_are_checked_when_sent(
    drawn: Json,
    read: Callable[[str, str], Json],
    put_result: Callable[[str, str, Json], tuple[int, Json]],
) -> None:
    match = bracket_matches(read(drawn["id"], "/bracket"))[1, "standard", 2]
    seen = _entry_ids(match)

    stale = put_result(
        drawn["id"], match["match_id"], {**win("side_1"), "expected_sides": seen[::-1]}
    )
    sent_none = put_result(
        drawn["id"], match["match_id"], {**win("side_1"), "expected_sides": None}
    )

    assert stale[1]["code"] == "match_sides_changed"
    assert sent_none[0] == 200


def test_br130_a_final_whose_side_is_cleared_leaves_its_field(
    drawn: Json,
    read: Callable[[str, str], Json],
    put_result: Callable[[str, str, Json], tuple[int, Json]],
) -> None:
    bracket = _play_to_the_semifinals(drawn, read, put_result)
    for position in (1, 2):
        put_result(
            drawn["id"], bracket[2, "standard", position]["match_id"], win("side_1")
        )
    final = bracket[3, "standard", 1]["match_id"]
    assert final in {f["match_id"] for f in read(drawn["id"], "")["fields"]}

    put_result(drawn["id"], bracket[2, "standard", 1]["match_id"], EMPTY)

    fields = {f["match_id"] for f in read(drawn["id"], "")["fields"]}
    after = bracket_matches(read(drawn["id"], "/bracket"))
    assert final not in fields
    assert after[3, "standard", 1]["state"] == "waiting"


def test_br074_the_bracket_marks_the_seeds_a_lot_decided(
    played_group: Callable[..., Json],
    start_knockout: Callable[..., tuple[int, Json]],
    read: Callable[[str, str], Json],
    put_result: Callable[[str, str, Json], tuple[int, Json]],
    client: TestClient,
    token: str,
) -> None:
    # Three entries each beat one other: level on every criterion, so a lot
    # orders them and takes two through the cut.
    tournament = played_group(3, finish=False)
    seed = seeds_of(tournament)
    beats = {(1, 2), (2, 3), (3, 1)}
    for match in matches_of(tournament, group_of(tournament)):
        one, two = (seed[side["entry_id"]] for side in match["sides"])
        put_result(
            tournament["id"],
            match["id"],
            win("side_1" if (one, two) in beats else "side_2"),
        )
    tournament = read(tournament["id"], "")
    query = "/knockout/preview?qualifiers=2&third_place_match=false"
    preview = read(tournament["id"], query)
    assert preview["is_cut_by_lot"] is True
    status, _ = start_knockout(tournament, qualifiers=2, third_place_match=False)
    assert status == 200

    bracket = read(tournament["id"], "/bracket")
    public = client.get(_public(token, tournament["id"], "/bracket")).json()

    for shown in (bracket, public):
        final = bracket_matches(shown)[1, "standard", 1]
        assert [(side["seed"], side["decided_by_lot"]) for side in final["sides"]] == [
            (1, True),
            (2, True),
        ]
    assert [e["decided_by_lot"] for e in preview["entries"]] == [True, True]


def test_br074_a_clear_standing_marks_no_seed(
    drawn: Json, read: Callable[[str, str], Json]
) -> None:
    bracket = bracket_matches(read(drawn["id"], "/bracket"))

    assert not any(
        side["decided_by_lot"] for match in bracket.values() for side in match["sides"]
    )


def test_br120_the_final_plays_its_own_format(
    played_group: Callable[..., Json],
    start_knockout: Callable[..., tuple[int, Json]],
    read: Callable[[str, str], Json],
    put_result: Callable[[str, str, Json], tuple[int, Json]],
) -> None:
    _, started = start_knockout(
        played_group(2), qualifiers=2, third_place_match=False, final_match_format="bo3"
    )
    final = bracket_matches(read(started["id"], "/bracket"))[1, "standard", 1]

    single = put_result(started["id"], final["match_id"], win("side_1"))
    series = put_result(started["id"], final["match_id"], bo3("side_2"))

    assert final["match_format"] == "bo3"
    assert single[0] == 422
    assert single[1]["code"] == "result_does_not_fit_format"
    assert series[0] == 200
    assert read(started["id"], "")["state"] == "finished"


# ---------------------------------------------------------------- the final's format


@pytest.fixture
def set_final(
    client: TestClient, league_id: UUID, headers: dict[str, str]
) -> Callable[[str, str | None], tuple[int, Json]]:
    def set_final(tournament_id: str, final_format: str | None) -> tuple[int, Json]:
        response = client.put(
            _t_url(league_id, tournament_id, "/knockout/final-format"),
            json={"final_match_format": final_format},
            headers=headers,
        )
        result: Json = response.json()
        return response.status_code, result

    return set_final


def test_fr054_br120_the_final_gets_a_format_of_its_own_after_the_start(
    drawn: Json,
    read: Callable[[str, str], Json],
    set_final: Callable[[str, str | None], tuple[int, Json]],
) -> None:
    status, body = set_final(drawn["id"], "bo5")
    bracket = read(drawn["id"], "/bracket")
    matches = bracket_matches(bracket)

    assert status == 200
    assert knockout_of(body)["final_match_format"] == "bo5"
    assert bracket["final_match_format"] == "bo5"
    assert matches[3, "standard", 1]["match_format"] == "bo5"
    assert matches[3, "third_place", 1]["match_format"] == "bo1"
    assert matches[2, "standard", 1]["match_format"] == "bo1"


def test_fr054_br120_a_cleared_final_format_plays_the_knockouts_again(
    played_group: Callable[..., Json],
    start_knockout: Callable[..., tuple[int, Json]],
    read: Callable[[str, str], Json],
    set_final: Callable[[str, str | None], tuple[int, Json]],
) -> None:
    _, started = start_knockout(
        played_group(4), qualifiers=4, match_format="bo3", final_match_format="bo5"
    )

    status, body = set_final(started["id"], None)
    repeated = set_final(started["id"], None)
    bracket = read(started["id"], "/bracket")

    assert status == 200
    assert knockout_of(body)["final_match_format"] is None
    assert repeated[0] == 200
    assert bracket["final_match_format"] is None
    assert bracket_matches(bracket)[2, "standard", 1]["match_format"] == "bo3"


def test_fr054_br121_bo2_is_never_the_finals(
    drawn: Json, set_final: Callable[[str, str | None], tuple[int, Json]]
) -> None:
    status, body = set_final(drawn["id"], "bo2")

    assert status == 422
    assert body["code"] == "validation_failed"


def test_fr054_br096_br120_a_final_with_a_result_keeps_its_format(
    drawn: Json,
    read: Callable[[str, str], Json],
    put_result: Callable[[str, str, Json], tuple[int, Json]],
    set_final: Callable[[str, str | None], tuple[int, Json]],
) -> None:
    bracket = _play_to_the_semifinals(drawn, read, put_result)
    for position in (1, 2):
        put_result(
            drawn["id"], bracket[2, "standard", position]["match_id"], win("side_1")
        )
    final = bracket[3, "standard", 1]["match_id"]
    put_result(drawn["id"], final, win("side_1"))

    refused = set_final(drawn["id"], "bo3")
    put_result(drawn["id"], final, EMPTY)
    cleared = set_final(drawn["id"], "bo3")

    assert refused == (409, {"code": "match_has_result", "detail": {"match_id": final}})
    assert cleared[0] == 200
    assert read(drawn["id"], "/bracket")["final_match_format"] == "bo3"


def test_fr054_br120_a_finished_tournaments_final_keeps_its_format(
    drawn: Json,
    read: Callable[[str, str], Json],
    put_result: Callable[[str, str, Json], tuple[int, Json]],
    set_final: Callable[[str, str | None], tuple[int, Json]],
) -> None:
    bracket = _play_out(drawn, read, put_result)

    status, body = set_final(drawn["id"], "bo3")

    assert read(drawn["id"], "")["state"] == "finished"
    assert status == 409
    assert body["code"] == "match_has_result"
    assert body["detail"] == {"match_id": bracket[3, "standard", 1]["match_id"]}


def test_fr054_br120_a_tournament_without_a_knockout_has_no_final_to_change(
    played_group: Callable[..., Json],
    set_final: Callable[[str, str | None], tuple[int, Json]],
) -> None:
    status, body = set_final(played_group(4)["id"], "bo3")

    assert (status, body) == (404, {"code": "knockout_not_found", "detail": {}})


def test_fr054_br120_the_final_of_a_tournament_in_setup_is_409(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    set_final: Callable[[str, str | None], tuple[int, Json]],
) -> None:
    body = {"id": str(uuid7()), **ROUND_ROBIN}
    created = client.post(_url(league_id, "/tournaments"), json=body, headers=headers)

    status, result = set_final(created.json()["tournament_id"], "bo3")

    assert status == 409
    assert result == {
        "code": "tournament_not_in_progress",
        "detail": {"state": "setup"},
    }


def test_fr054_br120_br011_the_final_of_a_closed_season_is_409(
    drawn: Json,
    session: Session,
    now: datetime,
    set_final: Callable[[str, str | None], tuple[int, Json]],
) -> None:
    season = session.get_one(Season, UUID(drawn["season_id"]))
    season.state, season.closed_at = SeasonState.CLOSED, now
    session.flush()  # season 1 closes before season 2 becomes the active one
    session.add(
        Season(
            league_id=season.league_id,
            number=2,
            state=SeasonState.ACTIVE,
            placement_points=season.placement_points,
            started_at=now,
            created_at=now,
        )
    )
    session.flush()

    status, body = set_final(drawn["id"], "bo3")

    assert (status, body) == (409, {"code": "season_closed", "detail": {}})


# ---------------------------------------------------------------- places


def test_br102_br103_the_places_of_a_knockout_after_a_round_robin(
    played_group: Callable[..., Json],
    start_knockout: Callable[..., tuple[int, Json]],
    read: Callable[[str, str], Json],
    put_result: Callable[[str, str, Json], tuple[int, Json]],
) -> None:
    tournament = played_group(6)
    _, drawn = start_knockout(tournament, qualifiers=4, third_place_match=False)
    bracket = bracket_matches(read(drawn["id"], "/bracket"))
    for position in (1, 2):  # 1 v 4 and 2 v 3: the better seeds win
        put_result(
            drawn["id"], bracket[1, "standard", position]["match_id"], win("side_1")
        )
    final = bracket[2, "standard", 1]["match_id"]
    put_result(drawn["id"], final, win("side_2", (10, 8)))

    places = read(drawn["id"], "/places")

    main_seed = {
        tuple(e["player_ids"]): e["seed"]
        for e in drawn["entries"]
        if e["stage"] == "main"
    }
    players_of = {e["id"]: tuple(e["player_ids"]) for e in drawn["entries"]}
    rows = [
        (
            row["place"],
            main_seed[players_of[row["entry_id"]]],
            row["reason"]["kind"],
            row["points_per_player"],
        )
        for row in places["rows"]
    ]
    assert places["complete"] is True
    assert rows == [
        (1, 2, "won_final", 10),
        (2, 1, "lost_final", 8),
        (3, 3, "lost_in_round", 5),
        (3, 4, "lost_in_round", 5),
        (5, 5, "group_place", 2),
        (6, 6, "group_place", 0),
    ]
    winner = places["rows"][0]["reason"]
    assert winner["round"] == "final"
    assert winner["score"] == [10, 8]
    assert winner["group_place"] == 2
    assert places["rows"][2]["reason"]["round"] == "semifinal"


def test_br102_the_third_place_match_decides_3rd_and_4th(
    drawn: Json,
    read: Callable[[str, str], Json],
    put_result: Callable[[str, str, Json], tuple[int, Json]],
) -> None:
    _play_out(drawn, read, put_result)

    places = read(drawn["id"], "/places")

    kinds = [(row["place"], row["reason"]["kind"]) for row in places["rows"]]
    assert kinds == [
        (1, "won_final"),
        (2, "lost_final"),
        (3, "won_third_place"),
        (4, "lost_third_place"),
        (5, "lost_in_round"),
        (5, "lost_in_round"),
    ]


# ---------------------------------------------------------------- delete


def test_fr046_deleting_the_knockout_unlocks_the_group_phase(
    drawn: Json,
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    read: Callable[[str, str], Json],
    put_result: Callable[[str, str, Json], tuple[int, Json]],
) -> None:
    _play_out(drawn, read, put_result)
    phase_id = knockout_of(drawn)["id"]

    deleted = client.delete(
        _t_url(league_id, drawn["id"], f"/phases/{phase_id}"), headers=headers
    )
    again = client.delete(
        _t_url(league_id, drawn["id"], f"/phases/{phase_id}"), headers=headers
    )

    after = read(drawn["id"], "")
    assert deleted.status_code == 204
    assert again.status_code == 404
    assert again.json() == {"code": "phase_not_found", "detail": {}}
    assert after["state"] == "in_progress"
    assert [p["kind"] for p in after["phases"]] == ["group"]
    assert after["current_phase_id"] == group_of(after)["id"]
    assert after["current_phase_done"] is True
    assert all(e["stage"] == "main" for e in after["entries"])
    assert all(f["match_id"] is None for f in after["fields"])
    match = matches_of(after, group_of(after))[0]
    assert put_result(drawn["id"], match["id"], EMPTY)[0] == 200


def test_fr046_the_group_phase_itself_is_not_deleted_here(
    drawn: Json, client: TestClient, league_id: UUID, headers: dict[str, str]
) -> None:
    group_id = group_of(drawn)["id"]

    response = client.delete(
        _t_url(league_id, drawn["id"], f"/phases/{group_id}"), headers=headers
    )

    assert response.status_code == 422
    assert response.json() == {
        "code": "phase_not_deletable",
        "detail": {"kind": "group"},
    }


def test_fr046_a_new_knockout_can_be_drawn_after_deleting_one(
    drawn: Json,
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    read: Callable[[str, str], Json],
    start_knockout: Callable[..., tuple[int, Json]],
) -> None:
    client.delete(
        _t_url(league_id, drawn["id"], f"/phases/{knockout_of(drawn)['id']}"),
        headers=headers,
    )

    status, again = start_knockout(
        read(drawn["id"], ""), qualifiers=2, third_place_match=False
    )

    assert status == 200
    assert len([e for e in again["entries"] if e["stage"] == "knockout"]) == 2


# ---------------------------------------------------------------- the bracket


def test_d4_the_bracket_numbers_its_matches_after_the_group_phase(
    drawn: Json, read: Callable[[str, str], Json]
) -> None:
    bracket = read(drawn["id"], "/bracket")
    matches = bracket_matches(bracket)

    assert (bracket["size"], bracket["third_place_match"]) == (8, True)
    assert bracket["has_group_phase"] is True
    assert [r["name"] for r in bracket["rounds"]] == [
        "quarterfinal",
        "semifinal",
        "final",
    ]
    assert matches[1, "standard", 1]["state"] == "bye"
    assert matches[1, "standard", 1]["number"] is None
    assert matches[1, "standard", 2]["number"] == 16  # after 15 group matches
    assert matches[1, "standard", 4]["number"] == 17
    assert matches[1, "standard", 2]["next_number"] == 18
    assert [matches[3, k, 1]["number"] for k in ("standard", "third_place")] == [20, 21]
    assert matches[2, "standard", 1]["state"] == "waiting"
    assert [s["seed"] for s in matches[2, "standard", 1]["sides"]] == [1, None]
    assert matches[1, "standard", 2]["field_number"] == 1
    assert matches[1, "standard", 2]["state"] == "on_field"


def test_d4_a_tournament_without_a_knockout_has_no_bracket(
    played_group: Callable[..., Json],
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
) -> None:
    tournament = played_group(4)

    response = client.get(
        _t_url(league_id, tournament["id"], "/bracket"), headers=headers
    )

    assert response.status_code == 404
    assert response.json() == {"code": "knockout_not_found", "detail": {}}


@pytest.mark.parametrize(
    ("method", "rest", "body"),
    [
        ("get", "/bracket", None),
        ("get", "/knockout/preview?qualifiers=2&third_place_match=false", None),
        ("put", "/knockout", "start"),
        ("put", "/knockout/final-format", "final"),
        ("delete", "/phases/{phase}", None),
    ],
)
def test_api1_another_organizers_knockout_is_not_found(
    drawn: Json,
    client: TestClient,
    league_id: UUID,
    make_league: Callable[..., League],
    auth_header: Callable[..., dict[str, str]],
    method: str,
    rest: str,
    body: str | None,
) -> None:
    other = make_league()
    url = _t_url(league_id, drawn["id"], rest.format(phase=knockout_of(drawn)["id"]))
    payloads: dict[str | None, Json | None] = {
        None: None,
        "start": {
            "expected_current_phase_id": drawn["current_phase_id"],
            "expected_draw_counter": 0,
            "expected_qualifier_ids": [],
            "qualifiers": 2,
            "third_place_match": False,
            "match_format": None,
            "final_match_format": None,
            "mode": None,
        },
        "final": {"final_match_format": "bo3"},
    }

    response = client.request(
        method,
        url,
        json=payloads[body],
        headers=auth_header(other.owner_user_id),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "league_not_found"


# ---------------------------------------------------------------- the share link


PUBLIC_BRACKET = {
    "phase_id",
    "size",
    "third_place_match",
    "has_group_phase",
    "match_format",
    "final_match_format",
    "rounds",
}
PUBLIC_ROUND = {"round_no", "name", "matches"}
PUBLIC_MATCH = {
    "match_id",
    "number",
    "round_no",
    "position",
    "kind",
    "state",
    "sides",
    "outcome",
    "is_walkover",
    "score",
    "match_format",
    "field_number",
    "next_number",
}
PUBLIC_SIDE = {"entry_id", "seed", "is_bye", "decided_by_lot"}


def test_fr070_the_share_link_shows_the_bracket_and_nothing_more(
    drawn: Json, client: TestClient, token: str
) -> None:
    response = client.get(_public(token, drawn["id"], "/bracket"))

    bracket = response.json()
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert set(bracket) == PUBLIC_BRACKET
    for round_ in bracket["rounds"]:
        assert set(round_) == PUBLIC_ROUND
        for match in round_["matches"]:
            assert set(match) == PUBLIC_MATCH
            assert all(set(side) == PUBLIC_SIDE for side in match["sides"])


def test_fr070_a_public_bracket_needs_a_knockout_and_a_known_token(
    played_group: Callable[..., Json], client: TestClient, token: str
) -> None:
    tournament = played_group(2)

    none = client.get(_public(token, tournament["id"], "/bracket"))
    unknown = client.get(_public("nope", tournament["id"], "/bracket"))

    assert none.status_code == 404
    assert none.json() == {"code": "knockout_not_found", "detail": {}}
    assert unknown.json() == {"code": "share_link_not_found", "detail": {}}
    assert unknown.headers["cache-control"] == "no-store"


def test_fr070_the_bracket_of_another_leagues_tournament_is_not_found(
    drawn: Json,
    client: TestClient,
    make_league: Callable[..., League],
) -> None:
    other = make_league()

    foreign = client.get(_public(other.share_token, drawn["id"], "/bracket"))
    unknown = client.get(_public(other.share_token, str(uuid7()), "/bracket"))

    assert foreign.status_code == 404
    assert foreign.json() == {"code": "tournament_not_found", "detail": {}}
    assert foreign.json() == unknown.json()
    assert foreign.headers["cache-control"] == "no-store"


def test_fr070_a_tournament_in_setup_has_no_public_bracket(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    token: str,
) -> None:
    body = {"id": str(uuid7()), **ROUND_ROBIN}
    created = client.post(_url(league_id, "/tournaments"), json=body, headers=headers)

    response = client.get(_public(token, created.json()["tournament_id"], "/bracket"))

    assert response.status_code == 404
    assert response.json() == {"code": "tournament_not_found", "detail": {}}


# ---------------------------------------------------------------- races


def _commit_knockout(
    engine: Engine, now: datetime, *, player_count: int, third_place: bool
) -> tuple[UUID, UUID, UUID]:
    """Commit a round robin played out and its knockout; return owner, league, id."""
    with Session(engine) as setup:
        owner = User(
            email=f"{uuid7()}@example.com",
            display_name="Race",
            password_hash="!",
            language=Language.EN,
            created_at=now,
        )
        setup.add(owner)
        setup.flush()
        league = league_service.create_league(
            setup, league_id=uuid7(), owner_user_id=owner.id, name="Race", now=now
        )
        player_ids = [
            player_service.add_player(
                setup,
                league_id=league.id,
                user_id=owner.id,
                name=f"P{n}",
                clock=lambda: now,
            ).id
            for n in range(player_count)
        ]
        tournament_id = uuid7()
        tournament_service.create_tournament(
            setup,
            league_id=league.id,
            user_id=owner.id,
            tournament_id=tournament_id,
            request=tournament_service.FormatRequest(
                name="Race",
                date=now.date(),
                type=TournamentType.SINGLES,
                group_phase=GroupPhase.ROUND_ROBIN,
                field_count=2,
            ),
            clock=lambda: now,
        )
        tournament_service.set_tournament_players(
            setup,
            league_id=league.id,
            tournament_id=tournament_id,
            user_id=owner.id,
            player_ids=player_ids,
            clock=lambda: now,
        )
        seeded = tournament_service.set_seeding_method(
            setup,
            league_id=league.id,
            tournament_id=tournament_id,
            user_id=owner.id,
            method=SeedingMethod.RANDOM,
            clock=lambda: now,
        )
        started = tournament_service.start_tournament(
            setup,
            league_id=league.id,
            tournament_id=tournament_id,
            user_id=owner.id,
            expected_draw_counter=seeded.draw_counter,
            expected_seed_order=[
                e.id for e in sorted(seeded.entries, key=lambda e: e.seed or 0)
            ],
            clock=lambda: now,
        )
        ids = (owner.id, league.id, tournament_id)
        for round_ in started.rounds:
            for match in round_.matches:
                _enter(setup, ids, match.id, _WIN, now)
        knockout_service.start_knockout(
            setup,
            league_id=league.id,
            tournament_id=tournament_id,
            user_id=owner.id,
            start=knockout_service.KnockoutStart(
                expected_current_phase_id=started.phases[0].id,
                expected_draw_counter=seeded.draw_counter,
                expected_qualifier_ids=_previewed(
                    setup, ids, qualifiers=player_count, third_place=third_place
                ),
                qualifiers=player_count,
                third_place_match=third_place,
                match_format=None,
                final_match_format=None,
            ),
            clock=lambda: now,
        )
        setup.commit()
        return ids


def _previewed(
    session: Session,
    ids: tuple[UUID, UUID, UUID],
    *,
    qualifiers: int,
    third_place: bool,
) -> tuple[UUID, ...]:
    """The group-phase entries the preview shows going through, by seed."""
    owner_id, league_id, tournament_id = ids
    preview = knockout_service.preview_knockout(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=owner_id,
        qualifiers=qualifiers,
        third_place_match=third_place,
    )
    return tuple(entry.members[0].entry_id for entry in preview.entries)


_WIN = tournament_service.MatchResult(
    walkover_winner=None, games=(Game(winner=Outcome.SIDE_1, score_1=10, score_2=7),)
)
_WIN_2 = tournament_service.MatchResult(
    walkover_winner=None, games=(Game(winner=Outcome.SIDE_2, score_1=7, score_2=10),)
)


def _enter(
    session: Session,
    ids: tuple[UUID, UUID, UUID],
    match_id: UUID,
    result: tournament_service.MatchResult,
    now: datetime,
) -> None:
    owner_id, league_id, tournament_id = ids
    try:
        shown = knockout_service.read_bracket(
            session, league_id=league_id, tournament_id=tournament_id, user_id=owner_id
        )
    except NotFoundError:  # a group-phase result: its sides are stored
        shown = None
    sides = next(
        (
            (m.sides[0].entry_id, m.sides[1].entry_id)
            for r in (() if shown is None else shown.rounds)
            for m in r.matches
            if m.match_id == match_id
        ),
        None,
    )
    if sides is not None and sides[0] is not None and sides[1] is not None:
        result = replace(result, expected_sides=(sides[0], sides[1]))
    tournament_service.set_match_result(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        match_id=match_id,
        user_id=owner_id,
        result=result,
        clock=lambda: now,
    )


def _bracket(
    engine: Engine, ids: tuple[UUID, UUID, UUID]
) -> dict[tuple[int, str, int], knockout_service.BracketMatchView]:
    owner_id, league_id, tournament_id = ids
    with Session(engine) as check:
        bracket = knockout_service.read_bracket(
            check, league_id=league_id, tournament_id=tournament_id, user_id=owner_id
        )
    return {
        (m.round_no, m.kind.value, m.position): m
        for round_ in bracket.rounds
        for m in round_.matches
    }


def _draw_counter(engine: Engine, ids: tuple[UUID, UUID, UUID]) -> int:
    """The stored draw counter, which the knockout start must name (ADR-008)."""
    with Session(engine) as check:
        return (
            check.scalar(select(Tournament.draw_counter).where(Tournament.id == ids[2]))
            or 0
        )


def _back_to_the_group_phase(
    engine: Engine, now: datetime, ids: tuple[UUID, UUID, UUID]
) -> tuple[UUID, UUID, tuple[UUID, ...]]:
    """Delete the committed knockout; return the group phase, a match and the preview."""
    owner_id, league_id, tournament_id = ids
    with Session(engine) as undo:
        phase = undo.scalars(
            select(TournamentPhase).where(
                TournamentPhase.tournament_id == tournament_id,
                TournamentPhase.position == 2,
            )
        ).one()
        knockout_service.delete_knockout(
            undo,
            league_id=league_id,
            tournament_id=tournament_id,
            phase_id=phase.id,
            user_id=owner_id,
            clock=lambda: now,
        )
        undo.commit()
    with Session(engine) as check:
        view = tournament_service.read_tournament(
            check, league_id=league_id, tournament_id=tournament_id, user_id=owner_id
        )
        previewed = _previewed(check, ids, qualifiers=2, third_place=False)
    return view.phases[0].id, view.rounds[0].matches[0].id, previewed


def _race(
    settings: Settings,
    engine: Engine,
    wait: Callable[[], None],
    first: Callable[[Session], object],
    second: Callable[[TestClient], tuple[int, Json]],
) -> tuple[int, Json]:
    """Run `first` and hold its locks while `second` waits for them; then commit."""
    outcome: list[tuple[int, Json]] = []
    with Session(engine) as session, TestClient(create_app(settings)) as client:
        first(session)
        thread = threading.Thread(target=lambda: outcome.append(second(client)))
        thread.start()
        wait()
        session.commit()
        thread.join()
    (result,) = outcome
    return result


@pytest.mark.concurrency
@pytest.mark.parametrize(
    "start_first", [True, False], ids=["start-first", "result-first"]
)
def test_br053_a_result_racing_the_knockout_start(
    committing_settings: Settings,
    committing_engine: Engine,
    now: datetime,
    committed_auth_header: Callable[..., dict[str, str]],
    wait_for_a_lock_wait: Callable[[], None],
    *,
    start_first: bool,
) -> None:
    ids = _commit_knockout(committing_engine, now, player_count=4, third_place=False)
    owner_id, league_id, tournament_id = ids
    group_id, match_id, previewed = _back_to_the_group_phase(
        committing_engine, now, ids
    )
    draw_counter = _draw_counter(committing_engine, ids)
    start = knockout_service.KnockoutStart(
        expected_current_phase_id=group_id,
        expected_draw_counter=draw_counter,
        expected_qualifier_ids=previewed,
        qualifiers=2,
        third_place_match=False,
        match_format=None,
        final_match_format=None,
    )
    headers = committed_auth_header(owner_id, issued_at=datetime.now(UTC))

    def put_result(client: TestClient) -> tuple[int, Json]:
        response = client.put(
            _t_url(league_id, str(tournament_id), f"/matches/{match_id}/result"),
            json=win("side_2"),
            headers=headers,
        )
        return response.status_code, response.json()

    def put_start(client: TestClient) -> tuple[int, Json]:
        response = client.put(
            _t_url(league_id, str(tournament_id), "/knockout"),
            json={
                "expected_current_phase_id": str(group_id),
                "expected_draw_counter": draw_counter,
                "expected_qualifier_ids": [str(i) for i in previewed],
                "qualifiers": 2,
                "third_place_match": False,
                "match_format": None,
                "final_match_format": None,
                "mode": None,
            },
            headers=headers,
        )
        return response.status_code, response.json()

    if start_first:
        status, body = _race(
            committing_settings,
            committing_engine,
            wait_for_a_lock_wait,
            lambda s: knockout_service.start_knockout(
                s,
                league_id=league_id,
                tournament_id=tournament_id,
                user_id=owner_id,
                start=start,
                clock=lambda: now,
            ),
            put_result,
        )
        # The result waited for the start, then found the round robin locked.
        assert (status, body["code"]) == (422, "group_phase_locked")
    else:
        status, body = _race(
            committing_settings,
            committing_engine,
            wait_for_a_lock_wait,
            lambda s: _enter(s, ids, match_id, _WIN_2, now),
            put_start,
        )
        # The start waited for the result; the standings after it seed the
        # entries otherwise than the preview did, so nothing is drawn (ADR-008).
        with Session(committing_engine) as check:
            current = _previewed(check, ids, qualifiers=2, third_place=False)
        assert current != previewed
        assert (status, body["code"]) == (409, "qualifiers_changed")
        assert body["detail"] == {"entry_ids": [str(i) for i in current]}


@pytest.mark.concurrency
def test_fr045_two_starts_at_once_draw_one_knockout(
    committing_settings: Settings,
    committing_engine: Engine,
    now: datetime,
    committed_auth_header: Callable[..., dict[str, str]],
    wait_for_a_lock_wait: Callable[[], None],
) -> None:
    ids = _commit_knockout(committing_engine, now, player_count=4, third_place=False)
    owner_id, league_id, tournament_id = ids
    group_id, _, previewed = _back_to_the_group_phase(committing_engine, now, ids)
    draw_counter = _draw_counter(committing_engine, ids)
    start = knockout_service.KnockoutStart(
        expected_current_phase_id=group_id,
        expected_draw_counter=draw_counter,
        expected_qualifier_ids=previewed,
        qualifiers=2,
        third_place_match=False,
        match_format=None,
        final_match_format=None,
    )
    headers = committed_auth_header(owner_id, issued_at=datetime.now(UTC))

    def put_start(client: TestClient) -> tuple[int, Json]:
        response = client.put(
            _t_url(league_id, str(tournament_id), "/knockout"),
            json={
                "expected_current_phase_id": str(group_id),
                "expected_draw_counter": draw_counter,
                "expected_qualifier_ids": [str(i) for i in previewed],
                "qualifiers": 2,
                "third_place_match": False,
                "match_format": None,
                "final_match_format": None,
                "mode": None,
            },
            headers=headers,
        )
        return response.status_code, response.json()

    status, body = _race(
        committing_settings,
        committing_engine,
        wait_for_a_lock_wait,
        lambda s: knockout_service.start_knockout(
            s,
            league_id=league_id,
            tournament_id=tournament_id,
            user_id=owner_id,
            start=start,
            clock=lambda: now,
        ),
        put_start,
    )

    # The second start waited, then found the knockout and drew nothing (ADR-008).
    assert status == 409
    assert body["code"] == "current_phase_changed"
    with Session(committing_engine) as check:
        phases = check.scalars(
            select(TournamentPhase).where(
                TournamentPhase.tournament_id == tournament_id
            )
        ).all()
        knockout_entries = check.scalar(
            select(func.count())
            .select_from(Entry)
            .where(Entry.tournament_id == tournament_id, Entry.stage == "knockout")
        )
    knockout = next(p for p in phases if p.position == 2)
    assert body["detail"] == {"current_phase_id": str(knockout.id)}
    assert len(phases) == 2
    assert knockout_entries == 2


@pytest.mark.concurrency
def test_d4_two_results_of_one_round_at_once_fill_the_next_match(
    committing_settings: Settings,
    committing_engine: Engine,
    now: datetime,
    committed_auth_header: Callable[..., dict[str, str]],
    wait_for_a_lock_wait: Callable[[], None],
) -> None:
    ids = _commit_knockout(committing_engine, now, player_count=4, third_place=False)
    owner_id, league_id, tournament_id = ids
    bracket = _bracket(committing_engine, ids)
    one, two = bracket[1, "standard", 1].match_id, bracket[1, "standard", 2].match_id

    def second(client: TestClient) -> tuple[int, Json]:
        response = client.put(
            _t_url(league_id, str(tournament_id), f"/matches/{two}/result"),
            json=win("side_1"),
            headers=committed_auth_header(owner_id, issued_at=datetime.now(UTC)),
        )
        return response.status_code, response.json()

    status, _ = _race(
        committing_settings,
        committing_engine,
        wait_for_a_lock_wait,
        lambda s: _enter(s, ids, one, _WIN, now),
        second,
    )

    after = _bracket(committing_engine, ids)
    final = after[2, "standard", 1]
    assert status == 200
    assert [side.seed for side in final.sides] == [1, 2]
    assert final.state == "on_field"


@pytest.mark.concurrency
@pytest.mark.parametrize(
    "delete_first", [True, False], ids=["delete-first", "result-first"]
)
def test_fr046_a_result_racing_the_knockout_delete(
    committing_settings: Settings,
    committing_engine: Engine,
    now: datetime,
    committed_auth_header: Callable[..., dict[str, str]],
    wait_for_a_lock_wait: Callable[[], None],
    *,
    delete_first: bool,
) -> None:
    ids = _commit_knockout(committing_engine, now, player_count=4, third_place=False)
    owner_id, league_id, tournament_id = ids
    bracket = _bracket(committing_engine, ids)
    match_id = bracket[1, "standard", 1].match_id
    with Session(committing_engine) as check:
        phase_id = check.scalars(
            select(TournamentPhase.id).where(
                TournamentPhase.tournament_id == tournament_id,
                TournamentPhase.position == 2,
            )
        ).one()
    headers = committed_auth_header(owner_id, issued_at=datetime.now(UTC))

    def delete(session: Session) -> None:
        knockout_service.delete_knockout(
            session,
            league_id=league_id,
            tournament_id=tournament_id,
            phase_id=phase_id,
            user_id=owner_id,
            clock=lambda: now,
        )

    if delete_first:

        def result(client: TestClient) -> tuple[int, Json]:
            response = client.put(
                _t_url(league_id, str(tournament_id), f"/matches/{match_id}/result"),
                json=win("side_1"),
                headers=headers,
            )
            return response.status_code, response.json()

        status, body = _race(
            committing_settings, committing_engine, wait_for_a_lock_wait, delete, result
        )
        assert (status, body["code"]) == (404, "match_not_found")
    else:

        def delete_request(client: TestClient) -> tuple[int, Json]:
            response = client.delete(
                _t_url(league_id, str(tournament_id), f"/phases/{phase_id}"),
                headers=headers,
            )
            return response.status_code, {}

        status, _ = _race(
            committing_settings,
            committing_engine,
            wait_for_a_lock_wait,
            lambda s: _enter(s, ids, match_id, _WIN, now),
            delete_request,
        )
        assert status == 204
    with Session(committing_engine) as check:
        knockout_entries = check.scalar(
            select(func.count())
            .select_from(Entry)
            .where(Entry.tournament_id == tournament_id, Entry.stage == "knockout")
        )
    assert knockout_entries == 0


@pytest.mark.concurrency
@pytest.mark.parametrize(
    "final_first", [True, False], ids=["final-first", "semi-first"]
)
def test_br094_a_final_result_racing_a_semifinal_edit(
    committing_settings: Settings,
    committing_engine: Engine,
    now: datetime,
    committed_auth_header: Callable[..., dict[str, str]],
    wait_for_a_lock_wait: Callable[[], None],
    *,
    final_first: bool,
) -> None:
    ids = _commit_knockout(committing_engine, now, player_count=4, third_place=False)
    owner_id, league_id, tournament_id = ids
    bracket = _bracket(committing_engine, ids)
    semi, other = bracket[1, "standard", 1].match_id, bracket[1, "standard", 2].match_id
    final = bracket[2, "standard", 1].match_id
    with Session(committing_engine) as setup:
        _enter(setup, ids, semi, _WIN, now)
        _enter(setup, ids, other, _WIN, now)
        setup.commit()
    headers = committed_auth_header(owner_id, issued_at=datetime.now(UTC))

    def request(match_id: UUID, body: Json) -> Callable[[TestClient], tuple[int, Json]]:
        def send(client: TestClient) -> tuple[int, Json]:
            response = client.put(
                _t_url(league_id, str(tournament_id), f"/matches/{match_id}/result"),
                json=body,
                headers=headers,
            )
            return response.status_code, response.json()

        return send

    if final_first:
        status, body = _race(
            committing_settings,
            committing_engine,
            wait_for_a_lock_wait,
            lambda s: _enter(s, ids, final, _WIN, now),
            request(semi, win("side_2")),
        )
        assert status == 422
        assert body == {"code": "result_locked", "detail": {"match_ids": [str(final)]}}
        assert _bracket(committing_engine, ids)[2, "standard", 1].sides[0].seed == 1
    else:
        shown = _bracket(committing_engine, ids)[2, "standard", 1]
        seen = [str(side.entry_id) for side in shown.sides]
        status, body = _race(
            committing_settings,
            committing_engine,
            wait_for_a_lock_wait,
            lambda s: _enter(s, ids, semi, _WIN_2, now),
            request(final, {**win("side_1"), "expected_sides": seen}),
        )
        # The final waited for the edit and found other pairs than the screen's:
        # "side 1 wins" would have meant another entry (ADR-008).
        after = _bracket(committing_engine, ids)[2, "standard", 1]
        assert (status, body["code"]) == (409, "match_sides_changed")
        assert body["detail"]["entry_ids"] == [
            str(side.entry_id) for side in after.sides
        ]
        assert (
            body["detail"]["entry_ids"][1] == seen[1] != body["detail"]["entry_ids"][0]
        )
        assert after.sides[0].seed == 4
        assert after.outcome is None
    with Session(committing_engine) as check:
        state = tournament_service.read_tournament(
            check, league_id=league_id, tournament_id=tournament_id, user_id=owner_id
        ).state
    assert state.value == ("finished" if final_first else "in_progress")
