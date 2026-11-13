"""Starting the knockout in Lord have mercy: pairs drawn by lot, round 1 stored
(FR-045, BR-080, BR-084, ADR-008, ADR-010, DATA-MODEL D4); a knockout whose
later rounds are drawn one by one is not a fixed bracket (BR-053, BR-120,
FR-054).
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
from tourneyhub.db.models.tournaments import Tournament, TournamentPhase
from tourneyhub.engine.ids import PlayerId
from tourneyhub.engine.tournaments import EntryStage, MonsterKnockoutMode, PhaseKind
from tourneyhub.services.tournaments.remix import left_player_ids, remix_knockout
from tourneyhub.services.tournaments.shared import _load_tournament

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
    *,
    third_place_match: bool = False,
) -> Json:
    third = str(third_place_match).lower()
    return _get(
        client,
        league_id,
        tournament["id"],
        f"/knockout/preview?qualifiers={qualifiers}&third_place_match={third}"
        f"&mode={MODE}",
        headers,
    )


def _members(shown: Json) -> list[list[str]]:
    """Each previewed entry's group-phase entries, seed 1 first."""
    return [[m["entry_id"] for m in e["members"]] for e in shown["entries"]]


def _start_body(
    tournament: Json,
    shown: Json,
    qualifiers: int = 8,
    *,
    third_place_match: bool = False,
    final_match_format: str | None = None,
) -> Json:
    return {
        "expected_current_phase_id": tournament["current_phase_id"],
        "expected_qualifier_ids": [
            member for members in _members(shown) for member in members
        ],
        "expected_draw_counter": shown["draw_counter"],
        "qualifiers": qualifiers,
        "third_place_match": third_place_match,
        "match_format": "bo1",
        "final_match_format": final_match_format,
        "mode": MODE,
    }


def _start(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    tournament: Json,
    shown: Json,
    qualifiers: int = 8,
    *,
    third_place_match: bool = False,
    final_match_format: str | None = None,
) -> Json:
    response = client.put(
        _t_url(league_id, tournament["id"], "/knockout"),
        json=_start_body(
            tournament,
            shown,
            qualifiers,
            third_place_match=third_place_match,
            final_match_format=final_match_format,
        ),
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


# ---------------------------------------------------------------- not a fixed bracket


def _started(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    tournament: Json,
    qualifiers: int = 8,
    *,
    third_place_match: bool = True,
    final_match_format: str | None = None,
) -> tuple[Json, Json]:
    """The preview and the tournament once Lord have mercy has started."""
    shown = _preview(
        client,
        league_id,
        headers,
        tournament,
        qualifiers,
        third_place_match=third_place_match,
    )
    started = _start(
        client,
        league_id,
        headers,
        tournament,
        shown,
        qualifiers,
        third_place_match=third_place_match,
        final_match_format=final_match_format,
    )
    return shown, started


def _knockout(tournament: Json) -> Json:
    knockout: Json = next(p for p in tournament["phases"] if p["kind"] == "knockout")
    return knockout


def _rounds(tournament: Json, phase: Json) -> list[Json]:
    return [r for r in tournament["rounds"] if r["phase_id"] == phase["id"]]


def _put_result(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    tournament: Json,
    match: Json,
    result: Json,
) -> tuple[int, Json]:
    response = client.put(
        _t_url(league_id, tournament["id"], f"/matches/{match['id']}/result"),
        json=result,
        headers=headers,
    )
    body: Json = response.json()
    return response.status_code, body


def _set_final(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    tournament: Json,
    final_match_format: str | None,
) -> tuple[int, Json]:
    response = client.put(
        _t_url(league_id, tournament["id"], "/knockout/final-format"),
        json={"final_match_format": final_match_format},
        headers=headers,
    )
    body: Json = response.json()
    return response.status_code, body


def _bo3_win() -> Json:
    """Side 1 wins a BO3 two games to none."""
    game = {"winner": "side_1", "score_1": 10, "score_2": 5}
    return {"walkover_winner": None, "games": [game, game]}


def test_br053_group_phase_stays_locked_during_lord_have_mercy(
    client: TestClient, league_id: UUID, headers: dict[str, str], monster: Json
) -> None:
    _, started = _started(client, league_id, headers, monster)
    knockout = _knockout(started)
    group = next(p for p in started["phases"] if p["kind"] == "group")
    [group_round] = _rounds(started, group)
    locked = {"code": "group_phase_locked", "detail": {"phase_id": knockout["id"]}}

    added = client.post(
        _t_url(league_id, monster["id"], "/rounds"),
        json={"expected_round_no": 2},
        headers=headers,
    )
    deleted = client.delete(
        _t_url(league_id, monster["id"], f"/rounds/{group_round['id']}"),
        headers=headers,
    )
    tiebreakers = client.put(
        _t_url(league_id, monster["id"], "/tiebreakers"),
        json={"tiebreakers": group["tiebreakers"]},
        headers=headers,
    )
    # The fixture's side 1 won every group match, so this is a new result.
    result = _put_result(
        client,
        league_id,
        headers,
        started,
        group_round["matches"][0],
        _win("side_2"),
    )

    assert (added.status_code, added.json()) == (422, locked)
    assert (deleted.status_code, deleted.json()) == (422, locked)
    assert (tiebreakers.status_code, tiebreakers.json()) == (422, locked)
    assert result == (422, locked)


def test_fr045_draw_again_once_a_lord_have_mercy_knockout_exists_is_409(
    client: TestClient, league_id: UUID, headers: dict[str, str], monster: Json
) -> None:
    shown, started = _started(client, league_id, headers, monster)
    changed = {
        "code": "current_phase_changed",
        "detail": {"current_phase_id": started["current_phase_id"]},
    }

    response = client.post(
        _t_url(league_id, monster["id"], "/knockout/draw"),
        json={"expected_draw_counter": shown["draw_counter"]},
        headers=headers,
    )
    preview = _preview(client, league_id, headers, monster, third_place_match=True)

    assert started["current_phase_id"] == _knockout(started)["id"]
    assert (response.status_code, response.json()) == (409, changed)
    assert (preview["can_start"], preview["problem"]) == (False, changed)


def test_br120_round_one_plays_the_knockouts_format_until_the_final(
    client: TestClient, league_id: UUID, headers: dict[str, str], monster: Json
) -> None:
    _, started = _started(client, league_id, headers, monster, final_match_format="bo3")
    knockout = _knockout(started)
    [round_1] = _rounds(started, knockout)

    results = [
        _put_result(client, league_id, headers, started, match, _win("side_1"))
        for match in round_1["matches"]
    ]

    # Four pairs: round 1 holds the semifinals, the final is round 2's.
    assert len(round_1["matches"]) == 2
    assert [status for status, _ in results] == [200, 200]
    assert knockout["final_match_format"] == "bo3"


def test_fr054_the_final_format_can_change_until_the_final_is_drawn(
    client: TestClient, league_id: UUID, headers: dict[str, str], monster: Json
) -> None:
    _, started = _started(client, league_id, headers, monster)
    [round_1] = _rounds(started, _knockout(started))
    first, second = round_1["matches"]
    entered = _put_result(client, league_id, headers, started, first, _win("side_1"))

    status, body = _set_final(client, league_id, headers, started, "bo3")
    later = _put_result(client, league_id, headers, started, second, _win("side_1"))

    assert entered[0] == 200
    assert status == 200, body
    assert _knockout(body)["final_match_format"] == "bo3"
    # A semifinal is not the final: it keeps the knockout's format (BR-120).
    assert later[0] == 200


def test_fr054_final_format_applies_to_the_drawn_final(
    client: TestClient, league_id: UUID, headers: dict[str, str], monster: Json
) -> None:
    _, started = _started(
        client, league_id, headers, monster, 4, third_place_match=False
    )
    [round_1] = _rounds(started, _knockout(started))
    [final] = round_1["matches"]  # two pairs: round 1 is the final

    status, _ = _set_final(client, league_id, headers, started, "bo3")
    bo1 = _put_result(client, league_id, headers, started, final, _win("side_1"))
    bo3 = _put_result(client, league_id, headers, started, final, _bo3_win())
    after = _set_final(client, league_id, headers, started, None)

    assert status == 200
    assert bo1[0] == 422
    assert bo3[0] == 200
    assert after == (
        409,
        {"code": "match_has_result", "detail": {"match_id": final["id"]}},
    )


def test_br084_br155_the_loader_reads_the_stored_rounds_and_who_left(
    client: TestClient,
    session: Session,
    league: League,
    headers: dict[str, str],
    monster: Json,
    disable: Callable[[str], None],
) -> None:
    def load() -> Tournament:
        return _load_tournament(
            session, league=league, tournament_id=UUID(monster["id"])
        )

    before = remix_knockout(load())
    _, started = _started(client, league.id, headers, monster)
    order = _order(client, league.id, headers, monster)
    disable(order[0])
    tournament = load()
    remix = remix_knockout(tournament)

    assert before is None
    assert remix is not None
    assert remix.phase.id == UUID(_knockout(started)["id"])
    assert (remix.state.size, remix.state.third_place_match) == (4, True)
    assert remix.state.rounds_drawn == 1
    assert set(remix.rounds) == {1}
    [round_1] = _rounds(started, _knockout(started))
    assert {remix.rows[key].id for key in remix.keys.values()} == {
        UUID(m["id"]) for m in round_1["matches"]
    }
    for match in round_1["matches"]:
        stored = remix.state.match(remix.keys[UUID(match["id"])])
        assert (stored.side_1, stored.side_2) == tuple(
            tuple(sorted(PlayerId(UUID(p)) for p in side["player_ids"]))
            for side in match["sides"]
        )
    assert len(remix.state.players) == 8
    player_of = {
        e["id"]: e["player_ids"][0] for e in started["entries"] if e["stage"] == "main"
    }
    assert left_player_ids(tournament, remix) == {PlayerId(UUID(player_of[order[0]]))}
