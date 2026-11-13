"""The Swiss: start, rounds, results lock, tie-breakers, standings and the end
(FR-035, FR-040, FR-042, FR-043, FR-045, FR-046, BR-055 to BR-058, BR-064 to
BR-066, BR-072 to BR-076, BR-087, BR-130).
"""

from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import UUID, uuid7

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tourneyhub.db.models.entries import Entry
from tourneyhub.db.models.leagues import League, Player, Season
from tourneyhub.db.models.matches import RoundParticipation
from tourneyhub.db.models.tournaments import TournamentPhase
from tourneyhub.engine.leagues import SeasonState

type Json = dict[str, Any]

SWISS: Json = {
    "name": "Thursday Swiss",
    "date": "2026-11-12",
    "type": "singles",
    "group_phase": "swiss",
    "round_robin_legs": None,
    "sit_out_points": None,
    "group_match_format": "bo1",
    "knockout_match_format": None,
    "final_match_format": None,
    "third_place_match": None,
    "goals_per_game": 10,
    "field_count": 2,
}
EMPTY: Json = {"walkover_winner": None, "games": []}


def win(side: str, score: tuple[int, int] = (10, 5)) -> Json:
    """A BO1 result with a score, which a Swiss requires (BR-092)."""
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


def seeds(tournament: Json) -> list[str]:
    """The main entries, seed 1 first."""
    main = [e for e in tournament["entries"] if e["stage"] == "main"]
    return [e["id"] for e in sorted(main, key=lambda e: e["seed"])]


def round_of(tournament: Json, round_no: int) -> Json:
    group = next(p for p in tournament["phases"] if p["kind"] == "group")
    return next(
        r
        for r in tournament["rounds"]
        if r["phase_id"] == group["id"] and r["round_no"] == round_no
    )


def pairs(round_: Json) -> list[tuple[str, str]]:
    return [
        (match["sides"][0]["entry_id"], match["sides"][1]["entry_id"])
        for match in round_["matches"]
    ]


def by_entry(rows: list[Json]) -> dict[str, Json]:
    return {row["entry_id"]: row for row in rows}


def unmarked(round_: Json) -> Json:
    """A drawn round without the marks only the draw returns (ADR-009)."""
    matches = [
        {k: v for k, v in match.items() if k not in {"is_repeat", "is_decided_by_lot"}}
        for match in round_["matches"]
    ]
    rest = {k: v for k, v in round_.items() if k != "is_sit_out_by_lot"}
    return {**rest, "matches": matches}


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
    return [str(make_player(league=league, name=f"P{n}").id) for n in range(1, 9)]


@pytest.fixture
def setup(
    client: TestClient, league_id: UUID, headers: dict[str, str], players: list[str]
) -> Callable[..., Json]:
    def setup(count: int, **values: object) -> Json:
        """A Swiss in setup with the first `count` players picked."""
        body = {"id": str(uuid7()), **SWISS, **values}
        created = client.post(
            _url(league_id, "/tournaments"), json=body, headers=headers
        )
        assert created.status_code == 201, created.text
        picked = client.put(
            _t_url(league_id, created.json()["tournament_id"], "/setup/players"),
            json={"player_ids": players[:count]},
            headers=headers,
        )
        assert picked.status_code == 200, picked.text
        result: Json = picked.json()
        return result

    return setup


@pytest.fixture
def start(
    client: TestClient, league_id: UUID, headers: dict[str, str]
) -> Callable[[Json], tuple[int, Json]]:
    def start(setup: Json) -> tuple[int, Json]:
        """Generate and start, from the setup the review screen showed (FR-035)."""
        main = [e for e in setup["entries"] if e["stage"] == "main"]
        response = client.post(
            _t_url(league_id, setup["tournament_id"], "/start"),
            json={
                "expected_draw_counter": setup["draw_counter"],
                "expected_seed_order": [
                    e["id"] for e in sorted(main, key=lambda e: e["seed"])
                ],
            },
            headers=headers,
        )
        result: Json = response.json()
        return response.status_code, result

    return start


@pytest.fixture
def swiss(
    setup: Callable[..., Json], start: Callable[[Json], tuple[int, Json]]
) -> Callable[..., Json]:
    def swiss(count: int = 4, **values: object) -> Json:
        """A started Swiss of `count` players: round 1 is drawn."""
        status, tournament = start(setup(count, **values))
        assert status == 200, tournament
        return tournament

    return swiss


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
def put_result(
    client: TestClient, league_id: UUID, headers: dict[str, str]
) -> Callable[[str, str, Json], tuple[int, Json]]:
    def put_result(tournament_id: str, match_id: str, body: Json) -> tuple[int, Json]:
        response = client.put(
            _t_url(league_id, tournament_id, f"/matches/{match_id}/result"),
            json=body,
            headers=headers,
        )
        result: Json = response.json()
        return response.status_code, result

    return put_result


@pytest.fixture
def add_round(
    client: TestClient, league_id: UUID, headers: dict[str, str]
) -> Callable[[str, int], tuple[int, Json]]:
    def add_round(tournament_id: str, expected_round_no: int) -> tuple[int, Json]:
        response = client.post(
            _t_url(league_id, tournament_id, "/rounds"),
            json={"expected_round_no": expected_round_no},
            headers=headers,
        )
        result: Json = response.json() if response.content else {}
        return response.status_code, result

    return add_round


@pytest.fixture
def delete_round(
    client: TestClient, league_id: UUID, headers: dict[str, str]
) -> Callable[[str, str], tuple[int, Json]]:
    def delete_round(tournament_id: str, round_id: str) -> tuple[int, Json]:
        response = client.delete(
            _t_url(league_id, tournament_id, f"/rounds/{round_id}"), headers=headers
        )
        result: Json = response.json() if response.content else {}
        return response.status_code, result

    return delete_round


@pytest.fixture
def set_tiebreakers(
    client: TestClient, league_id: UUID, headers: dict[str, str]
) -> Callable[[str, list[str]], tuple[int, Json]]:
    def set_tiebreakers(tournament_id: str, order: list[str]) -> tuple[int, Json]:
        response = client.put(
            _t_url(league_id, tournament_id, "/tiebreakers"),
            json={"tiebreakers": order},
            headers=headers,
        )
        result: Json = response.json()
        return response.status_code, result

    return set_tiebreakers


@pytest.fixture
def play_round(
    read: Callable[..., Json],
    put_result: Callable[[str, str, Json], tuple[int, Json]],
) -> Callable[..., Json]:
    def play_round(
        tournament_id: str, round_no: int, scores: list[tuple[int, int]] | None = None
    ) -> Json:
        """Side 1 wins every match of the round, 10-5 unless `scores` says."""
        tournament = read(tournament_id)
        for index, match in enumerate(round_of(tournament, round_no)["matches"]):
            score = (10, 5) if scores is None else scores[index]
            status, body = put_result(tournament_id, match["id"], win("side_1", score))
            assert status == 200, body
        return read(tournament_id)

    return play_round


@pytest.fixture
def close_season(session: Session, now: datetime) -> Callable[[Json], None]:
    def close_season(tournament: Json) -> None:
        """Close the tournament's season and open the next, as a new season does."""
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

    return close_season


@pytest.fixture
def disable(session: Session) -> Callable[[str], None]:
    def disable(entry_id: str) -> None:
        """Disable an entry; its route comes with P14 (FR-044)."""
        session.get_one(Entry, UUID(entry_id)).is_disabled = True
        session.flush()

    return disable


@pytest.fixture
def start_knockout(
    client: TestClient, league_id: UUID, headers: dict[str, str]
) -> Callable[..., tuple[int, Json]]:
    def start_knockout(tournament: Json, qualifiers: int = 4) -> tuple[int, Json]:
        """Start as the screen does: it names the qualifiers its preview showed."""
        shown = client.get(
            _t_url(
                league_id,
                tournament["id"],
                f"/knockout/preview?qualifiers={qualifiers}&third_place_match=false",
            ),
            headers=headers,
        ).json()
        response = client.put(
            _t_url(league_id, tournament["id"], "/knockout"),
            json={
                "expected_current_phase_id": tournament["current_phase_id"],
                "expected_draw_counter": shown["draw_counter"],
                "expected_qualifier_ids": [
                    e["members"][0]["entry_id"] for e in shown["entries"]
                ],
                "qualifiers": qualifiers,
                "third_place_match": False,
                "match_format": None,
                "final_match_format": None,
                "mode": None,
            },
            headers=headers,
        )
        result: Json = response.json()
        return response.status_code, result

    return start_knockout


@pytest.fixture
def play_knockout(
    read: Callable[..., Json],
    put_result: Callable[[str, str, Json], tuple[int, Json]],
) -> Callable[[str], Json]:
    def play_knockout(tournament_id: str) -> Json:
        """Side 1 wins every knockout match, round by round, until it finishes."""
        while read(tournament_id)["state"] != "finished":
            bracket = read(tournament_id, "/bracket")
            ready = [
                m
                for r in bracket["rounds"]
                for m in r["matches"]
                if m["state"] in {"ready", "on_field"}
            ]
            assert ready, bracket
            for match in ready:
                sides = [side["entry_id"] for side in match["sides"]]
                status, body = put_result(
                    tournament_id,
                    match["match_id"],
                    {**win("side_1"), "expected_sides": sides},
                )
                assert status == 200, body
        return read(tournament_id)

    return play_knockout


# ---------------------------------------------------------------- start


def test_br055_round_1_pairs_the_top_half_of_the_seeds_against_the_bottom_half(
    swiss: Callable[..., Json], session: Session
) -> None:
    tournament = swiss(8)

    order = seeds(tournament)
    [round_1] = tournament["rounds"]
    assert tournament["state"] == "in_progress"
    assert round_1["round_no"] == 1
    assert pairs(round_1) == [(order[i], order[i + 4]) for i in range(4)]
    assert round_1["sitting_out"] == []
    statuses = session.scalars(
        select(RoundParticipation.status).where(
            RoundParticipation.round_id == UUID(round_1["id"])
        )
    ).all()
    assert sorted(statuses) == ["played"] * 8
    assert [f["match_id"] for f in tournament["fields"]] == [
        m["id"] for m in round_1["matches"][:2]
    ]


def test_br058_the_lowest_seed_sits_out_round_1_with_an_odd_number(
    swiss: Callable[..., Json],
) -> None:
    tournament = swiss(7)

    order = seeds(tournament)
    [round_1] = tournament["rounds"]
    assert round_1["sitting_out"] == [order[6]]
    assert pairs(round_1) == [
        (order[0], order[3]),
        (order[1], order[4]),
        (order[2], order[5]),
    ]


def test_fr035_the_preview_of_a_swiss_is_round_1_without_counts(
    setup: Callable[..., Json],
    start: Callable[[Json], tuple[int, Json]],
    read: Callable[..., Json],
) -> None:
    ready = setup(5)

    preview = read(ready["tournament_id"], "/setup/preview")
    _, started = start(ready)

    members = {e["id"]: e["player_ids"] for e in started["entries"]}
    [round_1] = started["rounds"]
    assert preview["can_start"] is True
    assert (preview["match_count"], preview["round_count"]) == (None, None)
    [shown] = preview["rounds"]
    assert shown["round_no"] == 1
    assert [m["sides"] for m in shown["matches"]] == [
        [members[one], members[two]] for one, two in pairs(round_1)
    ]
    assert shown["sitting_out"] == [members[e] for e in round_1["sitting_out"]]


def test_fr039_a_new_swiss_starts_with_the_default_tiebreakers(
    swiss: Callable[..., Json],
) -> None:
    tournament = swiss(4)

    [phase] = tournament["phases"]
    assert phase["format"] == "swiss"
    assert phase["tiebreakers"] == ["bh1", "bh2", "score_difference"]
    assert phase["sit_out_points"] == 0


# ---------------------------------------------------------------- standings


def test_br076_sit_out_points_count_as_soon_as_the_round_is_drawn(
    swiss: Callable[..., Json], read: Callable[..., Json]
) -> None:
    tournament = swiss(3, sit_out_points=2)

    play = read(tournament["id"], "/play")

    sitter = seeds(tournament)[2]
    rows = by_entry(play["standings"])
    assert rows[sitter]["points"] == 2
    assert rows[sitter]["sat_out"] == 1
    assert rows[sitter]["place"] == 1
    assert rows[sitter]["played"] == 0
    assert [row["points"] for e, row in rows.items() if e != sitter] == [0, 0]
    assert play["group_done"] is False


def test_br073_the_standings_show_bh1_bh2_and_shared_places(
    swiss: Callable[..., Json],
    play_round: Callable[..., Json],
    read: Callable[..., Json],
) -> None:
    tournament = swiss(4)
    played = play_round(tournament["id"], 1)

    play = read(tournament["id"], "/play")

    one, two, three, four = seeds(tournament)
    rows = by_entry(play["standings"])
    assert play["group_done"] is True
    # Seeds 1 and 2 beat seeds 3 and 4, 10-5 each: level on everything (BR-074).
    for winner in (one, two):
        assert rows[winner] | {"entry_id": None} == {
            "place": 1,
            "entry_id": None,
            "played": 1,
            "won": 1,
            "drawn": 0,
            "lost": 0,
            "sat_out": 0,
            "points": 2,
            "game_difference": 1,
            "score_difference": 5,
            "form": [],
            "ahead_by": None,
            "bh1": 0,
            "bh2": 2,
        }
    for loser in (three, four):
        assert (rows[loser]["place"], rows[loser]["bh1"], rows[loser]["bh2"]) == (
            3,
            2,
            0,
        )
    assert pairs(round_of(played, 1)) == [(one, three), (two, four)]


def test_fr043_the_tiebreaker_order_changes_the_play_standings(
    swiss: Callable[..., Json],
    play_round: Callable[..., Json],
    read: Callable[..., Json],
    set_tiebreakers: Callable[[str, list[str]], tuple[int, Json]],
) -> None:
    tournament = swiss(4)
    play_round(tournament["id"], 1, [(10, 0), (10, 9)])
    one, two, _, _ = seeds(tournament)
    before = by_entry(read(tournament["id"], "/play")["standings"])

    status, body = set_tiebreakers(tournament["id"], ["bh1"])

    after = by_entry(read(tournament["id"], "/play")["standings"])
    assert status == 200, body
    assert body["phases"][0]["tiebreakers"] == ["bh1"]
    # Score difference set seed 1 (+10) above seed 2 (+1); BH1 alone cannot.
    assert (before[one]["place"], before[two]["place"]) == (1, 2)
    assert (after[one]["place"], after[two]["place"]) == (1, 1)


def test_fr043_the_tiebreakers_can_be_set_in_setup(
    setup: Callable[..., Json],
    set_tiebreakers: Callable[[str, list[str]], tuple[int, Json]],
) -> None:
    ready = setup(4)

    status, body = set_tiebreakers(ready["tournament_id"], ["score_difference", "bh2"])

    assert status == 200, body
    assert body["state"] == "setup"
    assert body["phases"][0]["tiebreakers"] == ["score_difference", "bh2"]


def test_adr008_the_same_tiebreakers_again_change_nothing(
    swiss: Callable[..., Json],
    set_tiebreakers: Callable[[str, list[str]], tuple[int, Json]],
    session: Session,
) -> None:
    tournament = swiss(4)
    phase = session.get_one(TournamentPhase, UUID(tournament["phases"][0]["id"]))

    status, body = set_tiebreakers(tournament["id"], ["bh1", "bh2", "score_difference"])

    session.refresh(phase)
    assert status == 200, body
    assert body["phases"] == tournament["phases"]
    assert phase.updated_at is None


@pytest.mark.parametrize(
    "order",
    [
        pytest.param(["bh1", "bh1"], id="given-twice"),
        pytest.param(["bh3"], id="unknown"),
        pytest.param(["bh1", "bh2", "score_difference", "bh1"], id="too-long"),
    ],
)
def test_fr043_an_invalid_tiebreaker_order_is_422(
    swiss: Callable[..., Json],
    set_tiebreakers: Callable[[str, list[str]], tuple[int, Json]],
    order: list[str],
) -> None:
    tournament = swiss(4)

    status, body = set_tiebreakers(tournament["id"], order)

    assert status == 422
    assert body["code"] == "validation_failed"


def test_fr043_a_repeated_tiebreaker_is_given_twice(
    swiss: Callable[..., Json],
    set_tiebreakers: Callable[[str, list[str]], tuple[int, Json]],
) -> None:
    tournament = swiss(4)

    _, body = set_tiebreakers(tournament["id"], ["bh2", "bh2"])

    assert body["detail"]["errors"][0]["type"] == "given_twice"


def test_fr043_a_round_robin_has_no_tiebreakers_to_set(
    setup: Callable[..., Json],
    set_tiebreakers: Callable[[str, list[str]], tuple[int, Json]],
) -> None:
    ready = setup(4, group_phase="round_robin", round_robin_legs=1)

    status, body = set_tiebreakers(ready["tournament_id"], ["bh1"])

    assert (status, body) == (
        422,
        {"code": "format_not_supported", "detail": {"format": "round_robin"}},
    )


def test_fr043_the_tiebreakers_of_a_finished_tournament_do_not_change(
    swiss: Callable[..., Json],
    play_round: Callable[..., Json],
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    set_tiebreakers: Callable[[str, list[str]], tuple[int, Json]],
) -> None:
    tournament = swiss(2)
    play_round(tournament["id"], 1)
    finished = client.post(
        _t_url(league_id, tournament["id"], "/finish"),
        json={"expected_state": "in_progress"},
        headers=headers,
    )
    assert finished.status_code == 200, finished.text

    status, body = set_tiebreakers(tournament["id"], [])

    assert (status, body) == (
        409,
        {"code": "tournament_not_in_progress", "detail": {"state": "finished"}},
    )


def test_br011_the_tiebreakers_of_a_closed_season_do_not_change(
    swiss: Callable[..., Json],
    close_season: Callable[[Json], None],
    set_tiebreakers: Callable[[str, list[str]], tuple[int, Json]],
) -> None:
    tournament = swiss(4)
    close_season(tournament)

    status, body = set_tiebreakers(tournament["id"], [])

    assert (status, body) == (409, {"code": "season_closed", "detail": {}})


def test_fr070_the_public_standings_of_a_swiss_show_bh1_and_bh2(
    swiss: Callable[..., Json],
    play_round: Callable[..., Json],
    client: TestClient,
    league: League,
) -> None:
    tournament = swiss(4)
    play_round(tournament["id"], 1)

    response = client.get(
        f"/api/v1/public/{league.share_token}/tournaments/{tournament['id']}/standings"
    )

    one = seeds(tournament)[0]
    rows = by_entry(response.json())
    assert response.status_code == 200
    assert rows[one] == {
        "place": 1,
        "entry_id": one,
        "played": 1,
        "won": 1,
        "drawn": 0,
        "lost": 0,
        "sat_out": 0,
        "points": 2,
        "game_difference": 1,
        "score_difference": 5,
        "bh1": 0,
        "bh2": 2,
    }


# ---------------------------------------------------------------- adding a round


def test_br056_the_next_round_pairs_neighbours_in_the_standings(
    swiss: Callable[..., Json],
    play_round: Callable[..., Json],
    add_round: Callable[[str, int], tuple[int, Json]],
    read: Callable[..., Json],
) -> None:
    tournament = swiss(4)
    play_round(tournament["id"], 1)

    status, round_2 = add_round(tournament["id"], 2)

    one, two, three, four = seeds(tournament)
    assert status == 201, round_2
    assert round_2["round_no"] == 2
    assert round_2["sitting_out"] == []
    # The winners are level, so the lot orders them; each plays the other (BR-056).
    assert sorted(map(frozenset, pairs(round_2)), key=sorted) == sorted(
        [frozenset({one, two}), frozenset({three, four})], key=sorted
    )
    after = read(tournament["id"])
    assert round_of(after, 2) == unmarked(round_2)
    assert {f["match_id"] for f in after["fields"]} == {
        m["id"] for m in round_2["matches"]
    }


@pytest.mark.parametrize(
    ("scores", "by_lot"),
    [([(10, 5), (10, 5)], True), ([(10, 1), (10, 5)], False)],
    ids=["level", "apart"],
)
def test_adr009_br056_a_pair_whose_place_a_lot_decided_is_marked(
    swiss: Callable[..., Json],
    play_round: Callable[..., Json],
    add_round: Callable[[str, int], tuple[int, Json]],
    scores: list[tuple[int, int]],
    by_lot: bool,
) -> None:
    tournament = swiss(4)
    play_round(tournament["id"], 1, scores)

    status, round_2 = add_round(tournament["id"], 2)

    # Level scores leave the two winners, and the two losers, sharing a place.
    assert status == 201, round_2
    assert [m["is_decided_by_lot"] for m in round_2["matches"]] == [by_lot, by_lot]
    assert [m["is_repeat"] for m in round_2["matches"]] == [False, False]


def test_adr009_br057_a_repeat_no_draw_avoids_is_marked(
    swiss: Callable[..., Json],
    play_round: Callable[..., Json],
    add_round: Callable[[str, int], tuple[int, Json]],
) -> None:
    tournament = swiss(4)
    repeats = []
    for round_no in (2, 3, 4):
        play_round(tournament["id"], round_no - 1)
        status, drawn = add_round(tournament["id"], round_no)
        assert status == 201, drawn
        repeats.append([m["is_repeat"] for m in drawn["matches"]])

    # Rounds 1 to 3 hold every pair of 4 entries, so round 4 repeats (BR-057).
    assert repeats == [[False, False], [False, False], [True, True]]


@pytest.mark.parametrize(
    ("scores", "by_lot"),
    [([(10, 5), (10, 5)], True), ([(10, 1), (10, 5)], False)],
    ids=["level", "apart"],
)
def test_adr009_br058_a_sit_out_a_lot_decided_is_marked(
    swiss: Callable[..., Json],
    play_round: Callable[..., Json],
    add_round: Callable[[str, int], tuple[int, Json]],
    scores: list[tuple[int, int]],
    by_lot: bool,
) -> None:
    tournament = swiss(5)
    play_round(tournament["id"], 1, scores)

    status, round_2 = add_round(tournament["id"], 2)

    # The two losers of round 1 are the lowest that have not sat out yet.
    assert status == 201, round_2
    assert len(round_2["sitting_out"]) == 1
    assert round_2["is_sit_out_by_lot"] is by_lot


def test_adr008_a_stale_expected_round_number_is_409(
    swiss: Callable[..., Json],
    play_round: Callable[..., Json],
    add_round: Callable[[str, int], tuple[int, Json]],
) -> None:
    tournament = swiss(4)
    play_round(tournament["id"], 1)

    ahead = add_round(tournament["id"], 3)
    added = add_round(tournament["id"], 2)
    repeat = add_round(tournament["id"], 2)

    assert ahead == (
        409,
        {"code": "round_number_changed", "detail": {"current_round_no": 1}},
    )
    assert added[0] == 201
    assert repeat == (
        409,
        {"code": "round_number_changed", "detail": {"current_round_no": 2}},
    )


def test_fr040_a_round_with_a_match_left_is_not_followed(
    swiss: Callable[..., Json],
    put_result: Callable[[str, str, Json], tuple[int, Json]],
    add_round: Callable[[str, int], tuple[int, Json]],
) -> None:
    tournament = swiss(4)
    first = round_of(tournament, 1)["matches"][0]
    put_result(tournament["id"], first["id"], win("side_1"))

    status, body = add_round(tournament["id"], 2)

    assert (status, body) == (
        422,
        {"code": "round_not_complete", "detail": {"matches_left": 1}},
    )


def test_br058_a_later_round_does_not_sit_out_the_same_entry_again(
    swiss: Callable[..., Json],
    play_round: Callable[..., Json],
    add_round: Callable[[str, int], tuple[int, Json]],
    read: Callable[..., Json],
) -> None:
    tournament = swiss(5, sit_out_points=1)
    play_round(tournament["id"], 1)
    sat_out_first = seeds(tournament)[4]

    status, round_2 = add_round(tournament["id"], 2)

    assert status == 201, round_2
    [sitter] = round_2["sitting_out"]
    assert sitter != sat_out_first
    assert sat_out_first in {entry for pair in pairs(round_2) for entry in pair}
    rows = by_entry(read(tournament["id"], "/play")["standings"])
    assert (rows[sitter]["sat_out"], rows[sat_out_first]["sat_out"]) == (1, 1)


def test_br064_a_disabled_entry_is_not_drawn_and_misses_the_round(
    swiss: Callable[..., Json],
    play_round: Callable[..., Json],
    add_round: Callable[[str, int], tuple[int, Json]],
    disable: Callable[[str], None],
    read: Callable[..., Json],
    session: Session,
) -> None:
    tournament = swiss(4, sit_out_points=2)
    play_round(tournament["id"], 1)
    off = seeds(tournament)[0]
    disable(off)

    status, round_2 = add_round(tournament["id"], 2)

    assert status == 201, round_2
    playing = {entry for pair in pairs(round_2) for entry in pair}
    assert off not in playing
    assert off not in round_2["sitting_out"]
    assert len(playing) == 2
    assert len(round_2["sitting_out"]) == 1
    status_of = {
        row.entry_id: row.status
        for row in session.scalars(
            select(RoundParticipation).where(
                RoundParticipation.round_id == UUID(round_2["id"])
            )
        )
    }
    assert status_of[UUID(off)] == "disabled"
    rows = by_entry(read(tournament["id"], "/play")["standings"])
    assert (rows[off]["points"], rows[off]["sat_out"]) == (2, 0)


def test_br064_too_few_entries_left_to_draw_is_422(
    swiss: Callable[..., Json],
    play_round: Callable[..., Json],
    add_round: Callable[[str, int], tuple[int, Json]],
    disable: Callable[[str], None],
) -> None:
    tournament = swiss(2)
    play_round(tournament["id"], 1)
    disable(seeds(tournament)[1])

    status, body = add_round(tournament["id"], 2)

    assert (status, body) == (
        422,
        {"code": "not_enough_entries", "detail": {"minimum": 2, "given": 1}},
    )


def test_fr040_a_round_robin_adds_no_rounds(
    setup: Callable[..., Json],
    start: Callable[[Json], tuple[int, Json]],
    add_round: Callable[[str, int], tuple[int, Json]],
) -> None:
    _, tournament = start(setup(4, group_phase="round_robin", round_robin_legs=1))

    status, body = add_round(tournament["id"], 4)

    assert (status, body) == (
        422,
        {"code": "format_not_supported", "detail": {"format": "round_robin"}},
    )


def test_adr008_a_round_for_a_tournament_in_setup_is_409(
    setup: Callable[..., Json], add_round: Callable[[str, int], tuple[int, Json]]
) -> None:
    ready = setup(4)

    status, body = add_round(ready["tournament_id"], 2)

    assert (status, body) == (
        409,
        {"code": "tournament_not_in_progress", "detail": {"state": "setup"}},
    )


def test_br011_a_round_in_a_closed_season_is_409(
    swiss: Callable[..., Json],
    play_round: Callable[..., Json],
    close_season: Callable[[Json], None],
    add_round: Callable[[str, int], tuple[int, Json]],
) -> None:
    tournament = swiss(4)
    play_round(tournament["id"], 1)
    close_season(tournament)

    status, body = add_round(tournament["id"], 2)

    assert (status, body) == (409, {"code": "season_closed", "detail": {}})


# ---------------------------------------------------------------- the results lock


def test_br065_a_result_of_an_earlier_round_is_locked(
    swiss: Callable[..., Json],
    play_round: Callable[..., Json],
    add_round: Callable[[str, int], tuple[int, Json]],
    put_result: Callable[[str, str, Json], tuple[int, Json]],
) -> None:
    tournament = swiss(4)
    played = play_round(tournament["id"], 1)
    add_round(tournament["id"], 2)
    match = round_of(played, 1)["matches"][0]

    changed = put_result(tournament["id"], match["id"], win("side_2"))
    cleared = put_result(tournament["id"], match["id"], EMPTY)
    repeated = put_result(tournament["id"], match["id"], win("side_1"))

    locked = (422, {"code": "round_locked", "detail": {"round_no": 2}})
    assert changed == locked
    assert cleared == locked
    assert repeated[0] == 200


def test_br066_deleting_the_newest_round_unlocks_the_one_before(
    swiss: Callable[..., Json],
    play_round: Callable[..., Json],
    add_round: Callable[[str, int], tuple[int, Json]],
    delete_round: Callable[[str, str], tuple[int, Json]],
    put_result: Callable[[str, str, Json], tuple[int, Json]],
    read: Callable[..., Json],
) -> None:
    tournament = swiss(4)
    played = play_round(tournament["id"], 1)
    _, round_2 = add_round(tournament["id"], 2)
    put_result(tournament["id"], round_2["matches"][0]["id"], win("side_1"))

    deleted = delete_round(tournament["id"], round_2["id"])
    changed = put_result(
        tournament["id"], round_of(played, 1)["matches"][0]["id"], win("side_2")
    )

    after = read(tournament["id"])
    assert deleted == (204, {})
    assert changed[0] == 200, changed
    assert [r["round_no"] for r in after["rounds"]] == [1]
    assert [f["match_id"] for f in after["fields"]] == [None, None]


# ---------------------------------------------------------------- deleting a round


def test_fr046_only_the_newest_round_is_deleted(
    swiss: Callable[..., Json],
    play_round: Callable[..., Json],
    add_round: Callable[[str, int], tuple[int, Json]],
    delete_round: Callable[[str, str], tuple[int, Json]],
) -> None:
    tournament = swiss(4)
    played = play_round(tournament["id"], 1)
    _, round_2 = add_round(tournament["id"], 2)

    status, body = delete_round(tournament["id"], round_of(played, 1)["id"])

    assert (status, body) == (
        409,
        {"code": "round_not_newest", "detail": {"round_id": round_2["id"]}},
    )


def test_adr008_an_unknown_or_deleted_round_is_404(
    swiss: Callable[..., Json],
    play_round: Callable[..., Json],
    add_round: Callable[[str, int], tuple[int, Json]],
    delete_round: Callable[[str, str], tuple[int, Json]],
) -> None:
    tournament = swiss(4)
    play_round(tournament["id"], 1)
    _, round_2 = add_round(tournament["id"], 2)
    delete_round(tournament["id"], round_2["id"])

    repeat = delete_round(tournament["id"], round_2["id"])
    unknown = delete_round(tournament["id"], str(uuid7()))

    assert repeat == unknown == (404, {"code": "round_not_found", "detail": {}})


def test_fr046_deleting_round_1_goes_back_to_setup_with_results(
    swiss: Callable[..., Json],
    put_result: Callable[[str, str, Json], tuple[int, Json]],
    delete_round: Callable[[str, str], tuple[int, Json]],
    disable: Callable[[str], None],
    read: Callable[..., Json],
    start: Callable[[Json], tuple[int, Json]],
) -> None:
    tournament = swiss(4)
    put_result(
        tournament["id"], round_of(tournament, 1)["matches"][0]["id"], win("side_1")
    )
    disable(seeds(tournament)[3])

    status, _ = delete_round(tournament["id"], round_of(tournament, 1)["id"])

    after = read(tournament["id"])
    assert status == 204
    assert after["state"] == "setup"
    assert after["rounds"] == []
    assert [f["match_id"] for f in after["fields"]] == [None, None]
    assert not any(e["is_disabled"] for e in after["entries"])
    assert seeds(after) == seeds(tournament)
    again, restarted = start(read(tournament["id"], "/setup"))
    assert again == 200, restarted
    assert pairs(round_of(restarted, 1)) == pairs(round_of(tournament, 1))


def test_fr046_a_round_robin_round_is_not_deleted(
    setup: Callable[..., Json],
    start: Callable[[Json], tuple[int, Json]],
    delete_round: Callable[[str, str], tuple[int, Json]],
) -> None:
    _, tournament = start(setup(4, group_phase="round_robin", round_robin_legs=1))

    status, body = delete_round(tournament["id"], tournament["rounds"][-1]["id"])

    assert (status, body) == (
        422,
        {"code": "format_not_supported", "detail": {"format": "round_robin"}},
    )


def test_br011_a_round_of_a_closed_season_is_not_deleted(
    swiss: Callable[..., Json],
    close_season: Callable[[Json], None],
    delete_round: Callable[[str, str], tuple[int, Json]],
) -> None:
    tournament = swiss(4)
    close_season(tournament)

    status, body = delete_round(tournament["id"], round_of(tournament, 1)["id"])

    assert (status, body) == (409, {"code": "season_closed", "detail": {}})


def test_fr046_a_round_of_a_finished_tournament_is_not_deleted(
    swiss: Callable[..., Json],
    play_round: Callable[..., Json],
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    delete_round: Callable[[str, str], tuple[int, Json]],
) -> None:
    tournament = swiss(2)
    play_round(tournament["id"], 1)
    client.post(
        _t_url(league_id, tournament["id"], "/finish"),
        json={"expected_state": "in_progress"},
        headers=headers,
    )

    status, body = delete_round(tournament["id"], round_of(tournament, 1)["id"])

    assert (status, body) == (
        409,
        {"code": "tournament_not_in_progress", "detail": {"state": "finished"}},
    )


# ---------------------------------------------------------------- the end


def test_fr040_a_swiss_evening_ends_with_places_and_season_points(
    swiss: Callable[..., Json],
    play_round: Callable[..., Json],
    add_round: Callable[[str, int], tuple[int, Json]],
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    read: Callable[..., Json],
) -> None:
    tournament = swiss(6)
    play_round(tournament["id"], 1)
    for round_no in (2, 3):
        status, body = add_round(tournament["id"], round_no)
        assert status == 201, body
        play_round(tournament["id"], round_no)
    standings = read(tournament["id"], "/play")["standings"]

    finished = client.post(
        _t_url(league_id, tournament["id"], "/finish"),
        json={"expected_state": "in_progress"},
        headers=headers,
    )

    places = read(tournament["id"], "/places")
    season = client.get(
        _url(league_id, f"/seasons/{tournament['season_id']}/standings"),
        headers=headers,
    ).json()
    assert finished.status_code == 200, finished.text
    assert finished.json()["state"] == "finished"
    assert places["complete"] is True
    assert {row["entry_id"]: row["place"] for row in places["rows"]} == {
        row["entry_id"]: row["place"] for row in standings
    }
    assert {row["reason"]["group_format"] for row in places["rows"]} == {"swiss"}
    assert len(season) == 6
    assert sum(row["points"] for row in season) > 0


def test_fr045_a_knockout_follows_a_swiss_and_locks_it(
    swiss: Callable[..., Json],
    play_round: Callable[..., Json],
    add_round: Callable[[str, int], tuple[int, Json]],
    start_knockout: Callable[..., tuple[int, Json]],
    put_result: Callable[[str, str, Json], tuple[int, Json]],
    delete_round: Callable[[str, str], tuple[int, Json]],
    set_tiebreakers: Callable[[str, list[str]], tuple[int, Json]],
    play_knockout: Callable[[str], Json],
    read: Callable[..., Json],
) -> None:
    tournament = swiss(6)
    play_round(tournament["id"], 1)
    add_round(tournament["id"], 2)
    played = play_round(tournament["id"], 2)
    newest = round_of(played, 2)

    status, drawn = start_knockout(played, qualifiers=4)

    assert status == 200, drawn
    knockout = next(p for p in drawn["phases"] if p["kind"] == "knockout")
    locked = {"code": "group_phase_locked", "detail": {"phase_id": knockout["id"]}}
    assert add_round(tournament["id"], 3) == (422, locked)
    assert delete_round(tournament["id"], newest["id"]) == (422, locked)
    assert set_tiebreakers(tournament["id"], []) == (422, locked)
    assert put_result(tournament["id"], newest["matches"][0]["id"], win("side_2")) == (
        422,
        locked,
    )
    finished = play_knockout(tournament["id"])
    places = read(tournament["id"], "/places")
    assert finished["state"] == "finished"
    assert [row["place"] for row in places["rows"]][:4] == [1, 2, 3, 3]
    assert [row["reason"]["kind"] for row in places["rows"][4:]] == [
        "group_place",
        "group_place",
    ]


def test_br087_deleting_the_knockout_unlocks_the_newest_swiss_round(
    swiss: Callable[..., Json],
    play_round: Callable[..., Json],
    add_round: Callable[[str, int], tuple[int, Json]],
    start_knockout: Callable[..., tuple[int, Json]],
    put_result: Callable[[str, str, Json], tuple[int, Json]],
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
) -> None:
    tournament = swiss(4)
    played = play_round(tournament["id"], 1)
    add_round(tournament["id"], 2)
    played = play_round(tournament["id"], 2)
    _, drawn = start_knockout(played, qualifiers=4)
    knockout = next(p for p in drawn["phases"] if p["kind"] == "knockout")

    deleted = client.delete(
        _t_url(league_id, tournament["id"], f"/phases/{knockout['id']}"),
        headers=headers,
    )

    assert deleted.status_code == 204, deleted.text
    newest = put_result(
        tournament["id"], round_of(played, 2)["matches"][0]["id"], win("side_2")
    )
    earlier = put_result(
        tournament["id"], round_of(played, 1)["matches"][0]["id"], win("side_2")
    )
    assert newest[0] == 200, newest
    assert earlier == (422, {"code": "round_locked", "detail": {"round_no": 2}})
    assert add_round(tournament["id"], 3)[0] == 201


# ---------------------------------------------------------------- another organizer


@pytest.mark.parametrize(
    ("method", "rest", "body"),
    [
        pytest.param("POST", "/rounds", {"expected_round_no": 2}, id="add-round"),
        pytest.param("DELETE", "/rounds/{round}", None, id="delete-round"),
        pytest.param("PUT", "/tiebreakers", {"tiebreakers": []}, id="tiebreakers"),
    ],
)
def test_api1_another_organizers_swiss_is_not_found(
    swiss: Callable[..., Json],
    client: TestClient,
    league_id: UUID,
    make_league: Callable[..., League],
    auth_header: Callable[..., dict[str, str]],
    method: str,
    rest: str,
    body: Json | None,
) -> None:
    tournament = swiss(4)
    other = make_league()
    url = _t_url(
        league_id, tournament["id"], rest.format(round=tournament["rounds"][0]["id"])
    )

    response = client.request(
        method, url, json=body, headers=auth_header(other.owner_user_id)
    )

    assert response.status_code == 404
    assert response.json()["code"] == "league_not_found"


def test_api1_a_round_of_another_tournament_is_not_found(
    swiss: Callable[..., Json],
    delete_round: Callable[[str, str], tuple[int, Json]],
) -> None:
    first, second = swiss(4), swiss(4)

    status, body = delete_round(first["id"], round_of(second, 1)["id"])

    assert (status, body) == (404, {"code": "round_not_found", "detail": {}})
