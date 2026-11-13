"""The Monster DYP group phase: the top players in setup, the start with round 1
and the standings (FR-041, FR-060, BR-060, BR-061, BR-063, BR-070, BR-072,
BR-075, BR-077).
"""

from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid7

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tourneyhub.db.models.entries import Entry, EntryMember
from tourneyhub.db.models.leagues import League, Player
from tourneyhub.db.models.matches import RoundParticipation
from tourneyhub.db.models.tournaments import Tournament
from tourneyhub.engine.tournaments import TournamentState

type Json = dict[str, Any]

MONSTER_DYP: Json = {
    "name": "Monster night",
    "date": "2026-11-12",
    "type": "monster_dyp",
    "group_phase": "monster_dyp",
    "round_robin_legs": None,
    "sit_out_points": 1,
    "group_match_format": "bo1",
    "knockout_match_format": None,
    "final_match_format": None,
    "third_place_match": None,
    "goals_per_game": 10,
    "field_count": 2,
}


def _t_url(league: League, tournament_id: str, rest: str = "") -> str:
    return f"/api/v1/leagues/{league.id}/tournaments/{tournament_id}{rest}"


@pytest.fixture
def league(make_league: Callable[..., League]) -> League:
    return make_league()


@pytest.fixture
def headers(
    league: League, auth_header: Callable[..., dict[str, str]]
) -> dict[str, str]:
    return auth_header(league.owner_user_id)


@pytest.fixture
def players(league: League, make_player: Callable[..., Player]) -> list[str]:
    return [str(make_player(league=league, name=f"P{n}").id) for n in range(1, 10)]


def _put(
    client: TestClient,
    league: League,
    tournament_id: str,
    what: str,
    body: Json,
    headers: dict[str, str],
) -> tuple[int, Json]:
    response = client.put(
        _t_url(league, tournament_id, what), json=body, headers=headers
    )
    result: Json = response.json()
    return response.status_code, result


def _monster(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    picked: list[str],
    **values: object,
) -> str:
    body = {"id": str(uuid7()), **MONSTER_DYP, **values}
    created = client.post(
        f"/api/v1/leagues/{league.id}/tournaments", json=body, headers=headers
    )
    assert created.status_code == 201, created.text
    tid: str = created.json()["tournament_id"]
    status, result = _put(
        client, league, tid, "/setup/players", {"player_ids": picked}, headers
    )
    assert status == 200, result
    return tid


def test_fr041_marks_top_players_as_a_target_state(
    client: TestClient,
    session: Session,
    league: League,
    headers: dict[str, str],
    players: list[str],
) -> None:
    tid = _monster(client, league, headers, players)
    a, b, c = players[:3]

    status, body = _put(
        client, league, tid, "/setup/top-players", {"player_ids": [a, b]}, headers
    )
    assert status == 200, body
    assert set(body["top_player_ids"]) == {a, b}

    status, body = _put(
        client, league, tid, "/setup/top-players", {"player_ids": [b, c]}, headers
    )
    assert status == 200, body
    assert set(body["top_player_ids"]) == {b, c}
    marked = session.scalars(
        select(EntryMember.player_id)
        .join(Entry, Entry.id == EntryMember.entry_id)
        .where(Entry.tournament_id == UUID(tid), Entry.is_top_player.is_(True))
    ).all()
    assert set(marked) == {UUID(b), UUID(c)}

    status, body = _put(
        client, league, tid, "/setup/top-players", {"player_ids": []}, headers
    )
    assert (status, body["top_player_ids"]) == (200, [])


def test_fr041_at_most_one_top_player_per_round_one_match(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    tid = _monster(client, league, headers, players)  # 9 players: 2 matches

    status, body = _put(
        client, league, tid, "/setup/top-players", {"player_ids": players[:3]}, headers
    )

    assert status == 422
    assert body == {"code": "too_many_top_players", "detail": {"max": 2}}


def test_fr041_top_players_must_be_tournament_players(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    players: list[str],
    make_player: Callable[..., Player],
) -> None:
    tid = _monster(client, league, headers, players[:8])
    outsider = str(make_player(league=league, name="Outsider").id)

    status, body = _put(
        client, league, tid, "/setup/top-players", {"player_ids": [outsider]}, headers
    )

    assert status == 409
    assert body["code"] == "player_not_picked"


def test_fr041_top_players_only_in_setup(
    client: TestClient,
    session: Session,
    league: League,
    headers: dict[str, str],
    players: list[str],
) -> None:
    tid = _monster(client, league, headers, players)
    session.get_one(Tournament, UUID(tid)).state = TournamentState.IN_PROGRESS
    session.flush()

    status, body = _put(
        client, league, tid, "/setup/top-players", {"player_ids": []}, headers
    )

    assert status == 409
    assert body["code"] == "tournament_not_in_setup"


def test_fr041_top_players_only_in_monster_dyp(
    client: TestClient, league: League, headers: dict[str, str]
) -> None:
    created = client.post(
        f"/api/v1/leagues/{league.id}/tournaments",
        json={
            "id": str(uuid7()),
            **MONSTER_DYP,
            "type": "singles",
            "group_phase": "swiss",
        },
        headers=headers,
    )
    tid: str = created.json()["tournament_id"]

    status, body = _put(
        client, league, tid, "/setup/top-players", {"player_ids": []}, headers
    )

    assert status == 409
    assert body["code"] == "tournament_type_changed"


# ---------------------------------------------------------------- start, round 1


@pytest.fixture
def twelve(league: League, make_player: Callable[..., Player]) -> list[str]:
    return [str(make_player(league=league, name=f"Q{n}").id) for n in range(1, 13)]


def _get(
    client: TestClient,
    league: League,
    tournament_id: str,
    rest: str,
    headers: dict[str, str],
) -> Json:
    response = client.get(_t_url(league, tournament_id, rest), headers=headers)
    assert response.status_code == 200, response.text
    result: Json = response.json()
    return result


def _start(
    client: TestClient, league: League, tournament_id: str, headers: dict[str, str]
) -> tuple[int, Json]:
    """Generate and start from what the review screen showed (FR-035, ADR-008)."""
    preview = _get(client, league, tournament_id, "/setup/preview", headers)
    response = client.post(
        _t_url(league, tournament_id, "/start"),
        json={
            "expected_draw_counter": preview["draw_counter"],
            "expected_seed_order": preview["seed_order"],
        },
        headers=headers,
    )
    result: Json = response.json()
    return response.status_code, result


def _started(
    client: TestClient, league: League, tournament_id: str, headers: dict[str, str]
) -> Json:
    status, tournament = _start(client, league, tournament_id, headers)
    assert status == 200, tournament
    return tournament


def _round(tournament: Json, round_no: int = 1) -> Json:
    return next(r for r in tournament["rounds"] if r["round_no"] == round_no)


def _teams(round_: Json) -> list[tuple[set[str], set[str]]]:
    """Each match's sides as sets of players: a team's order is not shown."""
    return [
        (set(m["sides"][0]["player_ids"]), set(m["sides"][1]["player_ids"]))
        for m in round_["matches"]
    ]


def _player_of(tournament: Json) -> dict[str, str]:
    """Each main entry's one player (DATA-MODEL §4.4)."""
    return {
        e["id"]: e["player_ids"][0]
        for e in tournament["entries"]
        if e["stage"] == "main"
    }


def _ranked(setup: Json) -> list[str]:
    """The picked players in league-ranking order, #1 first (BR-020)."""
    picked = set(setup["player_ids"])
    return [row["player_id"] for row in setup["ranking"] if row["player_id"] in picked]


def test_br060_round_one_groups_by_league_ranking(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    tid = _monster(client, league, headers, players[:8])
    r = _ranked(_get(client, league, tid, "/setup", headers))

    tournament = _started(client, league, tid, headers)

    # Two matches, so #1 and #2 are the top players, each leading a group, and
    # the others fill the groups in order (BR-061): #1 #3 #4 #5 · #2 #6 #7 #8.
    # In each group the 1st and 4th play the 2nd and 3rd (BR-060).
    round_ = _round(tournament)
    assert _teams(round_) == [
        ({r[0], r[4]}, {r[2], r[3]}),
        ({r[1], r[7]}, {r[5], r[6]}),
    ]
    assert round_["sitting_out"] == []
    assert all(
        side["entry_id"] is None for m in round_["matches"] for side in m["sides"]
    )
    assert tournament["state"] == "in_progress"


def test_br060_four_players_play_one_and_four_against_two_and_three(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    tid = _monster(client, league, headers, players[:4])
    r = _ranked(_get(client, league, tid, "/setup", headers))

    tournament = _started(client, league, tid, headers)

    assert _teams(_round(tournament)) == [({r[0], r[3]}, {r[1], r[2]})]


def test_br061_marked_top_players_lead_different_groups(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    tid = _monster(client, league, headers, players[:8])
    r = _ranked(_get(client, league, tid, "/setup", headers))
    status, body = _put(
        client, league, tid, "/setup/top-players", {"player_ids": [r[7], r[6]]}, headers
    )
    assert status == 200, body

    tournament = _started(client, league, tid, headers)

    # The marked #7 and #8 lead the groups in league-ranking order; the others
    # fill them in standing order: #7 #1 #2 #3 · #8 #4 #5 #6.
    assert _teams(_round(tournament)) == [
        ({r[6], r[2]}, {r[0], r[1]}),
        ({r[7], r[5]}, {r[3], r[4]}),
    ]


def test_br061_more_marks_than_matches_at_start_uses_one_per_match(
    client: TestClient, league: League, headers: dict[str, str], twelve: list[str]
) -> None:
    tid = _monster(client, league, headers, twelve)
    r = _ranked(_get(client, league, tid, "/setup", headers))
    marked = [r[11], r[9], r[10]]
    status, body = _put(
        client, league, tid, "/setup/top-players", {"player_ids": marked}, headers
    )
    assert status == 200, body
    kept = [p for p in twelve if p not in r[:4]]  # 8 players: 2 matches
    status, body = _put(
        client, league, tid, "/setup/players", {"player_ids": kept}, headers
    )
    assert status == 200, body
    assert set(body["top_player_ids"]) == set(marked)

    tournament = _started(client, league, tid, headers)

    # The marked players count in league-ranking order: #10 and #11 are the
    # top players, one per match; #12 plays as an ordinary player (BR-061).
    teams = _teams(_round(tournament))
    assert len(teams) == 2
    assert [r[9] in a | b for a, b in teams] == [True, False]
    assert [r[10] in a | b for a, b in teams] == [False, True]


def test_br061_removed_marked_player_loses_the_mark(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    tid = _monster(client, league, headers, players[:8])
    a, b = players[:2]
    _put(client, league, tid, "/setup/top-players", {"player_ids": [a, b]}, headers)

    status, body = _put(
        client, league, tid, "/setup/players", {"player_ids": players[1:8]}, headers
    )
    assert (status, body["top_player_ids"]) == (200, [b])
    status, body = _put(
        client, league, tid, "/setup/players", {"player_ids": players[:8]}, headers
    )

    assert (status, body["top_player_ids"]) == (200, [b])
    tournament = _started(client, league, tid, headers)
    assert [e["is_top_player"] for e in tournament["entries"]].count(True) == 1


def test_br063_extra_players_sit_out(
    client: TestClient, league: League, headers: dict[str, str], twelve: list[str]
) -> None:
    tid = _monster(client, league, headers, twelve[:10])

    tournament = _started(client, league, tid, headers)

    round_ = _round(tournament)
    player_of = _player_of(tournament)
    playing = set().union(*(a | b for a, b in _teams(round_)))
    out = {player_of[entry_id] for entry_id in round_["sitting_out"]}
    assert len(round_["matches"]) == 2
    assert len(round_["sitting_out"]) == 2
    assert len(playing) == 8
    assert playing | out == set(twelve[:10])


def test_br063_every_main_entry_has_one_participation_row(
    client: TestClient,
    session: Session,
    league: League,
    headers: dict[str, str],
    twelve: list[str],
) -> None:
    tid = _monster(client, league, headers, twelve[:10])

    tournament = _started(client, league, tid, headers)

    rows = session.execute(
        select(RoundParticipation.entry_id, RoundParticipation.status).where(
            RoundParticipation.round_id == UUID(_round(tournament)["id"])
        )
    ).all()
    status = {str(entry_id): value.value for entry_id, value in rows}
    out = set(_round(tournament)["sitting_out"])
    assert status == {
        entry_id: "sat_out" if entry_id in out else "played"
        for entry_id in _player_of(tournament)
    }


def test_br060_setup_preview_shows_round_one(
    client: TestClient, league: League, headers: dict[str, str], twelve: list[str]
) -> None:
    tid = _monster(client, league, headers, twelve[:10])
    setup = _get(client, league, tid, "/setup", headers)

    preview = _get(client, league, tid, "/setup/preview", headers)
    tournament = _started(client, league, tid, headers)

    assert preview["can_start"] is True
    assert preview["problem"] is None
    assert (preview["match_count"], preview["round_count"]) == (None, None)
    assert preview["bracket_size"] is None
    # The order round 1 is drawn from: the entries by league ranking (BR-060).
    entry_of = {e["player_ids"][0]: e["id"] for e in setup["entries"]}
    assert preview["seed_order"] == [entry_of[p] for p in _ranked(setup)]
    [shown] = preview["rounds"]
    assert shown["round_no"] == 1
    assert shown["byes"] == []
    assert all(len(out) == 1 for out in shown["sitting_out"])
    round_ = _round(tournament)
    assert [
        (set(m["sides"][0]), set(m["sides"][1])) for m in shown["matches"]
    ] == _teams(round_)
    player_of = _player_of(tournament)
    assert sorted(out[0] for out in shown["sitting_out"]) == sorted(
        player_of[entry_id] for entry_id in round_["sitting_out"]
    )


def test_br060_a_changed_ranking_is_a_stale_start(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    tid = _monster(client, league, headers, players[:8])
    preview = _get(client, league, tid, "/setup/preview", headers)

    response = client.post(
        _t_url(league, tid, "/start"),
        json={
            "expected_draw_counter": preview["draw_counter"],
            "expected_seed_order": preview["seed_order"][::-1],
        },
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["code"] == "seed_order_changed"


def test_fr032_a_monster_dyp_needs_four_players(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    tid = _monster(client, league, headers, players[:3])

    preview = _get(client, league, tid, "/setup/preview", headers)
    status, body = _start(client, league, tid, headers)

    refusal = {"code": "not_enough_entries", "detail": {"minimum": 4, "given": 3}}
    assert (status, body) == (422, refusal)
    assert preview["problem"] == refusal


# ---------------------------------------------------------------- standings


def win(side: str, score: tuple[int, int] = (10, 5)) -> Json:
    """A BO1 result with a score, which a Monster DYP requires (BR-092)."""
    winner, loser = score
    scores = (winner, loser) if side == "side_1" else (loser, winner)
    return {
        "walkover_winner": None,
        "games": [{"winner": side, "score_1": scores[0], "score_2": scores[1]}],
    }


DRAW: Json = {
    "walkover_winner": None,
    "games": [{"winner": "draw", "score_1": 5, "score_2": 5}],
}


def _result(
    client: TestClient,
    league: League,
    tournament_id: str,
    match_id: str,
    body: Json,
    headers: dict[str, str],
) -> None:
    response = client.put(
        _t_url(league, tournament_id, f"/matches/{match_id}/result"),
        json=body,
        headers=headers,
    )
    assert response.status_code == 200, response.text


def _standings(play: Json, tournament: Json) -> dict[str, Json]:
    """The standings by player."""
    player_of = _player_of(tournament)
    return {player_of[row["entry_id"]]: row for row in play["standings"]}


def test_br077_sit_out_points_count_right_after_the_draw(
    client: TestClient, league: League, headers: dict[str, str], twelve: list[str]
) -> None:
    tid = _monster(client, league, headers, twelve[:10], sit_out_points=2)
    tournament = _started(client, league, tid, headers)

    play = _get(client, league, tid, "/play", headers)

    out = set(_round(tournament)["sitting_out"])
    points = {
        row["entry_id"]: (row["points"], row["sat_out"]) for row in play["standings"]
    }
    assert points == {
        entry_id: (2, 1) if entry_id in out else (0, 0)
        for entry_id in _player_of(tournament)
    }
    assert play["group_done"] is False


def test_br075_sit_out_points_locked_after_first_result(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    tid = _monster(client, league, headers, players[:9], sit_out_points=2)
    tournament = _started(client, league, tid, headers)
    match = _round(tournament)["matches"][0]
    _result(client, league, tid, match["id"], win("side_1"), headers)

    refused = client.put(
        _t_url(league, tid, "/format"),
        json={**MONSTER_DYP, "sit_out_points": 0},
        headers=headers,
    )
    back = client.post(
        _t_url(league, tid, "/back-to-setup"),
        json={"expected_state": "in_progress"},
        headers=headers,
    )

    assert refused.status_code == 409
    assert refused.json()["code"] == "tournament_not_in_setup"
    assert back.status_code == 422
    assert back.json()["code"] == "tournament_has_results"
    phases = _get(client, league, tid, "", headers)["phases"]
    assert [p["sit_out_points"] for p in phases] == [2]


def test_br070_both_team_members_get_the_points(
    client: TestClient,
    session: Session,
    league: League,
    headers: dict[str, str],
    players: list[str],
) -> None:
    league.draws_allowed = True
    session.flush()
    tid = _monster(client, league, headers, players[:8])
    tournament = _started(client, league, tid, headers)
    first, second = _round(tournament)["matches"]
    _result(client, league, tid, first["id"], win("side_1"), headers)
    _result(client, league, tid, second["id"], DRAW, headers)

    rows = _standings(_get(client, league, tid, "/play", headers), tournament)

    points = {
        **dict.fromkeys(first["sides"][0]["player_ids"], (2, 1, 0, 0)),
        **dict.fromkeys(first["sides"][1]["player_ids"], (0, 0, 0, 1)),
        **dict.fromkeys(
            second["sides"][0]["player_ids"] + second["sides"][1]["player_ids"],
            (1, 0, 1, 0),
        ),
    }
    assert {
        p: (row["points"], row["won"], row["drawn"], row["lost"])
        for p, row in rows.items()
    } == points
    assert all(row["played"] == 1 for row in rows.values())


def test_br101_a_walkover_counts_the_games_needed_to_win(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    tid = _monster(client, league, headers, players[:4], group_match_format="bo3")
    tournament = _started(client, league, tid, headers)
    [match] = _round(tournament)["matches"]
    walkover = {"walkover_winner": "side_2", "games": []}
    _result(client, league, tid, match["id"], walkover, headers)

    rows = _standings(_get(client, league, tid, "/play", headers), tournament)

    # A BO3 walkover counts as 2:0 games; it has no score (BR-073, BR-101).
    side_1, side_2 = (side["player_ids"] for side in match["sides"])
    assert {p: rows[p]["game_difference"] for p in side_1 + side_2} == {
        **dict.fromkeys(side_1, -2),
        **dict.fromkeys(side_2, 2),
    }
    assert {rows[p]["score_difference"] for p in side_1 + side_2} == {0}
    assert {rows[p]["points"] for p in side_2} == {2}


def test_br072_tiebreakers_follow_the_organizers_order(
    client: TestClient, league: League, headers: dict[str, str], twelve: list[str]
) -> None:
    tid = _monster(client, league, headers, twelve[:10], sit_out_points=0)
    tournament = _started(client, league, tid, headers)
    for match in _round(tournament)["matches"]:
        _result(client, league, tid, match["id"], win("side_1"), headers)
    round_ = _round(tournament)
    losers = {p for m in round_["matches"] for p in m["sides"][1]["player_ids"]}
    out = {_player_of(tournament)[e] for e in round_["sitting_out"]}

    def places(order: list[str]) -> dict[str, int]:
        status, body = _put(
            client, league, tid, "/tiebreakers", {"tiebreakers": order}, headers
        )
        assert status == 200, body
        rows = _standings(_get(client, league, tid, "/play", headers), tournament)
        return {p: rows[p]["place"] for p in losers | out}

    # The losers and the sit-outs are level on 0 points. The losers lead on
    # BH1 (their opponents won), the sit-outs on score difference (0 to -5).
    by_bh1 = places(["bh1", "score_difference"])
    by_score = places(["score_difference", "bh1"])

    assert by_bh1 == {**dict.fromkeys(losers, 5), **dict.fromkeys(out, 9)}
    assert by_score == {**dict.fromkeys(out, 5), **dict.fromkeys(losers, 7)}


def test_fr060_monster_dyp_standings_on_play_and_share_link(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    tid = _monster(client, league, headers, players[:9])
    tournament = _started(client, league, tid, headers)
    for match in _round(tournament)["matches"]:
        _result(client, league, tid, match["id"], win("side_1", (10, 4)), headers)

    play = _get(client, league, tid, "/play", headers)
    shared = client.get(
        f"/api/v1/public/{league.share_token}/tournaments/{tid}/standings"
    )

    # One row per player's main entry, best first.
    assert len(play["standings"]) == 9
    assert {row["entry_id"] for row in play["standings"]} == set(_player_of(tournament))
    # The sit-out's 1 point puts them between the winners and the losers.
    assert [row["place"] for row in play["standings"]] == [1] * 4 + [5] + [6] * 4
    winner, out, loser = (play["standings"][i] for i in (0, 4, 5))
    assert {k: winner[k] for k in ("played", "won", "points", "bh1", "bh2")} == {
        "played": 1,
        "won": 1,
        "points": 2,
        "bh1": 0,
        "bh2": 8,
    }
    assert (winner["score_difference"], winner["game_difference"]) == (6, 1)
    assert (loser["bh1"], loser["bh2"], loser["score_difference"]) == (4, 0, -6)
    assert loser["game_difference"] == -1
    assert (out["sat_out"], out["points"], out["played"]) == (1, 1, 0)
    assert all(
        row["form"] == [] and row["ahead_by"] is None for row in play["standings"]
    )
    assert play["group_done"] is True
    assert shared.status_code == 200
    assert shared.json() == [
        {k: v for k, v in row.items() if k not in {"form", "ahead_by"}}
        for row in play["standings"]
    ]


def test_monster_dyp_round_reads_without_errors(
    client: TestClient, league: League, headers: dict[str, str], twelve: list[str]
) -> None:
    tid = _monster(client, league, headers, twelve[:10])
    tournament = _started(client, league, tid, headers)
    on_field = next(f for f in tournament["fields"] if f["match_id"] is not None)

    placed = [
        client.put(
            _t_url(league, tid, "/fields/placements"),
            json={"placements": [placement]},
            headers=headers,
        )
        for placement in (
            {
                "match_id": on_field["match_id"],
                "field_id": None,
                "from_field_id": on_field["id"],
            },
            {
                "match_id": on_field["match_id"],
                "field_id": on_field["id"],
                "from_field_id": None,
            },
        )
    ]
    for match in _round(tournament)["matches"]:
        _result(client, league, tid, match["id"], win("side_2"), headers)

    public = f"/api/v1/public/{league.share_token}"
    season_id = tournament["season_id"]
    reads = [
        client.get(_t_url(league, tid), headers=headers),
        client.get(_t_url(league, tid, "/play"), headers=headers),
        client.get(public),
        client.get(f"{public}/seasons/{season_id}/tournaments"),
        client.get(f"{public}/tournaments/{tid}"),
        client.get(f"{public}/tournaments/{tid}/standings"),
        client.get(f"{public}/seasons/{season_id}/standings"),
    ]

    assert [r.status_code for r in placed] == [200, 200], [r.text for r in placed]
    assert [r.status_code for r in reads] == [200] * len(reads), [r.text for r in reads]
