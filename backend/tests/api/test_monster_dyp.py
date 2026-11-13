"""The Monster DYP group phase: the top players in setup, the start with round 1,
the standings, and adding and deleting rounds (FR-041, FR-046, FR-060, BR-060 to
BR-064, BR-070, BR-072, BR-075, BR-077).
"""

from collections.abc import Callable, Sequence
from typing import Any
from uuid import UUID, uuid7

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tourneyhub.db.models.entries import Entry, EntryMember
from tourneyhub.db.models.leagues import League, Player
from tourneyhub.db.models.matches import RoundParticipation
from tourneyhub.db.models.tournaments import Tournament, TournamentPhase
from tourneyhub.engine.monster_dyp import MonsterDraw
from tourneyhub.engine.ranking import RankedPlayer
from tourneyhub.engine.tournaments import TournamentState
from tourneyhub.services.tournaments import rounds as rounds_service
from tourneyhub.services.tournaments.monster_dyp import draw_monster

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


def test_adr008_changed_marks_make_the_start_stale(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    tid = _monster(client, league, headers, players[:8])
    _put(
        client, league, tid, "/setup/top-players", {"player_ids": [players[0]]}, headers
    )
    preview = _get(client, league, tid, "/setup/preview", headers)

    status, _ = _put(
        client, league, tid, "/setup/top-players", {"player_ids": [players[1]]}, headers
    )
    response = client.post(
        _t_url(league, tid, "/start"),
        json={
            "expected_draw_counter": preview["draw_counter"],
            "expected_seed_order": preview["seed_order"],
        },
        headers=headers,
    )

    assert status == 200
    assert response.status_code == 409
    assert response.json()["code"] == "draw_counter_changed"


def test_fr041_same_marks_twice_keep_the_draw_counter(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    tid = _monster(client, league, headers, players[:8])
    body = {"player_ids": [players[0], players[1]]}
    _put(client, league, tid, "/setup/top-players", body, headers)
    first = _get(client, league, tid, "/setup/preview", headers)["draw_counter"]

    status, _ = _put(client, league, tid, "/setup/top-players", body, headers)

    assert status == 200
    assert _get(client, league, tid, "/setup/preview", headers)["draw_counter"] == first


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


def test_fr060_monster_dyp_in_setup_has_zero_standings(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    tid = _monster(client, league, headers, players[:9])

    play = _get(client, league, tid, "/play", headers)

    assert len(play["standings"]) == 9
    assert all(
        row[k] == 0
        for row in play["standings"]
        for k in ("played", "won", "points", "sat_out", "score_difference")
    )


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
        client.get(f"{public}/seasons/{tournament['season_id']}/standings"),
    ]

    assert [r.status_code for r in placed] == [200, 200], [r.text for r in placed]
    assert [r.status_code for r in reads] == [200] * len(reads), [r.text for r in reads]


# ---------------------------------------------------------------- rounds


@pytest.fixture
def disable(session: Session) -> Callable[[str], None]:
    def disable(entry_id: str) -> None:
        """Disable an entry; its route comes with P14 (FR-044)."""
        session.get_one(Entry, UUID(entry_id)).is_disabled = True
        session.flush()

    return disable


def _add_round(
    client: TestClient,
    league: League,
    tournament_id: str,
    expected_round_no: int,
    headers: dict[str, str],
) -> tuple[int, Json]:
    response = client.post(
        _t_url(league, tournament_id, "/rounds"),
        json={"expected_round_no": expected_round_no},
        headers=headers,
    )
    result: Json = response.json()
    return response.status_code, result


def _next_round(
    client: TestClient,
    league: League,
    tournament_id: str,
    round_no: int,
    headers: dict[str, str],
) -> Json:
    status, body = _add_round(client, league, tournament_id, round_no, headers)
    assert status == 201, body
    assert body["round_no"] == round_no
    return body


def _play_round(
    client: TestClient,
    league: League,
    tournament_id: str,
    round_: Json,
    headers: dict[str, str],
) -> None:
    """Side 1 wins every match of the round, by a score that differs per match."""
    for index, match in enumerate(round_["matches"]):
        _result(
            client,
            league,
            tournament_id,
            match["id"],
            win("side_1", (10, 1 + index)),
            headers,
        )


def _groups(round_: Json) -> list[set[str]]:
    """The four players of each match."""
    return [a | b for a, b in _teams(round_)]


def _partners(round_: Json) -> list[frozenset[str]]:
    return [frozenset(team) for pair in _teams(round_) for team in pair]


def _delete_round(
    client: TestClient,
    league: League,
    tournament_id: str,
    round_id: str,
    headers: dict[str, str],
) -> tuple[int, Json]:
    response = client.delete(
        _t_url(league, tournament_id, f"/rounds/{round_id}"), headers=headers
    )
    return response.status_code, response.json() if response.content else {}


def test_br060_later_rounds_group_by_standing(
    client: TestClient, league: League, headers: dict[str, str], twelve: list[str]
) -> None:
    tid = _monster(client, league, headers, twelve)
    r = _ranked(_get(client, league, tid, "/setup", headers))
    tournament = _started(client, league, tid, headers)
    _play_round(client, league, tid, _round(tournament), headers)
    play = _get(client, league, tid, "/play", headers)
    player_of = _player_of(tournament)
    order = [player_of[row["entry_id"]] for row in play["standings"]]

    two = _next_round(client, league, tid, 2, headers)

    # Round 2 keeps the top players of the league ranking apart (BR-061) and
    # fills the groups from the standings, best first (BR-060): the best-placed
    # of the others joins the first top player, the worst-placed the last. The
    # swaps of BR-062 move a player only when a partner would repeat.
    others = [p for p in order if p not in r[:3]]
    groups = _groups(two)
    assert sorted(len(g) for g in groups) == [4, 4, 4]
    assert {next(iter(g & set(r[:3]))) for g in groups} == set(r[:3])
    assert {p for g in groups for p in g} == set(twelve)
    first = next(g for g in groups if r[0] in g)
    last = next(g for g in groups if r[2] in g)
    assert others[0] in first
    assert others[-1] in last


def test_br061_top_players_apart_in_round_two(
    client: TestClient, league: League, headers: dict[str, str], twelve: list[str]
) -> None:
    tid = _monster(client, league, headers, twelve)
    r = _ranked(_get(client, league, tid, "/setup", headers))
    marked = [r[11], r[7]]
    _put(client, league, tid, "/setup/top-players", {"player_ids": marked}, headers)
    tournament = _started(client, league, tid, headers)
    _play_round(client, league, tid, _round(tournament), headers)

    two = _next_round(client, league, tid, 2, headers)

    # 3 matches: the marked #12 and #8 first, then #1 (BR-061).
    tops = {r[11], r[7], r[0]}
    assert sorted(len(g & tops) for g in _groups(two)) == [1, 1, 1]


def test_br061_round_two_uses_the_league_ranking_of_now(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    league: League,
    headers: dict[str, str],
    players: list[str],
) -> None:
    tid = _monster(client, league, headers, players[:8])
    tournament = _started(client, league, tid, headers)
    _play_round(client, league, tid, _round(tournament), headers)
    # Another tournament finishes meanwhile: its winner earns season points,
    # and the league ranking reflects the standings when it is used (BR-020).
    other = client.post(
        f"/api/v1/leagues/{league.id}/tournaments",
        json={
            "id": str(uuid7()),
            **MONSTER_DYP,
            "type": "singles",
            "group_phase": "round_robin",
            "round_robin_legs": 1,
            "sit_out_points": None,
        },
        headers=headers,
    )
    assert other.status_code == 201, other.text
    oid: str = other.json()["tournament_id"]
    duo = [players[7], players[6]]
    _put(client, league, oid, "/setup/players", {"player_ids": duo}, headers)
    finished = _started(client, league, oid, headers)
    _play_round(client, league, oid, _round(finished), headers)
    done = client.post(
        _t_url(league, oid, "/finish"),
        json={"expected_state": "in_progress"},
        headers=headers,
    )
    assert done.status_code == 200, done.text
    seen: list[tuple[RankedPlayer, ...]] = []
    real = draw_monster

    def spy(
        tournament: Tournament,
        group: TournamentPhase,
        *,
        ranking: Sequence[RankedPlayer],
    ) -> MonsterDraw:
        seen.append(tuple(ranking))
        return real(tournament, group, ranking=ranking)

    monkeypatch.setattr(rounds_service, "draw_monster", spy)

    two = _next_round(client, league, tid, 2, headers)

    [ranking] = seen
    assert {ranked.player_id for ranked in ranking[:2]} == {UUID(p) for p in duo}
    assert all(ranked.season_points > 0 for ranked in ranking[:2])
    assert all(ranked.season_points == 0 for ranked in ranking[2:])
    assert sorted(len(g & set(duo)) for g in _groups(two)) == [1, 1]


def test_br061_disabled_top_player_is_replaced(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    twelve: list[str],
    disable: Callable[[str], None],
) -> None:
    tid = _monster(client, league, headers, twelve)
    r = _ranked(_get(client, league, tid, "/setup", headers))
    _put(
        client, league, tid, "/setup/top-players", {"player_ids": [r[0], r[5]]}, headers
    )
    tournament = _started(client, league, tid, headers)
    _play_round(client, league, tid, _round(tournament), headers)
    entry_of = {p: e for e, p in _player_of(tournament).items()}
    disable(entry_of[r[0]])  # the marked #1 leaves

    two = _next_round(client, league, tid, 2, headers)

    # 11 players: 2 matches, 3 sit out (BR-063). The top players are taken
    # from the 8 who play: the marked #6 if it plays, then the others in
    # league-ranking order, never the disabled #1 (BR-061).
    playing = set().union(*_groups(two))
    assert len(playing) == 8
    assert r[0] not in playing
    assert r[0] not in {_player_of(tournament)[e] for e in two["sitting_out"]}
    tops = ([r[5]] if r[5] in playing else []) + [
        p for p in r if p in playing and p != r[5]
    ]
    assert sorted(len(g & set(tops[:2])) for g in _groups(two)) == [1, 1]


def test_br062_no_repeated_partner_while_avoidable(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    tid = _monster(client, league, headers, players[:8])
    tournament = _started(client, league, tid, headers)
    rounds = [_round(tournament)]
    for round_no in (2, 3):
        _play_round(client, league, tid, rounds[-1], headers)
        rounds.append(_next_round(client, league, tid, round_no, headers))

    partners = [pair for round_ in rounds for pair in _partners(round_)]
    assert len(partners) == 12
    assert len(set(partners)) == 12
    assert not any(m["is_repeat"] for m in rounds[1]["matches"] + rounds[2]["matches"])


def test_br063_who_played_last_round_sits_out_first(
    client: TestClient, league: League, headers: dict[str, str], twelve: list[str]
) -> None:
    tid = _monster(client, league, headers, twelve[:10])
    tournament = _started(client, league, tid, headers)
    _play_round(client, league, tid, _round(tournament), headers)

    two = _next_round(client, league, tid, 2, headers)

    # The 2 who sat out round 1 play round 2; 2 of the 8 who played sit out, and
    # all 8 have no sit-out yet, so the lot picks them (BR-063).
    assert len(two["sitting_out"]) == 2
    assert not set(two["sitting_out"]) & set(_round(tournament)["sitting_out"])
    assert two["is_sit_out_by_lot"] is True


def test_br064_disabled_player_is_not_drawn_and_counts_as_sit_out_for_order_only(
    client: TestClient,
    session: Session,
    league: League,
    headers: dict[str, str],
    players: list[str],
    disable: Callable[[str], None],
) -> None:
    tid = _monster(client, league, headers, players[:5])
    tournament = _started(client, league, tid, headers)
    player_of = _player_of(tournament)
    entry_of = {p: e for e, p in player_of.items()}
    [x] = (player_of[e] for e in _round(tournament)["sitting_out"])
    y = next(p for p in players[:5] if p != x)
    _play_round(client, league, tid, _round(tournament), headers)
    disable(entry_of[y])

    two = _next_round(client, league, tid, 2, headers)

    # y is not drawn and does not sit out: 4 players are left, so all of them
    # play (BR-064), and the sit-out column counts sit-outs only (FR-060).
    assert two["sitting_out"] == []
    assert y not in set().union(*_groups(two))
    status = session.scalar(
        select(RoundParticipation.status).where(
            RoundParticipation.round_id == UUID(two["id"]),
            RoundParticipation.entry_id == UUID(entry_of[y]),
        )
    )
    assert status is not None
    assert status.value == "disabled"
    play = _get(client, league, tid, "/play", headers)
    assert {row["entry_id"]: row["sat_out"] for row in play["standings"]}[
        entry_of[y]
    ] == 0

    # Back in the draw, y missed round 2, which counts as a sit-out for the
    # order only: the one who sits out round 3 is none of those with a sit-out
    # to their name, x (round 1) and y (round 2) (BR-063, BR-064).
    _play_round(client, league, tid, two, headers)
    session.get_one(Entry, UUID(entry_of[y])).is_disabled = False
    session.flush()
    three = _next_round(client, league, tid, 3, headers)
    [out] = (player_of[e] for e in three["sitting_out"])
    assert out not in {x, y}


def test_a_monster_dyp_needs_four_players_who_are_not_disabled(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    players: list[str],
    disable: Callable[[str], None],
) -> None:
    tid = _monster(client, league, headers, players[:4])
    tournament = _started(client, league, tid, headers)
    _play_round(client, league, tid, _round(tournament), headers)
    disable(next(iter(_player_of(tournament))))

    status, body = _add_round(client, league, tid, 2, headers)

    assert (status, body) == (
        422,
        {"code": "not_enough_players", "detail": {"minimum": 4, "given": 3}},
    )


def test_fr046_delete_the_newest_round(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    tid = _monster(client, league, headers, players[:9])
    tournament = _started(client, league, tid, headers)
    _play_round(client, league, tid, _round(tournament), headers)
    after_one = _get(client, league, tid, "/play", headers)["standings"]
    two = _next_round(client, league, tid, 2, headers)
    _play_round(client, league, tid, two, headers)
    assert _get(client, league, tid, "/play", headers)["standings"] != after_one
    teams_of_two = _teams(two)

    status, body = _delete_round(client, league, tid, two["id"], headers)

    assert (status, body) == (204, {})
    assert _get(client, league, tid, "/play", headers)["standings"] == after_one
    read = _get(client, league, tid, "", headers)
    assert [r["round_no"] for r in read["rounds"]] == [1]
    assert read["state"] == "in_progress"
    again, missing = _delete_round(client, league, tid, two["id"], headers)
    assert (again, missing["code"]) == (404, "round_not_found")
    # The round can be drawn again: it is the same draw (ADR-010).
    assert _teams(_next_round(client, league, tid, 2, headers)) == teams_of_two


def test_fr046_only_the_newest_round_can_be_deleted(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    tid = _monster(client, league, headers, players[:8])
    tournament = _started(client, league, tid, headers)
    _play_round(client, league, tid, _round(tournament), headers)
    two = _next_round(client, league, tid, 2, headers)

    status, body = _delete_round(client, league, tid, _round(tournament)["id"], headers)

    assert status == 409
    assert body == {"code": "round_not_newest", "detail": {"round_id": two["id"]}}


def test_fr046_deleting_round_one_returns_to_setup_and_keeps_marks(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    players: list[str],
    disable: Callable[[str], None],
) -> None:
    tid = _monster(client, league, headers, players[:8])
    a, b = players[:2]
    _put(client, league, tid, "/setup/top-players", {"player_ids": [a, b]}, headers)
    tournament = _started(client, league, tid, headers)
    _result(
        client,
        league,
        tid,
        _round(tournament)["matches"][0]["id"],
        win("side_1"),
        headers,
    )
    disable(next(iter(_player_of(tournament))))

    status, body = _delete_round(client, league, tid, _round(tournament)["id"], headers)

    assert (status, body) == (204, {})
    read = _get(client, league, tid, "", headers)
    assert read["state"] == "setup"
    assert read["rounds"] == []
    marked = {e["player_ids"][0] for e in read["entries"] if e["is_top_player"]}
    assert marked == {a, b}
    assert not any(e["is_disabled"] for e in read["entries"])
    setup = _get(client, league, tid, "/setup", headers)
    assert set(setup["top_player_ids"]) == {a, b}
    assert _started(client, league, tid, headers)["rounds"]


def test_adr008_stale_expected_round_no_is_409(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    tid = _monster(client, league, headers, players[:8])
    tournament = _started(client, league, tid, headers)
    _play_round(client, league, tid, _round(tournament), headers)

    ahead = _add_round(client, league, tid, 3, headers)
    _next_round(client, league, tid, 2, headers)
    repeat = _add_round(client, league, tid, 2, headers)

    expected = {"code": "round_number_changed"}
    assert ahead[0] == repeat[0] == 409
    assert ahead[1] == {**expected, "detail": {"current_round_no": 1}}
    assert repeat[1] == {**expected, "detail": {"current_round_no": 2}}
    read = _get(client, league, tid, "", headers)
    assert [r["round_no"] for r in read["rounds"]] == [1, 2]


def test_round_not_complete_is_422(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    tid = _monster(client, league, headers, players[:8])
    tournament = _started(client, league, tid, headers)
    first, _ = _round(tournament)["matches"]
    _result(client, league, tid, first["id"], win("side_1"), headers)

    status, body = _add_round(client, league, tid, 2, headers)

    assert (status, body) == (
        422,
        {"code": "round_not_complete", "detail": {"matches_left": 1}},
    )


def _finish(
    client: TestClient, league: League, tournament_id: str, headers: dict[str, str]
) -> tuple[int, Json]:
    response = client.post(
        _t_url(league, tournament_id, "/finish"),
        json={"expected_state": "in_progress"},
        headers=headers,
    )
    result: Json = response.json()
    return response.status_code, result


def test_br103_monster_dyp_without_knockout_places_follow_the_standings(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    tid = _monster(client, league, headers, players[:8])
    tournament = _started(client, league, tid, headers)
    _play_round(client, league, tid, _round(tournament), headers)

    status, finished = _finish(client, league, tid, headers)

    assert (status, finished["state"]) == (200, "finished"), finished
    play = _get(client, league, tid, "/play", headers)
    places = _get(client, league, tid, "/places", headers)
    assert places["complete"] is True
    assert {row["entry_id"]: row["place"] for row in places["rows"]} == {
        row["entry_id"]: row["place"] for row in play["standings"]
    }
    assert len(places["rows"]) == 8
    assert {row["reason"]["group_format"] for row in places["rows"]} == {"monster_dyp"}


def test_br111_shared_place_splits_season_points(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    tid = _monster(client, league, headers, players[:8])
    tournament = _started(client, league, tid, headers)
    for match in _round(tournament)["matches"]:
        _result(client, league, tid, match["id"], win("side_1"), headers)
    _finish(client, league, tid, headers)

    places = _get(client, league, tid, "/places", headers)

    # The four winners are level and share 1st, which covers places 1 to 4;
    # the four losers share 5th, which covers 5 to 8 (BR-104, BR-111).
    by_place: dict[int, set[int]] = {}
    for row in places["rows"]:
        by_place.setdefault(row["place"], set()).add(row["points_per_player"])
    assert by_place == {1: {(10 + 8 + 6 + 4) // 4}, 5: {(2 + 0 + 0 + 0) // 4}}


def test_br112_season_standings_count_a_finished_monster_dyp(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    players: list[str],
) -> None:
    tid = _monster(client, league, headers, players[:8])
    tournament = _started(client, league, tid, headers)
    _play_round(client, league, tid, _round(tournament), headers)
    url = f"/api/v1/leagues/{league.id}/seasons/{tournament['season_id']}/standings"
    assert client.get(url, headers=headers).json() == []

    _finish(client, league, tid, headers)

    season = client.get(url, headers=headers).json()
    assert {row["player_id"] for row in season} == set(players[:8])
    assert sum(row["points"] for row in season) > 0


def test_group_phase_not_done_is_422(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    tid = _monster(client, league, headers, players[:8])
    tournament = _started(client, league, tid, headers)
    first, _ = _round(tournament)["matches"]
    _result(client, league, tid, first["id"], win("side_1"), headers)

    status, body = _finish(client, league, tid, headers)

    assert (status, body) == (
        422,
        {"code": "group_phase_not_done", "detail": {"matches_left": 1}},
    )
