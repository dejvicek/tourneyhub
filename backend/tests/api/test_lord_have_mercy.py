"""Starting the knockout in Lord have mercy: pairs drawn by lot, round 1 stored
(FR-045, BR-080, BR-084, ADR-008, ADR-010, DATA-MODEL D4).
"""

from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid7

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tourneyhub.db.models.entries import Entry
from tourneyhub.db.models.leagues import League, Player
from tourneyhub.db.models.matches import Round
from tourneyhub.db.models.tournaments import TournamentPhase
from tourneyhub.engine.tournaments import EntryStage, MonsterKnockoutMode, PhaseKind

type Json = dict[str, Any]

MODE = MonsterKnockoutMode.LORD_HAVE_MERCY.value

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
def disable(session: Session) -> Callable[[str], None]:
    def disable(entry_id: str) -> None:
        """Disable an entry; its route comes with P14 (FR-044)."""
        session.get_one(Entry, UUID(entry_id)).is_disabled = True
        session.flush()

    return disable


def _win(side: str, score: tuple[int, int] = (10, 5)) -> Json:
    """A BO1 result with a score, which a Monster DYP requires (BR-092)."""
    winner, loser = score
    scores = (winner, loser) if side == "side_1" else (loser, winner)
    return {
        "walkover_winner": None,
        "games": [{"winner": side, "score_1": scores[0], "score_2": scores[1]}],
    }


def _get(
    client: TestClient,
    league_id: UUID,
    tournament_id: str,
    rest: str,
    headers: dict[str, str],
) -> Json:
    response = client.get(_t_url(league_id, tournament_id, rest), headers=headers)
    assert response.status_code == 200, response.text
    result: Json = response.json()
    return result


@pytest.fixture
def monster(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    players: list[str],
) -> Json:
    """Eight players after Monster DYP round 1, side 1 winning every match."""
    created = client.post(
        _url(league_id, "/tournaments"),
        json={"id": str(uuid7()), **MONSTER_DYP},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    tournament_id = created.json()["tournament_id"]
    picked = client.put(
        _t_url(league_id, tournament_id, "/setup/players"),
        json={"player_ids": players},
        headers=headers,
    )
    assert picked.status_code == 200, picked.text
    preview = _get(client, league_id, tournament_id, "/setup/preview", headers)
    started = client.post(
        _t_url(league_id, tournament_id, "/start"),
        json={
            "expected_draw_counter": preview["draw_counter"],
            "expected_seed_order": preview["seed_order"],
        },
        headers=headers,
    )
    assert started.status_code == 200, started.text
    [round_] = started.json()["rounds"]
    for index, match in enumerate(round_["matches"]):
        result = client.put(
            _t_url(league_id, tournament_id, f"/matches/{match['id']}/result"),
            json=_win("side_1", (10, 1 + index)),
            headers=headers,
        )
        assert result.status_code == 200, result.text
    return _get(client, league_id, tournament_id, "", headers)


def _order(
    client: TestClient, league_id: UUID, headers: dict[str, str], tournament: Json
) -> list[str]:
    """The players' main entries by their position in the standings."""
    play = _get(client, league_id, tournament["id"], "/play", headers)
    return [row["entry_id"] for row in play["standings"]]


def _preview(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    tournament: Json,
    qualifiers: int = 8,
) -> Json:
    return _get(
        client,
        league_id,
        tournament["id"],
        f"/knockout/preview?qualifiers={qualifiers}&third_place_match=false"
        f"&mode={MODE}",
        headers,
    )


def _members(shown: Json) -> list[list[str]]:
    """Each previewed entry's group-phase entries, seed 1 first."""
    return [[m["entry_id"] for m in e["members"]] for e in shown["entries"]]


def _start_body(tournament: Json, shown: Json, qualifiers: int = 8) -> Json:
    return {
        "expected_current_phase_id": tournament["current_phase_id"],
        "expected_qualifier_ids": [
            member for members in _members(shown) for member in members
        ],
        "expected_draw_counter": shown["draw_counter"],
        "qualifiers": qualifiers,
        "third_place_match": False,
        "match_format": "bo1",
        "final_match_format": None,
        "mode": MODE,
    }


def _start(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    tournament: Json,
    shown: Json,
) -> Json:
    response = client.put(
        _t_url(league_id, tournament["id"], "/knockout"),
        json=_start_body(tournament, shown),
        headers=headers,
    )
    assert response.status_code == 200, response.text
    started: Json = response.json()
    return started


def test_br084_preview_can_start_lord_have_mercy(
    client: TestClient, league_id: UUID, headers: dict[str, str], monster: Json
) -> None:
    shown = _preview(client, league_id, headers, monster)

    assert (shown["can_start"], shown["problem"]) == (True, None)
    assert [e["seed"] for e in shown["entries"]] == [1, 2, 3, 4]
    assert all(len(members) == 2 for members in _members(shown))
    assert all(e["decided_by_lot"] for e in shown["entries"])
    assert len({m for members in _members(shown) for m in members}) == 8


def test_br084_start_creates_pair_entries_and_round_one_only(
    client: TestClient,
    session: Session,
    league_id: UUID,
    headers: dict[str, str],
    monster: Json,
) -> None:
    shown = _preview(client, league_id, headers, monster)

    _start(client, league_id, headers, monster, shown)

    after = _get(client, league_id, monster["id"], "", headers)
    entries = sorted(
        (e for e in after["entries"] if e["stage"] == "knockout"),
        key=lambda e: e["seed"],
    )
    assert [(e["kind"], len(e["player_ids"])) for e in entries] == [("pair", 2)] * 4
    rows = session.scalars(
        select(Entry).where(
            Entry.tournament_id == UUID(monster["id"]),
            Entry.stage == EntryStage.KNOCKOUT,
        )
    ).all()
    assert sorted(str(row.id) for row in rows) == sorted(e["id"] for e in entries)
    assert all(row.source_entry_id is None for row in rows)
    phase = next(p for p in after["phases"] if p["kind"] == "knockout")
    assert phase["monster_knockout_mode"] == MODE
    [round_1] = [r for r in after["rounds"] if r["phase_id"] == phase["id"]]
    assert round_1["round_no"] == 1
    seed_of = {e["id"]: e["seed"] for e in entries}
    stored = sorted(
        sorted(seed_of[side["entry_id"]] for side in match["sides"])
        for match in round_1["matches"]
    )
    assert stored == sorted(sorted(pair) for pair in shown["first_round"])
    stored_rounds = session.scalars(
        select(Round).where(Round.phase_id == UUID(phase["id"]))
    ).all()
    assert [r.round_no for r in stored_rounds] == [1]


def test_br084_fr045_draw_again_before_the_start(
    client: TestClient,
    session: Session,
    league_id: UUID,
    headers: dict[str, str],
    monster: Json,
) -> None:
    shown = _preview(client, league_id, headers, monster)
    n = shown["draw_counter"]

    response = client.post(
        _t_url(league_id, monster["id"], "/knockout/draw"),
        json={"expected_draw_counter": n},
        headers=headers,
    )

    assert (response.status_code, response.json()) == (200, {"draw_counter": n + 1})
    again = _preview(client, league_id, headers, monster)
    assert again["draw_counter"] == n + 1
    stale = client.put(
        _t_url(league_id, monster["id"], "/knockout"),
        json=_start_body(monster, shown),
        headers=headers,
    )
    assert (stale.status_code, stale.json()) == (
        409,
        {"code": "draw_counter_changed", "detail": {"draw_counter": n + 1}},
    )
    knockouts = session.scalars(
        select(TournamentPhase).where(
            TournamentPhase.tournament_id == UUID(monster["id"]),
            TournamentPhase.kind == PhaseKind.KNOCKOUT,
        )
    ).all()
    assert knockouts == []


def test_br080_br084_a_disabled_player_does_not_qualify(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    monster: Json,
    disable: Callable[[str], None],
) -> None:
    order = _order(client, league_id, headers, monster)
    disable(order[0])

    shown = _preview(client, league_id, headers, monster)

    # Seven players are left and a pair mode takes an even number (BR-080).
    assert (shown["max_qualifiers"], shown["qualifiers"]) == (6, 6)
    assert len(shown["entries"]) == 3
    assert order[0] not in [m for members in _members(shown) for m in members]
    assert shown["skipped_entry_ids"] == [order[0]]
