"""Results, the play read, finishing and the places (FR-040, FR-050 to FR-060)."""

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid7

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tourneyhub.db.models.leagues import League, Player, Season
from tourneyhub.engine.leagues import SeasonState

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
    "field_count": 1,
}

S1_WINS: Json = {
    "walkover_winner": None,
    "games": [{"winner": "side_1", "score_1": 10, "score_2": 7}],
}
EMPTY: Json = {"walkover_winner": None, "games": []}


def game(winner: str, score_1: int | None = None, score_2: int | None = None) -> Json:
    return {"winner": winner, "score_1": score_1, "score_2": score_2}


def games(*played: Json) -> Json:
    return {"walkover_winner": None, "games": list(played)}


def _url(league: League | UUID, rest: str = "") -> str:
    league_id = league.id if isinstance(league, League) else league
    return f"/api/v1/leagues/{league_id}{rest}"


def _t_url(league: League | UUID, tournament_id: str, rest: str = "") -> str:
    return _url(league, f"/tournaments/{tournament_id}{rest}")


@pytest.fixture
def league(make_league: Callable[..., League]) -> League:
    return make_league()


@pytest.fixture
def league_id(league: League) -> UUID:
    """The league's id, read before a request expires the row."""
    return league.id


@pytest.fixture
def headers(
    league: League, auth_header: Callable[..., dict[str, str]]
) -> dict[str, str]:
    return auth_header(league.owner_user_id)


@pytest.fixture
def players(league: League, make_player: Callable[..., Player]) -> list[str]:
    return [str(make_player(league=league, name=f"P{n}").id) for n in range(1, 7)]


@pytest.fixture
def start(
    client: TestClient, league_id: UUID, headers: dict[str, str]
) -> Callable[..., Json]:
    """Create, pick and start a round robin; returns the started tournament."""

    def start(player_ids: list[str], **values: object) -> Json:
        body = {"id": str(uuid7()), **ROUND_ROBIN, **values}
        created = client.post(
            _url(league_id, "/tournaments"), json=body, headers=headers
        )
        assert created.status_code == 201, created.text
        tournament_id = created.json()["tournament_id"]
        picked = client.put(
            _t_url(league_id, tournament_id, "/setup/players"),
            json={"player_ids": player_ids},
            headers=headers,
        )
        assert picked.status_code == 200, picked.text
        started = client.post(
            _t_url(league_id, tournament_id, "/start"),
            json={"expected_draw_counter": picked.json()["draw_counter"]},
            headers=headers,
        )
        assert started.status_code == 200, started.text
        tournament: Json = started.json()
        return tournament

    return start


@pytest.fixture
def put_result(
    client: TestClient, league_id: UUID, headers: dict[str, str]
) -> Callable[..., tuple[int, Json]]:
    def put_result(tournament: Json, match_id: str, body: Json) -> tuple[int, Json]:
        response = client.put(
            _t_url(league_id, tournament["id"], f"/matches/{match_id}/result"),
            json=body,
            headers=headers,
        )
        result: Json = response.json()
        return response.status_code, result

    return put_result


@pytest.fixture
def read(
    client: TestClient, league_id: UUID, headers: dict[str, str]
) -> Callable[[Json, str], Json]:
    def read(tournament: Json, rest: str = "") -> Json:
        response = client.get(
            _t_url(league_id, tournament["id"], rest), headers=headers
        )
        assert response.status_code == 200, response.text
        body: Json = response.json()
        return body

    return read


@pytest.fixture
def finish(
    client: TestClient, league_id: UUID, headers: dict[str, str]
) -> Callable[[Json], tuple[int, Json]]:
    def finish(tournament: Json) -> tuple[int, Json]:
        response = client.post(
            _t_url(league_id, tournament["id"], "/finish"),
            json={"expected_state": "in_progress"},
            headers=headers,
        )
        body: Json = response.json()
        return response.status_code, body

    return finish


def matches_of(tournament: Json) -> list[Json]:
    return [m for r in tournament["rounds"] for m in r["matches"]]


def field_matches(tournament: Json) -> list[str | None]:
    return [
        f["match_id"] for f in sorted(tournament["fields"], key=lambda f: f["number"])
    ]


def play_all(
    put_result: Callable[..., tuple[int, Json]], tournament: Json, body: Json = S1_WINS
) -> None:
    for match in matches_of(tournament):
        status, saved = put_result(tournament, match["id"], body)
        assert status == 200, saved


# ---------------------------------------------------------------- entering


def test_fr050_a_result_is_saved_with_its_games_and_time(
    start: Callable[..., Json],
    put_result: Callable[..., tuple[int, Json]],
    players: list[str],
    now: datetime,
) -> None:
    tournament = start(players[:4])
    match = tournament["rounds"][0]["matches"][0]

    status, body = put_result(tournament, match["id"], S1_WINS)

    assert status == 200, body
    assert body["id"] == match["id"]
    assert body["outcome"] == "side_1"
    assert body["is_walkover"] is False
    assert body["games"] == [
        {"game_no": 1, "winner": "side_1", "score_1": 10, "score_2": 7}
    ]
    assert datetime.fromisoformat(body["result_entered_at"]) == now
    assert body["sides"] == match["sides"]


def test_fr094_a_result_frees_the_field_for_the_next_waiting_match(
    start: Callable[..., Json],
    put_result: Callable[..., tuple[int, Json]],
    read: Callable[[Json, str], Json],
    players: list[str],
) -> None:
    tournament = start(players[:4])
    on_field = field_matches(tournament)[0]
    first_waiting = tournament["waiting"][0]

    put_result(tournament, on_field, S1_WINS)

    after = read(tournament, "")
    assert field_matches(after) == [first_waiting]
    assert on_field not in after["waiting"]
    assert after["waiting"] == tournament["waiting"][1:]


def test_fr094_a_waiting_match_with_a_result_never_takes_a_field(
    start: Callable[..., Json],
    put_result: Callable[..., tuple[int, Json]],
    read: Callable[[Json, str], Json],
    players: list[str],
) -> None:
    tournament = start(players[:4])
    waiting = tournament["waiting"][0]

    put_result(tournament, waiting, S1_WINS)

    after = read(tournament, "")
    assert field_matches(after) == field_matches(tournament)
    assert waiting not in after["waiting"]


def test_fr053_a_result_is_replaced_whole(
    start: Callable[..., Json],
    put_result: Callable[..., tuple[int, Json]],
    players: list[str],
) -> None:
    tournament = start(players[:2], group_match_format="bo3")
    match_id = matches_of(tournament)[0]["id"]
    put_result(tournament, match_id, games(game("side_1"), game("side_1")))

    status, body = put_result(
        tournament,
        match_id,
        games(game("side_2", 3, 10), game("side_1", 10, 8), game("side_2", 9, 11)),
    )

    assert status == 200, body
    assert body["outcome"] == "side_2"
    assert [(g["game_no"], g["winner"]) for g in body["games"]] == [
        (1, "side_2"),
        (2, "side_1"),
        (3, "side_2"),
    ]


def test_adr008_a_repeated_result_changes_nothing(
    start: Callable[..., Json],
    put_result: Callable[..., tuple[int, Json]],
    travel: Callable[[timedelta], datetime],
    players: list[str],
    now: datetime,
) -> None:
    tournament = start(players[:2])
    match_id = matches_of(tournament)[0]["id"]
    put_result(tournament, match_id, S1_WINS)
    travel(timedelta(minutes=5))

    status, body = put_result(tournament, match_id, S1_WINS)

    assert status == 200
    assert datetime.fromisoformat(body["result_entered_at"]) == now


def test_d7_a_changed_result_takes_the_new_time(
    start: Callable[..., Json],
    put_result: Callable[..., tuple[int, Json]],
    travel: Callable[[timedelta], datetime],
    players: list[str],
) -> None:
    tournament = start(players[:2])
    match_id = matches_of(tournament)[0]["id"]
    put_result(tournament, match_id, S1_WINS)
    later = travel(timedelta(minutes=5))

    _, body = put_result(tournament, match_id, games(game("side_2")))

    assert datetime.fromisoformat(body["result_entered_at"]) == later
    assert body["games"] == [
        {"game_no": 1, "winner": "side_2", "score_1": None, "score_2": None}
    ]


def test_fr052_a_walkover_has_a_winner_and_no_games(
    start: Callable[..., Json],
    put_result: Callable[..., tuple[int, Json]],
    players: list[str],
) -> None:
    tournament = start(players[:2], group_match_format="bo3")
    match_id = matches_of(tournament)[0]["id"]

    status, body = put_result(
        tournament, match_id, {"walkover_winner": "side_2", "games": []}
    )

    assert status == 200, body
    assert (body["outcome"], body["is_walkover"], body["games"]) == ("side_2", True, [])


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            {"walkover_winner": "side_1", "games": [game("side_1")]}, id="games"
        ),
        pytest.param({"walkover_winner": "draw", "games": []}, id="draw"),
        pytest.param(games(*[game("side_1")] * 6), id="six-games"),
        pytest.param(games(game("side_1", -1, -2)), id="negative-score"),
    ],
)
def test_br124_a_malformed_result_is_a_validation_error(
    start: Callable[..., Json],
    put_result: Callable[..., tuple[int, Json]],
    players: list[str],
    body: Json,
) -> None:
    tournament = start(players[:2])

    status, error = put_result(tournament, matches_of(tournament)[0]["id"], body)

    assert status == 422
    assert error["code"] == "validation_failed"


@pytest.mark.parametrize(
    ("values", "body", "code", "detail"),
    [
        pytest.param(
            {"group_match_format": "bo3"},
            games(game("side_1")),
            "result_does_not_fit_format",
            {"format": "bo3", "games": 1},
            id="BR-121-undecided",
        ),
        pytest.param(
            {},
            games(game("side_1"), game("side_1")),
            "result_does_not_fit_format",
            {"format": "bo1", "games": 2},
            id="BR-121-two-games",
        ),
        pytest.param(
            {}, games(game("draw", 5, 5)), "draws_not_allowed", {}, id="BR-090"
        ),
        pytest.param(
            {},
            games(game("side_1", 3, 10)),
            "game_score_mismatch",
            {"game_no": 1},
            id="BR-092",
        ),
        pytest.param(
            {},
            games(game("side_1", 10, None)),
            "game_score_mismatch",
            {"game_no": 1},
            id="BR-092-one-score",
        ),
    ],
)
def test_br090_br092_br121_a_result_that_breaks_a_rule_is_refused(
    start: Callable[..., Json],
    put_result: Callable[..., tuple[int, Json]],
    read: Callable[[Json, str], Json],
    players: list[str],
    values: Json,
    body: Json,
    code: str,
    detail: Json,
) -> None:
    tournament = start(players[:2], **values)
    match_id = matches_of(tournament)[0]["id"]

    status, error = put_result(tournament, match_id, body)

    assert status == 422
    assert error == {"code": code, "detail": detail}
    assert matches_of(read(tournament, ""))[0]["outcome"] is None


def test_br090_a_league_with_draws_records_a_drawn_bo2(
    start: Callable[..., Json],
    put_result: Callable[..., tuple[int, Json]],
    league: League,
    session: Session,
    players: list[str],
) -> None:
    league.draws_allowed = True
    session.flush()
    tournament = start(players[:2], group_match_format="bo2")

    status, body = put_result(
        tournament,
        matches_of(tournament)[0]["id"],
        games(game("side_1", 10, 4), game("side_2", 6, 10)),
    )

    assert status == 200, body
    assert body["outcome"] == "draw"


def test_owasp_api1_a_match_of_another_tournament_is_not_found(
    start: Callable[..., Json],
    put_result: Callable[..., tuple[int, Json]],
    players: list[str],
) -> None:
    tournament = start(players[:2])
    other = start(players[2:4])

    status, error = put_result(tournament, matches_of(other)[0]["id"], S1_WINS)

    assert status == 404
    assert error == {"code": "match_not_found", "detail": {}}


def test_br011_a_result_in_a_closed_season_is_a_conflict(
    start: Callable[..., Json],
    put_result: Callable[..., tuple[int, Json]],
    finish: Callable[[Json], tuple[int, Json]],
    session: Session,
    players: list[str],
    now: datetime,
) -> None:
    tournament = start(players[:2])
    play_all(put_result, tournament)
    finish(tournament)
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

    status, error = put_result(tournament, matches_of(tournament)[0]["id"], EMPTY)

    assert status == 409
    assert error == {"code": "season_closed", "detail": {}}


# ---------------------------------------------------------------- clearing


def test_br134_a_cleared_match_waits_in_schedule_order_and_takes_a_free_field(
    start: Callable[..., Json],
    put_result: Callable[..., tuple[int, Json]],
    read: Callable[[Json, str], Json],
    players: list[str],
) -> None:
    tournament = start(players[:2], field_count=2)
    match_id = matches_of(tournament)[0]["id"]
    put_result(tournament, match_id, S1_WINS)
    assert field_matches(read(tournament, "")) == [None, None]

    status, body = put_result(tournament, match_id, EMPTY)

    assert status == 200, body
    assert (body["outcome"], body["games"], body["result_entered_at"]) == (
        None,
        [],
        None,
    )
    after = read(tournament, "")
    assert field_matches(after) == [match_id, None]
    assert after["waiting"] == []


def test_br134_a_cleared_match_waits_at_its_place_while_the_fields_are_busy(
    start: Callable[..., Json],
    put_result: Callable[..., tuple[int, Json]],
    read: Callable[[Json, str], Json],
    players: list[str],
) -> None:
    tournament = start(players[:4], field_count=1)
    first, second = tournament["rounds"][0]["matches"]
    put_result(tournament, first["id"], S1_WINS)  # the field takes the second match
    assert field_matches(read(tournament, "")) == [second["id"]]

    put_result(tournament, first["id"], EMPTY)

    after = read(tournament, "")
    assert field_matches(after) == [second["id"]]
    assert after["waiting"][0] == first["id"]


def test_br131_a_cleared_match_whose_players_are_on_a_field_waits(
    start: Callable[..., Json],
    put_result: Callable[..., tuple[int, Json]],
    read: Callable[[Json, str], Json],
    players: list[str],
) -> None:
    tournament = start(players[:3], field_count=2)
    played = field_matches(tournament)[0]
    put_result(tournament, played, S1_WINS)  # every other match shares a player
    on_field = field_matches(read(tournament, ""))
    assert on_field[0] is not None
    assert on_field[1] is None

    put_result(tournament, played, EMPTY)

    after = read(tournament, "")
    assert field_matches(after) == on_field
    assert after["waiting"][0] == played


def test_fr053_clearing_a_match_without_a_result_changes_nothing(
    start: Callable[..., Json],
    put_result: Callable[..., tuple[int, Json]],
    read: Callable[[Json, str], Json],
    players: list[str],
) -> None:
    tournament = start(players[:4])
    on_field = field_matches(tournament)[0]

    status, body = put_result(tournament, on_field, EMPTY)

    assert status == 200
    assert body["outcome"] is None
    assert field_matches(read(tournament, "")) == [on_field]


def test_br134_clearing_in_a_finished_tournament_puts_the_match_on_a_free_field(
    start: Callable[..., Json],
    put_result: Callable[..., tuple[int, Json]],
    finish: Callable[[Json], tuple[int, Json]],
    read: Callable[[Json, str], Json],
    players: list[str],
) -> None:
    tournament = start(players[:2], field_count=2)
    play_all(put_result, tournament)
    finish(tournament)
    match_id = matches_of(tournament)[0]["id"]

    put_result(tournament, match_id, EMPTY)

    after = read(tournament, "")
    assert after["state"] == "in_progress"
    assert field_matches(after) == [match_id, None]
    assert after["waiting"] == []


def test_br095_clearing_a_result_puts_a_finished_tournament_back_in_progress(
    start: Callable[..., Json],
    put_result: Callable[..., tuple[int, Json]],
    finish: Callable[[Json], tuple[int, Json]],
    read: Callable[[Json, str], Json],
    players: list[str],
) -> None:
    tournament = start(players[:2])
    play_all(put_result, tournament)
    finish(tournament)

    put_result(tournament, matches_of(tournament)[0]["id"], EMPTY)

    after = read(tournament, "")
    assert after["state"] == "in_progress"
    assert after["current_phase_done"] is False
    assert read(tournament, "/places") == {"complete": False, "rows": []}


def test_br112_changing_a_result_keeps_the_tournament_finished(
    start: Callable[..., Json],
    put_result: Callable[..., tuple[int, Json]],
    finish: Callable[[Json], tuple[int, Json]],
    read: Callable[[Json, str], Json],
    players: list[str],
) -> None:
    tournament = start(players[:2])
    play_all(put_result, tournament)
    finish(tournament)
    match = matches_of(tournament)[0]
    winner = match["sides"][1]["entry_id"]

    put_result(tournament, match["id"], games(game("side_2")))

    assert read(tournament, "")["state"] == "finished"
    places = read(tournament, "/places")["rows"]
    assert (places[0]["place"], places[0]["entry_id"]) == (1, winner)


# ---------------------------------------------------------------- play read


def test_fr060_the_play_read_ranks_the_round_robin(
    start: Callable[..., Json],
    put_result: Callable[..., tuple[int, Json]],
    read: Callable[[Json, str], Json],
    players: list[str],
) -> None:
    tournament = start(players[:4])
    first = tournament["rounds"][0]["matches"]
    put_result(tournament, first[0]["id"], S1_WINS)
    put_result(tournament, first[1]["id"], games(game("side_2", 0, 10)))

    play = read(tournament, "/play")

    winner_1, loser_1 = (s["entry_id"] for s in first[0]["sides"])
    loser_2, winner_2 = (s["entry_id"] for s in first[1]["sides"])
    rows = play["standings"]
    assert [row["entry_id"] for row in rows] == [winner_2, winner_1, loser_1, loser_2]
    assert [row["place"] for row in rows] == [1, 2, 3, 4]
    assert rows[0] | {"form": None} == {
        "place": 1,
        "entry_id": winner_2,
        "played": 1,
        "won": 1,
        "drawn": 0,
        "lost": 0,
        "sat_out": 0,
        "points": 2,
        "score_difference": 10,
        "form": None,
        "ahead_by": "score_difference",
        "bh1": None,
        "bh2": None,
    }
    assert rows[0]["form"] == ["won"]
    assert rows[2]["form"] == ["lost"]
    assert play["group_done"] is False


def test_br071_a_sit_out_counts_once_its_round_is_complete(
    start: Callable[..., Json],
    put_result: Callable[..., tuple[int, Json]],
    read: Callable[[Json, str], Json],
    players: list[str],
) -> None:
    tournament = start(players[:3], sit_out_points=1)
    first = tournament["rounds"][0]
    sitter = first["sitting_out"][0]
    before = {row["entry_id"]: row for row in read(tournament, "/play")["standings"]}

    put_result(tournament, first["matches"][0]["id"], S1_WINS)

    after = {row["entry_id"]: row for row in read(tournament, "/play")["standings"]}
    assert (before[sitter]["sat_out"], before[sitter]["points"]) == (0, 0)
    assert (after[sitter]["sat_out"], after[sitter]["points"]) == (1, 1)


def test_br131_a_waiting_match_names_the_field_its_players_are_on(
    start: Callable[..., Json],
    read: Callable[[Json, str], Json],
    players: list[str],
) -> None:
    tournament = start(players[:3], field_count=2)
    on_field = matches_of(tournament)[0]
    busy_players = {p for s in on_field["sides"] for p in s["player_ids"]}

    play = read(tournament, "/play")

    field_1 = tournament["fields"][0]
    assert field_matches(tournament) == [on_field["id"], None]
    assert [w["match_id"] for w in play["waiting"]] == tournament["waiting"]
    for waiting in play["waiting"]:
        match = next(
            m for m in matches_of(tournament) if m["id"] == waiting["match_id"]
        )
        shared = sorted(
            busy_players & {p for s in match["sides"] for p in s["player_ids"]}
        )
        assert waiting["busy"] == [{"field_id": field_1["id"], "player_ids": shared}]


def test_fr040_the_group_phase_is_done_once_every_match_has_a_result(
    start: Callable[..., Json],
    put_result: Callable[..., tuple[int, Json]],
    read: Callable[[Json, str], Json],
    players: list[str],
) -> None:
    tournament = start(players[:3])

    play_all(put_result, tournament)

    play = read(tournament, "/play")
    assert play["group_done"] is True
    assert play["waiting"] == []
    assert read(tournament, "")["current_phase_done"] is True


# ---------------------------------------------------------------- finishing


def test_fr040_finishing_turns_the_standings_into_places_and_points(
    start: Callable[..., Json],
    put_result: Callable[..., tuple[int, Json]],
    finish: Callable[[Json], tuple[int, Json]],
    read: Callable[[Json, str], Json],
    players: list[str],
) -> None:
    tournament = start(players[:3])
    play_all(put_result, tournament)
    standings = read(tournament, "/play")["standings"]

    status, body = finish(tournament)

    assert status == 200, body
    assert body["state"] == "finished"
    places = read(tournament, "/places")
    assert places["complete"] is True
    assert [(row["place"], row["entry_id"]) for row in places["rows"]] == [
        (row["place"], row["entry_id"]) for row in standings
    ]
    assert [row["points_per_player"] for row in places["rows"]] == [10, 8, 6]
    assert places["rows"][0]["reason"] == {
        "kind": "group_place",
        "round": None,
        "score": None,
        "opponent_entry_id": None,
        "group_place": 1,
        "group_format": "round_robin",
    }


def test_br111_entries_sharing_a_place_split_its_points(
    start: Callable[..., Json],
    put_result: Callable[..., tuple[int, Json]],
    finish: Callable[[Json], tuple[int, Json]],
    read: Callable[[Json, str], Json],
    league: League,
    session: Session,
    players: list[str],
) -> None:
    league.draws_allowed = True
    session.flush()
    tournament = start(players[:2])
    play_all(put_result, tournament, games(game("draw")))

    finish(tournament)

    rows = read(tournament, "/places")["rows"]
    # They cover 1st and 2nd of the default table: (10 + 8) / 2 = 9 each.
    assert [(row["place"], row["points_per_player"]) for row in rows] == [
        (1, 9),
        (1, 9),
    ]


def test_fr040_finishing_before_every_result_is_refused(
    start: Callable[..., Json],
    put_result: Callable[..., tuple[int, Json]],
    finish: Callable[[Json], tuple[int, Json]],
    players: list[str],
) -> None:
    tournament = start(players[:3])
    put_result(tournament, matches_of(tournament)[0]["id"], S1_WINS)

    status, error = finish(tournament)

    assert status == 422
    assert error == {"code": "group_phase_not_done", "detail": {"matches_left": 2}}


def test_adr008_finishing_twice_is_a_conflict(
    start: Callable[..., Json],
    put_result: Callable[..., tuple[int, Json]],
    finish: Callable[[Json], tuple[int, Json]],
    players: list[str],
) -> None:
    tournament = start(players[:2])
    play_all(put_result, tournament)
    finish(tournament)

    status, error = finish(tournament)

    assert status == 409
    assert error == {
        "code": "tournament_not_in_progress",
        "detail": {"state": "finished"},
    }


def test_fr040_a_tournament_in_progress_has_no_places_yet(
    start: Callable[..., Json],
    read: Callable[[Json, str], Json],
    players: list[str],
) -> None:
    tournament = start(players[:2])

    assert read(tournament, "/places") == {"complete": False, "rows": []}
