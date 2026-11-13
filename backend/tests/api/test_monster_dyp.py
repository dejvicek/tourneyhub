"""The Monster DYP group phase: the top players in setup (FR-041, BR-061)."""

from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid7

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tourneyhub.db.models.entries import Entry, EntryMember
from tourneyhub.db.models.leagues import League, Player
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

    assert status == 422
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
