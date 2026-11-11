"""A knockout without a group phase (FR-031, FR-032, FR-035 to FR-037, BR-040
to BR-044, BR-094, BR-102, BR-110, BR-112, FR-070).
"""

import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid7

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from tourneyhub.app import create_app
from tourneyhub.db.models.accounts import User
from tourneyhub.db.models.leagues import League, Player
from tourneyhub.db.models.matches import Match, Round
from tourneyhub.db.models.tournaments import Tournament
from tourneyhub.engine.accounts import Language
from tourneyhub.engine.tournaments import (
    GroupPhase,
    KnockoutMatchFormat,
    SeedingMethod,
    TournamentType,
)
from tourneyhub.services import leagues as league_service
from tourneyhub.services import players as player_service
from tourneyhub.services import tournaments as tournament_service
from tourneyhub.settings import Settings

type Json = dict[str, Any]
type Key = tuple[int, str, int]

KNOCKOUT: Json = {
    "name": "Thursday",
    "date": "2026-11-12",
    "type": "singles",
    "group_phase": "none",
    "round_robin_legs": None,
    "sit_out_points": None,
    "group_match_format": None,
    "knockout_match_format": "bo1",
    "final_match_format": None,
    "third_place_match": False,
    "goals_per_game": 10,
    "field_count": 2,
}


def win(side: str, score: tuple[int, int] = (10, 5)) -> Json:
    winner, loser = score
    scores = (winner, loser) if side == "side_1" else (loser, winner)
    return {
        "walkover_winner": None,
        "games": [{"winner": side, "score_1": scores[0], "score_2": scores[1]}],
    }


def _url(league_id: UUID, rest: str = "") -> str:
    return f"/api/v1/leagues/{league_id}{rest}"


def _t_url(league_id: UUID, tournament_id: str, rest: str = "") -> str:
    return _url(league_id, f"/tournaments/{tournament_id}{rest}")


def _public(token: str, tournament_id: str, rest: str = "") -> str:
    return f"/api/v1/public/{token}/tournaments/{tournament_id}{rest}"


def by_key(bracket: Json) -> dict[Key, Json]:
    return {
        (m["round_no"], m["kind"], m["position"]): m
        for round_ in bracket["rounds"]
        for m in round_["matches"]
    }


def seeds(match: Json) -> list[int | None]:
    return [side["seed"] for side in match["sides"]]


@pytest.fixture
def league(make_league: Callable[..., League]) -> League:
    return make_league()


@pytest.fixture
def league_id(league: League) -> UUID:
    return league.id


@pytest.fixture
def headers(
    league: League, auth_header: Callable[..., dict[str, str]]
) -> dict[str, str]:
    return auth_header(league.owner_user_id)


@pytest.fixture
def players(league: League, make_player: Callable[..., Player]) -> list[str]:
    return [str(make_player(league=league, name=f"P{n:02}").id) for n in range(1, 13)]


@pytest.fixture
def read(
    client: TestClient, league_id: UUID, headers: dict[str, str]
) -> Callable[..., Json]:
    def read(tournament_id: str, rest: str = "") -> Json:
        response = client.get(_t_url(league_id, tournament_id, rest), headers=headers)
        assert response.status_code == 200, response.text
        result: Json = response.json()
        return result

    return read


@pytest.fixture
def set_up(
    client: TestClient, league_id: UUID, headers: dict[str, str], players: list[str]
) -> Callable[..., Json]:
    """A knockout-only tournament in setup with `count` players picked; its setup."""

    def set_up(count: int, **values: object) -> Json:
        body = {"id": str(uuid7()), **KNOCKOUT, **values}
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
        setup: Json = picked.json()
        if body["type"] == "doubles":
            paired = client.put(
                _t_url(league_id, tournament_id, "/setup/pairs"),
                json={"pairs": [players[n : n + 2] for n in range(0, count - 1, 2)]},
                headers=headers,
            )
            assert paired.status_code == 200, paired.text
            setup = paired.json()
        return setup

    return set_up


@pytest.fixture
def start(
    client: TestClient, league_id: UUID, headers: dict[str, str]
) -> Callable[[Json], tuple[int, Json]]:
    def start(setup: Json) -> tuple[int, Json]:
        response = client.post(
            _t_url(league_id, setup["tournament_id"], "/start"),
            json={"expected_draw_counter": setup["draw_counter"]},
            headers=headers,
        )
        result: Json = response.json()
        return response.status_code, result

    return start


@pytest.fixture
def started(
    set_up: Callable[..., Json], start: Callable[[Json], tuple[int, Json]]
) -> Callable[..., Json]:
    def started(count: int = 6, **values: object) -> Json:
        status, tournament = start(set_up(count, **values))
        assert status == 200, tournament
        return tournament

    return started


@pytest.fixture
def put_result(
    client: TestClient, league_id: UUID, headers: dict[str, str]
) -> Callable[..., tuple[int, Json]]:
    def put_result(
        tournament_id: str, match: Json, body: Json, *, name_sides: bool = True
    ) -> tuple[int, Json]:
        """Send a result for a bracket match, naming the sides the bracket showed."""
        sides = [side["entry_id"] for side in match["sides"]]
        if name_sides and None not in sides:
            body = {**body, "expected_sides": sides}
        response = client.put(
            _t_url(league_id, tournament_id, f"/matches/{match['match_id']}/result"),
            json=body,
            headers=headers,
        )
        result: Json = response.json()
        return response.status_code, result

    return put_result


@pytest.fixture
def play_out(
    read: Callable[..., Json], put_result: Callable[..., tuple[int, Json]]
) -> Callable[[Json], dict[Key, Json]]:
    """Play every match in schedule order, the better seed winning (BR-043)."""

    def play_out(tournament: Json) -> dict[Key, Json]:
        while True:
            bracket = by_key(read(tournament["id"], "/bracket"))
            ready = [m for m in bracket.values() if m["state"] in {"ready", "on_field"}]
            if not ready:
                return bracket
            match = min(ready, key=lambda m: m["number"])
            one, two = seeds(match)
            assert one is not None
            assert two is not None
            status, body = put_result(
                tournament["id"], match, win("side_1" if one < two else "side_2")
            )
            assert status == 200, body

    return play_out


# ---------------------------------------------------------------- start


def test_fr031_a_knockout_without_a_group_phase_starts_from_the_setup_seeds(
    started: Callable[..., Json], read: Callable[..., Json]
) -> None:
    tournament = started(6)

    bracket = read(tournament["id"], "/bracket")

    assert tournament["state"] == "in_progress"
    assert [(p["kind"], p["position"]) for p in tournament["phases"]] == [
        ("knockout", 1)
    ]
    assert tournament["current_phase_id"] == tournament["phases"][0]["id"]
    assert bracket["size"] == 8
    assert bracket["has_group_phase"] is False
    assert [r["name"] for r in bracket["rounds"]] == [
        "quarterfinal",
        "semifinal",
        "final",
    ]
    first = [seeds(m) for m in bracket["rounds"][0]["matches"]]
    # BR-041 and BR-042: byes for seeds 1 and 2, who can meet only in the final
    assert first == [[1, None], [4, 5], [2, None], [3, 6]]
    numbers = [m["number"] for r in bracket["rounds"] for m in r["matches"]]
    assert numbers == [None, 1, None, 2, 3, 4, 5]
    setup_seed = {e["id"]: e["seed"] for e in tournament["entries"]}
    sides = [s for m in bracket["rounds"][0]["matches"] for s in m["sides"]]
    assert all(s["seed"] == setup_seed[s["entry_id"]] for s in sides if s["entry_id"])


@pytest.mark.parametrize(
    ("tournament_type", "count", "entries"),
    [
        pytest.param("singles", 5, 5, id="singles"),
        pytest.param("doubles", 10, 5, id="doubles"),
        pytest.param("dyp", 12, 6, id="dyp"),
    ],
)
def test_br040_every_type_but_monster_dyp_plays_a_knockout_from_the_start(
    started: Callable[..., Json],
    read: Callable[..., Json],
    tournament_type: str,
    count: int,
    entries: int,
) -> None:
    tournament = started(count, type=tournament_type)

    bracket = read(tournament["id"], "/bracket")

    first = bracket["rounds"][0]["matches"]
    in_bracket = {s["entry_id"] for m in first for s in m["sides"] if s["entry_id"]}
    assert len(in_bracket) == entries
    assert in_bracket == {e["id"] for e in tournament["entries"]}
    assert all(e["stage"] == "main" for e in tournament["entries"])
    assert sum(s["is_bye"] for m in first for s in m["sides"]) == 8 - entries
    byes = sorted(m["sides"][0]["seed"] for m in first if m["sides"][1]["is_bye"])
    assert byes == list(range(1, 8 - entries + 1))  # BR-041: the top seeds


def test_d2_the_first_round_sides_list_their_players(
    started: Callable[..., Json], read: Callable[..., Json]
) -> None:
    tournament = started(12, type="dyp")

    players_of = {e["id"]: sorted(e["player_ids"]) for e in tournament["entries"]}
    first = next(r for r in tournament["rounds"] if r["round_no"] == 1)
    for match in first["matches"]:
        for side in match["sides"]:
            if side["entry_id"] is not None:
                assert sorted(side["player_ids"]) == players_of[side["entry_id"]]
    assert read(tournament["id"], "/bracket")["rounds"][0]["matches"]


def test_br130_the_first_matches_take_the_fields(
    started: Callable[..., Json], read: Callable[..., Json]
) -> None:
    tournament = started(6)

    bracket = by_key(read(tournament["id"], "/bracket"))

    assert bracket[1, "standard", 2]["field_number"] == 1
    assert bracket[1, "standard", 4]["field_number"] == 2
    assert bracket[1, "standard", 1]["state"] == "bye"
    assert bracket[2, "standard", 1]["state"] == "waiting"


def test_br120_the_phase_keeps_the_formats_of_setup(
    started: Callable[..., Json], read: Callable[..., Json]
) -> None:
    tournament = started(4, knockout_match_format="bo3", final_match_format="bo5")

    bracket = by_key(read(tournament["id"], "/bracket"))

    assert bracket[1, "standard", 1]["match_format"] == "bo3"
    assert bracket[2, "standard", 1]["match_format"] == "bo5"


# ---------------------------------------------------------------- FR-032


@pytest.mark.parametrize(
    ("count", "third_place_match", "starts"),
    [
        pytest.param(1, False, False, id="one-entry"),
        pytest.param(2, False, True, id="two-entries-play-the-final"),
        pytest.param(3, True, False, id="three-entries-with-third-place"),
        pytest.param(4, True, True, id="four-entries-with-third-place"),
    ],
)
def test_fr032_the_minimum_entries_of_a_knockout(
    set_up: Callable[..., Json],
    start: Callable[[Json], tuple[int, Json]],
    read: Callable[..., Json],
    count: int,
    third_place_match: bool,
    starts: bool,
) -> None:
    setup = set_up(count, third_place_match=third_place_match)

    preview = read(setup["tournament_id"], "/setup/preview")
    status, body = start(setup)

    minimum = 4 if third_place_match else 2
    if starts:
        assert status == 200, body
        assert preview["can_start"] is True
        kinds = [m["kind"] for r in body["rounds"] for m in r["matches"]]
        assert kinds.count("third_place") == int(third_place_match)
    else:
        refusal = {
            "code": "not_enough_entries",
            "detail": {"minimum": minimum, "given": count},
        }
        assert (status, body) == (422, refusal)
        assert preview["problem"] == refusal


def test_fr032_a_knockout_of_257_entries_is_refused(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    make_player: Callable[..., Player],
    start: Callable[[Json], tuple[int, Json]],
    session: Session,
) -> None:
    ids = [str(make_player(league=league, name=f"Q{n}").id) for n in range(257)]
    created = client.post(
        _url(league.id, "/tournaments"),
        json={"id": str(uuid7()), **KNOCKOUT},
        headers=headers,
    )
    setup = client.put(
        _t_url(league.id, created.json()["tournament_id"], "/setup/players"),
        json={"player_ids": ids},
        headers=headers,
    ).json()

    status, body = start(setup)

    assert (status, body) == (
        422,
        {"code": "too_many_entries_for_knockout", "detail": {"limit": 256}},
    )
    assert session.scalar(select(func.count()).select_from(Round)) == 0


def test_fr032_a_knockout_of_256_entries_starts(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    make_player: Callable[..., Player],
    start: Callable[[Json], tuple[int, Json]],
) -> None:
    ids = [str(make_player(league=league, name=f"Q{n}").id) for n in range(256)]
    created = client.post(
        _url(league.id, "/tournaments"),
        json={"id": str(uuid7()), **KNOCKOUT},
        headers=headers,
    )
    setup = client.put(
        _t_url(league.id, created.json()["tournament_id"], "/setup/players"),
        json={"player_ids": ids},
        headers=headers,
    ).json()

    status, body = start(setup)

    assert status == 200, body
    assert len(body["rounds"]) == 8
    assert sum(len(r["matches"]) for r in body["rounds"]) == 255


# ---------------------------------------------------------------- preview


@pytest.mark.parametrize("third_place_match", [False, True])
def test_fr035_the_preview_describes_the_bracket(
    set_up: Callable[..., Json],
    start: Callable[[Json], tuple[int, Json]],
    read: Callable[..., Json],
    third_place_match: bool,
) -> None:
    setup = set_up(6, third_place_match=third_place_match)
    players_of = {e["seed"]: e["player_ids"] for e in setup["entries"]}

    preview = read(setup["tournament_id"], "/setup/preview")
    _, tournament = start(setup)

    assert preview["can_start"] is True
    assert preview["bracket_size"] == 8
    assert preview["round_count"] == 3
    assert preview["match_count"] == 5 + int(third_place_match)
    [first] = preview["rounds"]
    assert first["round_no"] == 1
    assert first["sitting_out"] == []
    assert first["byes"] == [players_of[1], players_of[2]]  # BR-041
    assert [m["sides"] for m in first["matches"]] == [
        [players_of[4], players_of[5]],
        [players_of[3], players_of[6]],
    ]
    started = next(r for r in tournament["rounds"] if r["round_no"] == 1)
    assert [
        [s["player_ids"] for s in m["sides"]]
        for m in started["matches"]
        if not any(s["is_bye"] for s in m["sides"])
    ] == [m["sides"] for m in first["matches"]]


def test_fr035_a_round_robin_preview_has_no_byes(
    set_up: Callable[..., Json], read: Callable[..., Json]
) -> None:
    setup = set_up(
        4,
        group_phase="round_robin",
        round_robin_legs=1,
        group_match_format="bo1",
        knockout_match_format=None,
        third_place_match=None,
    )

    preview = read(setup["tournament_id"], "/setup/preview")

    assert all(r["byes"] == [] for r in preview["rounds"])
    assert preview["bracket_size"] is None


# ---------------------------------------------------------------- results


def test_fr037_the_final_finishes_the_tournament(
    started: Callable[..., Json],
    read: Callable[..., Json],
    play_out: Callable[[Json], dict[Key, Json]],
) -> None:
    tournament = started(6)

    bracket = play_out(tournament)

    assert read(tournament["id"])["state"] == "finished"
    assert bracket[3, "standard", 1]["state"] == "played"
    assert seeds(bracket[3, "standard", 1]) == [1, 2]


def test_fr037_with_a_third_place_match_both_last_matches_finish_it(
    started: Callable[..., Json],
    read: Callable[..., Json],
    put_result: Callable[..., tuple[int, Json]],
) -> None:
    tournament = started(4, third_place_match=True)
    bracket = by_key(read(tournament["id"], "/bracket"))
    for position in (1, 2):
        put_result(tournament["id"], bracket[1, "standard", position], win("side_1"))
    bracket = by_key(read(tournament["id"], "/bracket"))

    put_result(tournament["id"], bracket[2, "standard", 1], win("side_1"))
    after_final = read(tournament["id"])["state"]
    put_result(tournament["id"], bracket[2, "third_place", 1], win("side_2"))

    assert after_final == "in_progress"
    assert read(tournament["id"])["state"] == "finished"


def test_br094_a_derived_match_needs_the_sides_and_locks_its_feeders(
    started: Callable[..., Json],
    read: Callable[..., Json],
    put_result: Callable[..., tuple[int, Json]],
) -> None:
    tournament = started(6)
    bracket = by_key(read(tournament["id"], "/bracket"))
    quarter = bracket[1, "standard", 2]  # 4 v 5, feeds the semifinal of seed 1
    put_result(tournament["id"], quarter, win("side_1"))
    semifinal = by_key(read(tournament["id"], "/bracket"))[2, "standard", 1]

    unnamed = put_result(tournament["id"], semifinal, win("side_1"), name_sides=False)
    named = put_result(tournament["id"], semifinal, win("side_1"))
    locked = put_result(tournament["id"], quarter, win("side_2"))
    cleared = put_result(
        tournament["id"], semifinal, {"walkover_winner": None, "games": []}
    )
    changed = put_result(tournament["id"], quarter, win("side_2"))

    assert unnamed == (422, {"code": "expected_sides_required", "detail": {}})
    assert named[0] == 200
    assert locked == (
        422,
        {"code": "result_locked", "detail": {"match_ids": [semifinal["match_id"]]}},
    )
    assert cleared[0] == 200
    assert changed[0] == 200
    after = by_key(read(tournament["id"], "/bracket"))[2, "standard", 1]
    assert seeds(after) == [1, 5]  # the new winner takes the side (BR-094)


def test_br091_a_bye_takes_no_result(
    started: Callable[..., Json],
    read: Callable[..., Json],
    put_result: Callable[..., tuple[int, Json]],
) -> None:
    tournament = started(6)
    bye = by_key(read(tournament["id"], "/bracket"))[1, "standard", 1]

    assert put_result(tournament["id"], bye, win("side_1")) == (
        422,
        {"code": "match_sides_unknown", "detail": {}},
    )


def test_fr040_a_knockout_is_not_finished_by_hand(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    started: Callable[..., Json],
) -> None:
    tournament = started(4)

    response = client.post(
        _t_url(league_id, tournament["id"], "/finish"),
        json={"expected_state": "in_progress"},
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json() == {
        "code": "format_not_supported",
        "detail": {"format": "single_elimination"},
    }


# ---------------------------------------------------------------- places


def test_br102_the_places_come_from_the_knockout_alone(
    started: Callable[..., Json],
    read: Callable[..., Json],
    play_out: Callable[[Json], dict[Key, Json]],
) -> None:
    tournament = started(6)
    play_out(tournament)
    seed_of = {e["id"]: e["seed"] for e in tournament["entries"]}

    places = read(tournament["id"], "/places")

    rows = [
        (
            row["place"],
            seed_of[row["entry_id"]],
            row["reason"]["kind"],
            row["reason"]["round"],
            row["points_per_player"],
        )
        for row in places["rows"]
    ]
    assert places["complete"] is True
    # BR-110, BR-111: a shared place earns the average of the places it covers
    assert rows == [
        (1, 1, "won_final", "final", 10),
        (2, 2, "lost_final", "final", 8),
        (3, 3, "lost_in_round", "semifinal", 5),
        (3, 4, "lost_in_round", "semifinal", 5),
        (5, 5, "lost_in_round", "quarterfinal", 1),
        (5, 6, "lost_in_round", "quarterfinal", 1),
    ]
    reasons = [row["reason"] for row in places["rows"]]
    assert {(r["group_place"], r["group_format"]) for r in reasons} == {(None, None)}
    assert reasons[0]["score"] == [10, 5]
    loser = next(e for e, seed in seed_of.items() if seed == 2)
    assert reasons[0]["opponent_entry_id"] == loser


def test_br102_the_third_place_match_decides_3rd_and_4th(
    started: Callable[..., Json],
    read: Callable[..., Json],
    play_out: Callable[[Json], dict[Key, Json]],
) -> None:
    tournament = started(5, third_place_match=True)
    play_out(tournament)

    places = read(tournament["id"], "/places")

    assert [(r["place"], r["reason"]["kind"]) for r in places["rows"]] == [
        (1, "won_final"),
        (2, "lost_final"),
        (3, "won_third_place"),
        (4, "lost_third_place"),
        (5, "lost_in_round"),
    ]


def test_br112_the_season_standings_count_a_knockout_from_the_start(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    started: Callable[..., Json],
    read: Callable[..., Json],
    play_out: Callable[[Json], dict[Key, Json]],
    set_up: Callable[..., Json],
) -> None:
    tournament = started(12, type="dyp")
    play_out(tournament)
    points = {
        player: row["points_per_player"]
        for row in read(tournament["id"], "/places")["rows"]
        for entry in tournament["entries"]
        if entry["id"] == row["entry_id"]
        for player in entry["player_ids"]
    }
    in_setup = set_up(4)  # the setup ranking reads the season standings (BR-020)

    standings = client.get(
        _url(league_id, f"/seasons/{tournament['season_id']}/standings"),
        headers=headers,
    )
    effect = read(tournament["id"], "/season-effect")

    assert standings.status_code == 200, standings.text
    assert {r["player_id"]: r["points"] for r in standings.json()} == points
    assert sorted(points.values(), reverse=True) == [10, 10, 8, 8] + [5] * 4 + [1] * 4
    assert effect
    assert read(in_setup["tournament_id"], "/setup")["ranking"]


# ---------------------------------------------------------------- back to setup


def test_fr036_back_to_setup_deletes_the_bracket_and_keeps_the_format(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    started: Callable[..., Json],
    read: Callable[..., Json],
    start: Callable[[Json], tuple[int, Json]],
    session: Session,
) -> None:
    tournament = started(6, third_place_match=True, knockout_match_format="bo3")

    response = client.post(
        _t_url(league_id, tournament["id"], "/back-to-setup"),
        json={"expected_state": "in_progress"},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["state"] == "setup"
    assert response.json()["rounds"] == []
    assert session.scalar(select(func.count()).select_from(Match)) == 0
    bracket = client.get(
        _t_url(league_id, tournament["id"], "/bracket"), headers=headers
    )
    assert bracket.json() == {"code": "knockout_not_found", "detail": {}}
    fmt = read(tournament["id"], "/setup")["format"]
    assert (fmt["group_phase"], fmt["third_place_match"]) == ("none", True)
    assert fmt["knockout_match_format"] == KnockoutMatchFormat.BO3
    setup = read(tournament["id"], "/setup")
    status, again = start(setup)
    assert status == 200, again
    assert sum(len(r["matches"]) for r in again["rounds"]) == 8


def test_fr036_back_to_setup_ends_with_the_first_result(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    started: Callable[..., Json],
    read: Callable[..., Json],
    put_result: Callable[..., tuple[int, Json]],
) -> None:
    tournament = started(4)
    first = by_key(read(tournament["id"], "/bracket"))[1, "standard", 1]
    put_result(tournament["id"], first, win("side_1"))

    response = client.post(
        _t_url(league_id, tournament["id"], "/back-to-setup"),
        json={"expected_state": "in_progress"},
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json() == {
        "code": "tournament_has_results",
        "detail": {"results": 1},
    }


def test_fr046_a_knockout_without_a_group_phase_is_not_deleted_as_a_phase(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    started: Callable[..., Json],
) -> None:
    tournament = started(4)
    phase_id = tournament["phases"][0]["id"]

    response = client.delete(
        _t_url(league_id, tournament["id"], f"/phases/{phase_id}"), headers=headers
    )

    assert response.status_code == 422
    assert response.json() == {
        "code": "phase_not_deletable",
        "detail": {"kind": "knockout"},
    }


# ---------------------------------------------------------------- share link


def test_fr070_the_share_link_shows_the_bracket_and_the_places(
    client: TestClient,
    league: League,
    started: Callable[..., Json],
    play_out: Callable[[Json], dict[Key, Json]],
    read: Callable[..., Json],
) -> None:
    tournament = started(6)
    running = client.get(_public(league.share_token, tournament["id"], "/bracket"))
    play_out(tournament)

    shared = client.get(_public(league.share_token, tournament["id"], "/bracket"))
    places = client.get(_public(league.share_token, tournament["id"], "/places"))

    assert running.status_code == 200
    assert running.json()["has_group_phase"] is False
    assert [seeds(m) for m in running.json()["rounds"][0]["matches"]] == [
        [1, None],
        [4, 5],
        [2, None],
        [3, 6],
    ]
    assert shared.status_code == 200
    assert shared.json()["rounds"][-1]["matches"][0]["state"] == "played"
    assert places.status_code == 200
    organizer = read(tournament["id"], "/places")["rows"]
    assert [
        (r["place"], r["entry_id"], r["reason"]["kind"]) for r in places.json()["rows"]
    ] == [(r["place"], r["entry_id"], r["reason"]["kind"]) for r in organizer]


# ---------------------------------------------------------------- races


def _commit_setup(engine: Engine, now: datetime) -> tuple[UUID, UUID, UUID, int]:
    """A committed league with a Singles knockout of six players in setup."""
    with Session(engine) as setup:
        owner = User(
            email="knockout-only@example.test",
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
        player_ids = [
            player_service.add_player(
                setup,
                league_id=league.id,
                user_id=owner.id,
                name=f"P{n}",
                clock=lambda: now,
            ).id
            for n in range(6)
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
                group_phase=GroupPhase.NONE,
                third_place_match=True,
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
        counter = tournament_service.set_seeding_method(  # a draw has seeds to shuffle
            setup,
            league_id=league.id,
            tournament_id=tournament_id,
            user_id=owner.id,
            method=SeedingMethod.RANDOM,
            clock=lambda: now,
        ).draw_counter
        setup.commit()
        return owner.id, league.id, tournament_id, counter


@pytest.mark.concurrency
@pytest.mark.parametrize("winner", ["start", "draw"])
def test_adr008_a_knockout_start_racing_a_new_seed_draw_has_one_winner(
    committing_settings: Settings,
    committing_engine: Engine,
    now: datetime,
    committed_auth_header: Callable[..., dict[str, str]],
    wait_for_a_lock_wait: Callable[[], None],
    winner: str,
) -> None:
    owner_id, league_id, tournament_id, counter = _commit_setup(committing_engine, now)
    outcome: list[tuple[int, object]] = []

    with (
        Session(committing_engine) as first,
        TestClient(create_app(committing_settings)) as client,
    ):
        if winner == "start":
            tournament_service.start_tournament(
                first,
                league_id=league_id,
                tournament_id=tournament_id,
                user_id=owner_id,
                expected_draw_counter=counter,
                clock=lambda: now,
            )
            path, body = "/setup/draw", {"target": "seeds"}
        else:
            tournament_service.draw_again(
                first,
                league_id=league_id,
                tournament_id=tournament_id,
                user_id=owner_id,
                target=tournament_service.DrawTarget.SEEDS,
                expected_draw_counter=counter,
                clock=lambda: now,
            )
            path, body = "/start", {}

        def second_request() -> None:
            response = client.post(
                _t_url(league_id, str(tournament_id), path),
                json={"expected_draw_counter": counter, **body},
                headers=committed_auth_header(owner_id, issued_at=datetime.now(UTC)),
            )
            outcome.append((response.status_code, response.json()))

        second = threading.Thread(target=second_request)
        second.start()
        wait_for_a_lock_wait()  # it waits for the league lock the first one holds
        first.commit()
        second.join()

    stale = {
        "start": {
            "code": "tournament_not_in_setup",
            "detail": {"state": "in_progress"},
        },
        "draw": {
            "code": "draw_counter_changed",
            "detail": {"draw_counter": counter + 1},
        },
    }
    assert outcome == [(409, stale[winner])]
    with Session(committing_engine) as check:
        tournament = check.get_one(Tournament, tournament_id)
        matches = check.scalar(select(func.count()).select_from(Match))
        if winner == "start":
            assert (tournament.state, tournament.draw_counter, matches) == (
                "in_progress",
                counter,
                8,  # 4 + 2 + the final + the third-place match, the byes included
            )
        else:
            assert (tournament.state, tournament.draw_counter, matches) == (
                "setup",
                counter + 1,
                0,
            )
