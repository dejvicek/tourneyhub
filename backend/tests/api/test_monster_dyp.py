"""The Monster DYP group phase: the top players in setup and the start with
round 1 (FR-041, BR-060, BR-061, BR-063).
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
