"""The knockout's contract with the draw counter (ADR-008, ADR-010)."""

from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid7

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tourneyhub.db.models.leagues import League, Player
from tourneyhub.db.models.tournaments import Tournament, TournamentPhase
from tourneyhub.engine.tournaments import PhaseKind

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


def _url(league_id: UUID, rest: str = "") -> str:
    return f"/api/v1/leagues/{league_id}{rest}"


def _t_url(league_id: UUID, tournament_id: str, rest: str = "") -> str:
    return _url(league_id, f"/tournaments/{tournament_id}{rest}")


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
def played_group(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    players: list[str],
) -> Json:
    """Four players after their round robin, every match won by side 1."""
    created = client.post(
        _url(league_id, "/tournaments"),
        json={"id": str(uuid7()), **ROUND_ROBIN},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    tournament_id = created.json()["tournament_id"]
    picked = client.put(
        _t_url(league_id, tournament_id, "/setup/players"),
        json={"player_ids": players[:4]},
        headers=headers,
    )
    assert picked.status_code == 200, picked.text
    order = [e["id"] for e in sorted(picked.json()["entries"], key=lambda e: e["seed"])]
    started = client.post(
        _t_url(league_id, tournament_id, "/start"),
        json={
            "expected_draw_counter": picked.json()["draw_counter"],
            "expected_seed_order": order,
        },
        headers=headers,
    )
    assert started.status_code == 200, started.text
    for round_ in started.json()["rounds"]:
        for match in round_["matches"]:
            result = client.put(
                _t_url(league_id, tournament_id, f"/matches/{match['id']}/result"),
                json={
                    "walkover_winner": None,
                    "games": [{"winner": "side_1", "score_1": 10, "score_2": 5}],
                },
                headers=headers,
            )
            assert result.status_code == 200, result.text
    shown = client.get(_t_url(league_id, tournament_id), headers=headers)
    tournament: Json = shown.json()
    return tournament


def _preview(
    client: TestClient, league_id: UUID, headers: dict[str, str], tournament: Json
) -> Json:
    response = client.get(
        _t_url(
            league_id,
            tournament["id"],
            "/knockout/preview?qualifiers=4&third_place_match=false",
        ),
        headers=headers,
    )
    assert response.status_code == 200, response.text
    shown: Json = response.json()
    return shown


def _start_body(tournament: Json, shown: Json, **values: object) -> Json:
    return {
        "expected_current_phase_id": tournament["current_phase_id"],
        "expected_qualifier_ids": [
            e["members"][0]["entry_id"] for e in shown["entries"]
        ],
        "expected_draw_counter": shown["draw_counter"],
        "qualifiers": 4,
        "third_place_match": False,
        "match_format": None,
        "final_match_format": None,
        "mode": None,
        **values,
    }


def test_adr008_the_knockout_preview_carries_the_draw_counter(
    client: TestClient,
    session: Session,
    league_id: UUID,
    headers: dict[str, str],
    played_group: Json,
) -> None:
    tournament = session.get_one(Tournament, UUID(played_group["id"]))
    tournament.draw_counter = 3
    session.flush()  # the stored counter is not the default 0

    shown = _preview(client, league_id, headers, played_group)

    assert shown["draw_counter"] == 3


def test_adr008_a_stale_draw_counter_at_the_knockout_start_is_409(
    client: TestClient,
    session: Session,
    league_id: UUID,
    headers: dict[str, str],
    played_group: Json,
) -> None:
    shown = _preview(client, league_id, headers, played_group)
    stale = shown["draw_counter"] + 1

    response = client.put(
        _t_url(league_id, played_group["id"], "/knockout"),
        json=_start_body(played_group, shown, expected_draw_counter=stale),
        headers=headers,
    )

    assert (response.status_code, response.json()) == (
        409,
        {
            "code": "draw_counter_changed",
            "detail": {"draw_counter": shown["draw_counter"]},
        },
    )
    knockouts = session.scalar(
        select(func.count())
        .select_from(TournamentPhase)
        .where(
            TournamentPhase.tournament_id == UUID(played_group["id"]),
            TournamentPhase.kind == PhaseKind.KNOCKOUT,
        )
    )
    assert knockouts == 0
