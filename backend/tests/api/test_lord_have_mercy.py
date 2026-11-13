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
from tourneyhub.engine.lots import order_by_lot
from tourneyhub.engine.remix import THIRD_PLACE_PURPOSE, remix_purpose
from tourneyhub.engine.tournaments import (
    EntryStage,
    MonsterKnockoutMode,
    PhaseKind,
)
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


def _monster_of(
    client: TestClient, league_id: UUID, headers: dict[str, str], players: list[str]
) -> Json:
    """These players after Monster DYP round 1, side 1 winning every match."""
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


@pytest.fixture
def monster(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    players: list[str],
) -> Json:
    """Eight players after Monster DYP round 1, side 1 winning every match."""
    return _monster_of(client, league_id, headers, players)


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


# ---------------------------------------------------------------- draw the next round


def _draw_round(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    tournament: Json,
    expected_round_no: int,
) -> tuple[int, Json]:
    response = client.post(
        _t_url(league_id, tournament["id"], "/knockout/rounds"),
        json={"expected_round_no": expected_round_no},
        headers=headers,
    )
    body: Json = response.json()
    return response.status_code, body


def _is_bye(match: Json) -> bool:
    return any(side["is_bye"] for side in match["sides"])


def _play(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    tournament: Json,
    matches: list[Json],
    *,
    losers: int = 0,
) -> None:
    """Give every match without a bye a result, side 1 winning (side 2 for the
    last `losers` matches). Matches come from the tournament or from a draw."""
    for index, match in enumerate(matches):
        if _is_bye(match) or match.get("state") == "bye":
            continue
        side = "side_2" if index >= len(matches) - losers else "side_1"
        status, body = _put_result(
            client,
            league_id,
            headers,
            tournament,
            {"id": match.get("id", match.get("match_id"))},
            _win(side),
        )
        assert status == 200, body


def _round_one(started: Json) -> list[Json]:
    [round_1] = _rounds(started, _knockout(started))
    matches: list[Json] = round_1["matches"]
    return matches


def _players_of(sides: list[Json]) -> set[str]:
    return {player for side in sides for player in side["player_ids"]}


def _winners(matches: list[Json]) -> set[str]:
    """The players of side 1 of every match without a bye, and of a bye's pair."""
    return {
        player
        for match in matches
        for side in match["sides"]
        if not side["is_bye"] and (_is_bye(match) or side is match["sides"][0])
        for player in side["player_ids"]
    }


def test_br140_br141_round_two_is_drawn_from_the_winners(
    client: TestClient, league_id: UUID, headers: dict[str, str], monster: Json
) -> None:
    _, started = _started(client, league_id, headers, monster, third_place_match=False)
    round_1 = _round_one(started)
    _play(client, league_id, headers, started, round_1)

    status, drawn = _draw_round(client, league_id, headers, started, 2)

    assert status == 201, drawn
    [round_2] = drawn["rounds"][1:]
    [final] = round_2["matches"]
    assert round_2["round_no"] == 2
    assert _players_of(final["sides"]) == _winners(round_1)
    for side in final["sides"]:
        assert side["entry_id"] is None
        assert len(side["player_ids"]) == 2
        assert not side["is_bye"]
    assert (drawn["round_count"], drawn["can_draw_next"]) == (2, False)
    stored = _get(client, league_id, monster["id"], "", headers)
    assert [r["round_no"] for r in _rounds(stored, _knockout(stored))] == [1, 2]


def test_br141_pairs_with_a_bye_go_through(
    client: TestClient,
    league: League,
    league_id: UUID,
    headers: dict[str, str],
    make_player: Callable[..., Player],
) -> None:
    twelve = [str(make_player(league=league, name=f"Q{n}").id) for n in range(12)]
    big = _monster_of(client, league_id, headers, twelve)
    _, started = _started(client, league_id, headers, big, 12, third_place_match=False)
    round_1 = _round_one(started)
    byes = [match for match in round_1 if _is_bye(match)]
    _play(client, league_id, headers, started, round_1)

    status, drawn = _draw_round(client, league_id, headers, started, 2)

    # Six pairs fill a bracket of eight: two byes, two played matches.
    assert len(round_1) == 4
    assert len(byes) == 2
    assert status == 201, drawn
    round_2 = drawn["rounds"][1]
    assert len(round_2["matches"]) == 2
    players = _players_of([s for m in round_2["matches"] for s in m["sides"]])
    assert len(players) == 8
    assert _winners(round_1) == players


def test_br142_br144_br156_final_and_third_place_drawn_together(
    client: TestClient, league_id: UUID, headers: dict[str, str], monster: Json
) -> None:
    _, started = _started(client, league_id, headers, monster)
    round_1 = _round_one(started)
    _play(client, league_id, headers, started, round_1)

    status, drawn = _draw_round(client, league_id, headers, started, 2)

    assert status == 201, drawn
    final, third = drawn["rounds"][1]["matches"]
    assert (final["kind"], third["kind"]) == ("standard", "third_place")
    assert drawn["rounds"][1]["name"] == "final"
    assert _players_of(final["sides"]) == _winners(round_1)
    losers = {p for m in round_1 for s in m["sides"] for p in s["player_ids"]}
    assert _players_of(third["sides"]) == losers - _winners(round_1)
    assert third["number"] == final["number"] + 1


def test_br156_third_place_pairs_do_not_depend_on_the_final(
    client: TestClient,
    session: Session,
    league_id: UUID,
    headers: dict[str, str],
    monster: Json,
) -> None:
    _, started = _started(client, league_id, headers, monster)
    round_1 = _round_one(started)
    _play(client, league_id, headers, started, round_1)
    seed = session.get_one(Tournament, UUID(monster["id"])).rng_seed
    winners = _winners(round_1)
    losers = {p for m in round_1 for s in m["sides"] for p in s["player_ids"]} - winners

    _, drawn = _draw_round(client, league_id, headers, started, 2)

    def pairs(players: set[str], purpose: str) -> list[set[str]]:
        ordered = order_by_lot(
            sorted(UUID(p) for p in players), rng_seed=seed, purpose=purpose
        )
        return [
            {str(a), str(b)} for a, b in zip(ordered[::2], ordered[1::2], strict=True)
        ]

    def stored(match: Json) -> list[set[str]]:
        return [set(side["player_ids"]) for side in match["sides"]]

    final, third = drawn["rounds"][1]["matches"]
    # Each match is drawn from its own players with its own lot (ADR-010).
    assert stored(third) == pairs(losers, THIRD_PLACE_PURPOSE)
    assert stored(final) == pairs(winners, remix_purpose(2))


def test_adr008_stale_expected_round_no_is_409(
    client: TestClient,
    session: Session,
    league_id: UUID,
    headers: dict[str, str],
    monster: Json,
) -> None:
    _, started = _started(client, league_id, headers, monster)
    _play(client, league_id, headers, started, _round_one(started))
    first = _draw_round(client, league_id, headers, started, 2)

    again = _draw_round(client, league_id, headers, started, 2)

    assert first[0] == 201
    assert again == (
        409,
        {"code": "round_number_changed", "detail": {"current_round_no": 2}},
    )
    phase = _knockout(started)
    rounds = session.scalars(
        select(Round).where(Round.phase_id == UUID(phase["id"]), Round.round_no == 2)
    ).all()
    assert len(rounds) == 1


def test_br140_round_not_complete_is_422(
    client: TestClient, league_id: UUID, headers: dict[str, str], monster: Json
) -> None:
    _, started = _started(client, league_id, headers, monster)
    first, _ = _round_one(started)
    _put_result(client, league_id, headers, started, first, _win("side_1"))

    result = _draw_round(client, league_id, headers, started, 2)

    assert result == (
        422,
        {"code": "round_not_complete", "detail": {"matches_left": 1}},
    )


def test_br140_draw_in_a_fixed_pair_knockout_is_422(
    client: TestClient, league_id: UUID, headers: dict[str, str], monster: Json
) -> None:
    shown = _get(
        client,
        league_id,
        monster["id"],
        "/knockout/preview?qualifiers=8&third_place_match=false&mode=seeded_pairs",
        headers,
    )
    body = _start_body(monster, shown)
    body["mode"] = "seeded_pairs"
    started = client.put(
        _t_url(league_id, monster["id"], "/knockout"), json=body, headers=headers
    )
    assert started.status_code == 200, started.text

    result = _draw_round(client, league_id, headers, monster, 2)

    assert result == (
        422,
        {
            "code": "format_not_supported",
            "detail": {"format": "single_elimination", "mode": "seeded_pairs"},
        },
    )


def test_br140_draw_without_a_knockout_is_404(
    client: TestClient, league_id: UUID, headers: dict[str, str], monster: Json
) -> None:
    result = _draw_round(client, league_id, headers, monster, 2)

    assert result == (404, {"code": "knockout_not_found", "detail": {}})


def test_br130_a_drawn_round_takes_free_fields_third_place_after_final(
    client: TestClient, league_id: UUID, headers: dict[str, str], monster: Json
) -> None:
    _, started = _started(client, league_id, headers, monster)
    _play(client, league_id, headers, started, _round_one(started))
    fields = _get(client, league_id, monster["id"], "", headers)["fields"]
    removed = client.delete(
        _t_url(league_id, monster["id"], f"/fields/{fields[-1]['id']}"),
        headers=headers,
    )
    assert removed.status_code == 204, removed.text

    status, drawn = _draw_round(client, league_id, headers, started, 2)

    assert status == 201, drawn
    final, third = drawn["rounds"][1]["matches"]
    # One field is left: the final takes it, the third-place match waits.
    assert (final["state"], final["field_number"]) == ("on_field", 1)
    assert (third["state"], third["field_number"]) == ("ready", None)
    done = _put_result(
        client, league_id, headers, started, {"id": final["match_id"]}, _win("side_1")
    )
    assert done[0] == 200, done[1]
    after = _get(client, league_id, monster["id"], "", headers)
    assert [f["match_id"] for f in after["fields"]] == [third["match_id"]]


def test_br147_br149_a_disabled_player_still_in_stays_in_the_draw(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    monster: Json,
    disable: Callable[[str], None],
) -> None:
    _, started = _started(client, league_id, headers, monster)
    round_1 = _round_one(started)
    player_of = {
        e["player_ids"][0]: e["id"] for e in started["entries"] if e["stage"] == "main"
    }
    winner = next(iter(round_1[0]["sides"][0]["player_ids"]))
    disable(player_of[winner])
    _play(client, league_id, headers, started, round_1)

    status, drawn = _draw_round(client, league_id, headers, started, 2)

    assert status == 201, drawn
    final, _ = drawn["rounds"][1]["matches"]
    assert winner in _players_of(final["sides"])
    assert drawn["left_player_ids"] == [winner]
    # The walkover against that player's pair is the organizer's to record.
    against = "side_2" if winner in final["sides"][0]["player_ids"] else "side_1"
    walkover = _put_result(
        client,
        league_id,
        headers,
        started,
        {"id": final["match_id"]},
        {"walkover_winner": against, "games": []},
    )
    assert walkover[0] == 200, walkover[1]


def test_fr054_br120_a_final_drawn_in_round_two_plays_the_final_format(
    client: TestClient, league_id: UUID, headers: dict[str, str], monster: Json
) -> None:
    _, started = _started(client, league_id, headers, monster, final_match_format="bo3")
    _play(client, league_id, headers, started, _round_one(started))

    status, drawn = _draw_round(client, league_id, headers, started, 2)

    assert status == 201, drawn
    final, third = drawn["rounds"][1]["matches"]
    assert (final["match_format"], third["match_format"]) == ("bo3", "bo1")
    assert drawn["rounds"][0]["matches"][0]["match_format"] == "bo1"
    # The format can change until the final has a result (BR-096).
    before = _set_final(client, league_id, headers, started, None)
    assert before[0] == 200, before[1]
    again = _set_final(client, league_id, headers, started, "bo3")
    assert again[0] == 200, again[1]
    bo1 = _put_result(
        client, league_id, headers, started, {"id": final["match_id"]}, _win("side_1")
    )
    bo3 = _put_result(
        client, league_id, headers, started, {"id": final["match_id"]}, _bo3_win()
    )
    after = _set_final(client, league_id, headers, started, None)
    assert bo1[0] == 422
    assert bo3[0] == 200
    assert after == (
        409,
        {"code": "match_has_result", "detail": {"match_id": final["match_id"]}},
    )


# ---------------------------------------------------------------- the round lock


_CLEAR: Json = {"walkover_winner": None, "games": []}


def _two_rounds(
    client: TestClient, league_id: UUID, headers: dict[str, str], monster: Json
) -> tuple[Json, list[Json], Json]:
    """The tournament, its round 1 (side 1 winning) and round 2 drawn after it."""
    _, started = _started(client, league_id, headers, monster)
    round_1 = _round_one(started)
    _play(client, league_id, headers, started, round_1)
    status, drawn = _draw_round(client, league_id, headers, started, 2)
    assert status == 201, drawn
    return started, round_1, drawn


def test_br146_a_locked_round_takes_a_correction_with_the_same_winner(
    client: TestClient, league_id: UUID, headers: dict[str, str], monster: Json
) -> None:
    started, round_1, _ = _two_rounds(client, league_id, headers, monster)

    status, body = _put_result(
        client, league_id, headers, started, round_1[0], _win("side_1", (10, 2))
    )

    assert status == 200, body
    assert (body["games"][0]["score_1"], body["games"][0]["score_2"]) == (10, 2)
    assert body["outcome"] == "side_1"


def test_br146_a_locked_round_cannot_be_cleared(
    client: TestClient, league_id: UUID, headers: dict[str, str], monster: Json
) -> None:
    started, round_1, _ = _two_rounds(client, league_id, headers, monster)

    result = _put_result(client, league_id, headers, started, round_1[0], _CLEAR)

    assert result == (422, {"code": "round_locked", "detail": {"round_no": 2}})


def test_br146_a_locked_round_cannot_change_its_winner(
    client: TestClient, league_id: UUID, headers: dict[str, str], monster: Json
) -> None:
    started, round_1, drawn = _two_rounds(client, league_id, headers, monster)
    walkover = {"walkover_winner": "side_2", "games": []}

    other = _put_result(client, league_id, headers, started, round_1[0], _win("side_2"))
    forfeited = _put_result(client, league_id, headers, started, round_1[0], walkover)

    expected = (422, {"code": "round_locked", "detail": {"round_no": 2}})
    assert other == expected
    assert forfeited == expected
    # The view says the same as the lock: round 1 is locked, round 2 is not.
    assert [m["winner_locked"] for m in drawn["rounds"][0]["matches"]] == [True] * 2
    assert [m["winner_locked"] for m in drawn["rounds"][1]["matches"]] == [False] * 2


def test_br146_the_final_and_third_place_are_one_round(
    client: TestClient, league_id: UUID, headers: dict[str, str], monster: Json
) -> None:
    started, round_1, drawn = _two_rounds(client, league_id, headers, monster)
    final, third = drawn["rounds"][1]["matches"]
    in_final, in_third = {"id": final["match_id"]}, {"id": third["match_id"]}

    played = [
        _put_result(client, league_id, headers, started, in_final, _win("side_1")),
        _put_result(client, league_id, headers, started, in_third, _win("side_1")),
    ]
    # Both matches are the newest round: neither locks the other.
    changed = _put_result(client, league_id, headers, started, in_final, _win("side_2"))
    cleared = _put_result(client, league_id, headers, started, in_third, _CLEAR)
    still_locked = _put_result(
        client, league_id, headers, started, round_1[0], _win("side_2")
    )

    assert [status for status, _ in played] == [200, 200]
    assert changed[0] == 200, changed[1]
    assert cleared[0] == 200, cleared[1]
    assert still_locked[0] == 422


# ---------------------------------------------------------------- delete a round


def _delete_round(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    tournament: Json,
    round_id: str,
) -> tuple[int, Json | None]:
    response = client.delete(
        _t_url(league_id, tournament["id"], f"/knockout/rounds/{round_id}"),
        headers=headers,
    )
    return response.status_code, response.json() if response.content else None


def _round_id(tournament: Json, round_no: int) -> str:
    [found] = [
        r["id"]
        for r in _rounds(tournament, _knockout(tournament))
        if r["round_no"] == round_no
    ]
    return str(found)


def _pairs(drawn: Json, index: int) -> list[tuple[str, list[list[str]]]]:
    """The kind and the players of each side of the matches of a drawn round."""
    return [
        (match["kind"], [side["player_ids"] for side in match["sides"]])
        for match in drawn["rounds"][index]["matches"]
    ]


def _three_rounds(
    client: TestClient,
    league: League,
    league_id: UUID,
    headers: dict[str, str],
    make_player: Callable[..., Player],
) -> tuple[Json, Json, Json]:
    """Twelve players: the tournament with round 1, then rounds 2 and 3 drawn."""
    twelve = [str(make_player(league=league, name=f"Q{n}").id) for n in range(12)]
    big = _monster_of(client, league_id, headers, twelve)
    _, started = _started(client, league_id, headers, big, 12, third_place_match=False)
    _play(client, league_id, headers, started, _round_one(started))
    status, second = _draw_round(client, league_id, headers, started, 2)
    assert status == 201, second
    _play(client, league_id, headers, started, second["rounds"][1]["matches"])
    status, third = _draw_round(client, league_id, headers, started, 3)
    assert status == 201, third
    return started, second, third


def test_fr046_br146_delete_the_newest_knockout_round(
    client: TestClient, league_id: UUID, headers: dict[str, str], monster: Json
) -> None:
    started, round_1, drawn = _two_rounds(client, league_id, headers, monster)
    locked = _put_result(
        client, league_id, headers, started, round_1[0], _win("side_2")
    )

    deleted = _delete_round(client, league_id, headers, started, _round_id_of(drawn, 2))

    assert locked[0] == 422
    assert deleted == (204, None)
    after = _get(client, league_id, monster["id"], "", headers)
    assert [r["round_no"] for r in _rounds(after, _knockout(after))] == [1]
    # The round before is unlocked (BR-066): a winner can change, and change back.
    changed = _put_result(
        client, league_id, headers, started, round_1[0], _win("side_2")
    )
    restored = _put_result(
        client, league_id, headers, started, round_1[0], _win("side_1")
    )
    assert changed[0] == 200, changed[1]
    assert restored[0] == 200, restored[1]
    # The same players give the same pairs (BR-156).
    status, again = _draw_round(client, league_id, headers, started, 2)
    assert status == 201, again
    assert _pairs(again, 1) == _pairs(drawn, 1)
    assert again["rounds"][1]["round_id"] != drawn["rounds"][1]["round_id"]


def _round_id_of(drawn: Json, round_no: int) -> str:
    [found] = [r["round_id"] for r in drawn["rounds"] if r["round_no"] == round_no]
    return str(found)


def test_fr046_deleting_an_older_knockout_round_is_409(
    client: TestClient,
    league: League,
    league_id: UUID,
    headers: dict[str, str],
    make_player: Callable[..., Player],
) -> None:
    started, second, third = _three_rounds(
        client, league, league_id, headers, make_player
    )
    newest = _round_id_of(third, 3)
    expected = (409, {"code": "round_not_newest", "detail": {"round_id": newest}})

    two = _delete_round(client, league_id, headers, started, _round_id_of(second, 2))
    one = _delete_round(client, league_id, headers, started, _round_id(started, 1))

    assert two == expected
    assert one == expected
    after = _get(client, league_id, started["id"], "", headers)
    assert [r["round_no"] for r in _rounds(after, _knockout(after))] == [1, 2, 3]


def test_adr008_a_repeated_knockout_round_delete_is_404(
    client: TestClient, league_id: UUID, headers: dict[str, str], monster: Json
) -> None:
    started, _, drawn = _two_rounds(client, league_id, headers, monster)
    group = next(p for p in started["phases"] if p["kind"] == "group")
    [group_round] = _rounds(started, group)
    gone = {"code": "round_not_found", "detail": {}}

    first = _delete_round(client, league_id, headers, started, _round_id_of(drawn, 2))
    repeat = _delete_round(client, league_id, headers, started, _round_id_of(drawn, 2))
    in_group = _delete_round(client, league_id, headers, started, group_round["id"])
    unknown = _delete_round(client, league_id, headers, started, str(uuid7()))

    assert first[0] == 204
    assert repeat == (404, gone)
    assert in_group == (404, gone)
    assert unknown == (404, gone)


def test_fr046_br087_deleting_knockout_round_one_deletes_the_knockout(
    client: TestClient,
    session: Session,
    league_id: UUID,
    headers: dict[str, str],
    monster: Json,
) -> None:
    _, started = _started(client, league_id, headers, monster)
    knockout = _knockout(started)
    round_1 = _round_one(started)

    deleted = _delete_round(client, league_id, headers, started, _round_id(started, 1))
    repeat = _delete_round(client, league_id, headers, started, _round_id(started, 1))

    assert deleted == (204, None)
    assert repeat[0] == 404
    after = _get(client, league_id, monster["id"], "", headers)
    assert [p["kind"] for p in after["phases"]] == ["group"]
    assert all(e["stage"] == "main" for e in after["entries"])
    assert session.get(TournamentPhase, UUID(knockout["id"])) is None
    assert all(f["match_id"] not in {m["id"] for m in round_1} for f in after["fields"])
    # The group phase is unlocked again (BR-087).
    group = after["phases"][0]
    [group_round] = _rounds(after, group)
    result = _put_result(
        client, league_id, headers, after, group_round["matches"][0], _win("side_2")
    )
    assert result[0] == 200, result[1]


def test_fr046_deleting_the_whole_knockout_with_later_rounds(
    client: TestClient,
    session: Session,
    league: League,
    league_id: UUID,
    headers: dict[str, str],
    make_player: Callable[..., Player],
) -> None:
    started, _, _ = _three_rounds(client, league, league_id, headers, make_player)
    knockout = _knockout(started)

    response = client.delete(
        _t_url(league_id, started["id"], f"/phases/{knockout['id']}"),
        headers=headers,
    )

    assert response.status_code == 204, response.text
    after = _get(client, league_id, started["id"], "", headers)
    assert [p["kind"] for p in after["phases"]] == ["group"]
    assert not [r for r in after["rounds"] if r["phase_id"] == knockout["id"]]
    left = session.scalars(
        select(Round).where(Round.phase_id == UUID(knockout["id"]))
    ).all()
    assert left == []


def test_br095_br112_deleting_the_final_round_of_a_finished_tournament(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    monster: Json,
) -> None:
    started, _, drawn = _two_rounds(client, league_id, headers, monster)
    season = monster["season_id"]
    _play(client, league_id, headers, started, drawn["rounds"][1]["matches"])
    finished = _get(client, league_id, monster["id"], "", headers)
    counted = client.get(
        _url(league_id, f"/seasons/{season}/standings"), headers=headers
    )
    assert finished["state"] == "finished"
    assert len(counted.json()) == 8

    deleted = _delete_round(client, league_id, headers, started, _round_id_of(drawn, 2))

    assert deleted == (204, None)
    after = _get(client, league_id, monster["id"], "", headers)
    assert after["state"] == "in_progress"
    assert [r["round_no"] for r in _rounds(after, _knockout(after))] == [1]
    # The tournament no longer counts in the season (BR-112).
    uncounted = client.get(
        _url(league_id, f"/seasons/{season}/standings"), headers=headers
    )
    assert uncounted.json() == []
    # The final's round is drawn again from the same winners.
    status, again = _draw_round(client, league_id, headers, started, 2)
    assert status == 201, again
    assert _pairs(again, 1) == _pairs(drawn, 1)


def test_fr046_deleting_a_round_of_a_fixed_pair_knockout_is_422(
    client: TestClient, league_id: UUID, headers: dict[str, str], monster: Json
) -> None:
    shown = _get(
        client,
        league_id,
        monster["id"],
        "/knockout/preview?qualifiers=8&third_place_match=false&mode=seeded_pairs",
        headers,
    )
    body = _start_body(monster, shown)
    body["mode"] = "seeded_pairs"
    response = client.put(
        _t_url(league_id, monster["id"], "/knockout"), json=body, headers=headers
    )
    assert response.status_code == 200, response.text

    result = _delete_round(
        client, league_id, headers, response.json(), _round_id(response.json(), 1)
    )

    assert result == (
        422,
        {
            "code": "format_not_supported",
            "detail": {"format": "single_elimination", "mode": "seeded_pairs"},
        },
    )


# ---------------------------------------------------------------- finish and places


def _knockout_played(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    tournament: Json,
    *,
    third_place_match: bool = True,
    qualifiers: int = 8,
) -> tuple[Json, list[Json], Json]:
    """Round 1 played (side 1 winning), round 2 drawn, not yet played."""
    _, started = _started(
        client,
        league_id,
        headers,
        tournament,
        qualifiers,
        third_place_match=third_place_match,
    )
    round_1 = _round_one(started)
    _play(client, league_id, headers, started, round_1)
    status, drawn = _draw_round(client, league_id, headers, started, 2)
    assert status == 201, drawn
    return started, round_1, drawn


def _entry_of(started: Json) -> dict[str, str]:
    """Each player's main entry."""
    return {
        e["player_ids"][0]: e["id"] for e in started["entries"] if e["stage"] == "main"
    }


def _places(
    client: TestClient, league_id: UUID, headers: dict[str, str], tournament: Json
) -> Json:
    return _get(client, league_id, tournament["id"], "/places", headers)


def _state(
    client: TestClient, league_id: UUID, headers: dict[str, str], tournament: Json
) -> str:
    state: str = _get(client, league_id, tournament["id"], "", headers)["state"]
    return state


def test_fr037_not_finished_after_round_one(
    client: TestClient, league_id: UUID, headers: dict[str, str], monster: Json
) -> None:
    _, started = _started(client, league_id, headers, monster)
    _play(client, league_id, headers, started, _round_one(started))

    assert _state(client, league_id, headers, monster) == "in_progress"
    assert _places(client, league_id, headers, monster) == {
        "complete": False,
        "rows": [],
    }
    status, drawn = _draw_round(client, league_id, headers, started, 2)
    assert status == 201, drawn
    # The final is drawn, but not played.
    assert _state(client, league_id, headers, monster) == "in_progress"


def test_fr037_finishes_with_the_final_and_third_place(
    client: TestClient, league_id: UUID, headers: dict[str, str], monster: Json
) -> None:
    started, _, drawn = _knockout_played(client, league_id, headers, monster)
    final, third = drawn["rounds"][1]["matches"]

    _play(client, league_id, headers, started, [final])
    after_final = _state(client, league_id, headers, monster)
    _play(client, league_id, headers, started, [third])
    third_result = {"id": third["match_id"]}

    assert after_final == "in_progress"  # the third-place match is still open
    assert _state(client, league_id, headers, monster) == "finished"
    assert _places(client, league_id, headers, monster)["complete"] is True
    # Clearing the third-place result takes it back (BR-095).
    cleared = _put_result(client, league_id, headers, started, third_result, _CLEAR)
    assert cleared[0] == 200, cleared[1]
    assert _state(client, league_id, headers, monster) == "in_progress"


def test_fr037_two_pairs_finish_with_round_one(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    players: list[str],
) -> None:
    four = _monster_of(client, league_id, headers, players[:4])
    _, started = _started(client, league_id, headers, four, 4, third_place_match=False)
    [final] = _round_one(started)
    assert _state(client, league_id, headers, four) == "in_progress"

    _play(client, league_id, headers, started, [final])

    assert _state(client, league_id, headers, four) == "finished"
    rows = _places(client, league_id, headers, four)["rows"]
    assert [row["place"] for row in rows] == [1, 1, 2, 2]
    assert {row["reason"]["kind"] for row in rows} == {"won_final", "lost_final"}


def test_br145_places_per_player_with_partner(
    client: TestClient, league_id: UUID, headers: dict[str, str], monster: Json
) -> None:
    started, _, drawn = _knockout_played(client, league_id, headers, monster)
    final, third = drawn["rounds"][1]["matches"]
    _play(client, league_id, headers, started, [final, third])
    entry_of = _entry_of(started)

    rows = _places(client, league_id, headers, monster)["rows"]

    by_entry = {row["entry_id"]: row for row in rows}
    assert set(by_entry) == set(entry_of.values())
    assert len(rows) == 8  # one row per player
    assert [row["place"] for row in rows] == sorted(row["place"] for row in rows)
    # Side 1 wins each match 10:5: place, points and why, for both of a pair.
    expected = [
        (final["sides"][0], 1, 10, "won_final", (10, 5)),
        (final["sides"][1], 2, 8, "lost_final", (5, 10)),
        (third["sides"][0], 3, 6, "won_third_place", (10, 5)),
        (third["sides"][1], 4, 4, "lost_third_place", (5, 10)),
    ]
    for side, place, points, kind, score in expected:
        first, second = side["player_ids"]
        for player, partner in ((first, second), (second, first)):
            row = by_entry[entry_of[player]]
            assert (row["place"], row["points_per_player"]) == (place, points)
            assert row["reason"]["kind"] == kind
            assert row["reason"]["round"] == "final"
            assert row["reason"]["score"] == list(score)
            assert row["reason"]["opponent_entry_id"] is None
            assert row["reason"]["partner_entry_id"] == entry_of[partner]
            assert row["reason"]["group_place"] is not None


def test_br145_br111_semifinal_losers_share_3rd_without_third_place(
    client: TestClient, league_id: UUID, headers: dict[str, str], monster: Json
) -> None:
    started, round_1, drawn = _knockout_played(
        client, league_id, headers, monster, third_place_match=False
    )
    _play(client, league_id, headers, started, drawn["rounds"][1]["matches"])
    entry_of = _entry_of(started)

    rows = _places(client, league_id, headers, monster)["rows"]

    assert [row["place"] for row in rows] == [1, 1, 2, 2, 3, 3, 3, 3]
    shared = rows[4:]
    # (6 + 4) / 2 points each (BR-111), and why: out in the semifinal.
    assert {row["points_per_player"] for row in shared} == {5}
    assert {row["reason"]["kind"] for row in shared} == {"lost_in_round"}
    assert {row["reason"]["round"] for row in shared} == {"semifinal"}
    losers = {p for match in round_1 for p in match["sides"][1]["player_ids"]}
    assert {row["entry_id"] for row in shared} == {entry_of[p] for p in losers}


def test_br103_best_non_qualifier_is_5th_after_4_pairs(
    client: TestClient,
    league: League,
    league_id: UUID,
    headers: dict[str, str],
    make_player: Callable[..., Player],
) -> None:
    twelve = [str(make_player(league=league, name=f"Q{n}").id) for n in range(12)]
    big = _monster_of(client, league_id, headers, twelve)
    started, round_1, drawn = _knockout_played(
        client, league_id, headers, big, third_place_match=False
    )
    _play(client, league_id, headers, started, drawn["rounds"][1]["matches"])
    entry_of = _entry_of(started)
    qualified = {
        p for match in round_1 for s in match["sides"] for p in s["player_ids"]
    }

    rows = _places(client, league_id, headers, big)["rows"]

    rest = [row for row in rows if row["reason"]["kind"] == "group_place"]
    assert len(rows) == 12
    assert {row["entry_id"] for row in rest} == {
        entry_of[p] for p in twelve if p not in qualified
    }
    # Places count pairs: four knockout pairs fill 1st to 4th (BR-103).
    assert min(row["place"] for row in rest) == 5
    # Players level in the group phase share a place (BR-103, BR-104), and the
    # 5th of the table earns 2 points where it is not shared (BR-110).
    shared: dict[int, set[int]] = {}
    for row in rest:
        shared.setdefault(row["reason"]["group_place"], set()).add(row["place"])
    assert all(len(places) == 1 for places in shared.values())
    assert rest[0]["points_per_player"] == (
        2 if rest[0]["place"] != rest[1]["place"] else 1
    )
    for row in rest:
        assert row["reason"]["partner_entry_id"] is None
        assert (row["reason"]["round"], row["reason"]["score"]) == (None, None)
        assert row["reason"]["opponent_entry_id"] is None
    # They follow in their group-phase order.
    assert [row["reason"]["group_place"] for row in rest] == sorted(
        row["reason"]["group_place"] for row in rest
    )


def test_br104_pairs_sharing_a_place_in_lot_order(
    client: TestClient, league_id: UUID, headers: dict[str, str], monster: Json
) -> None:
    started, round_1, drawn = _knockout_played(
        client, league_id, headers, monster, third_place_match=False
    )
    _play(client, league_id, headers, started, drawn["rounds"][1]["matches"])
    entry_of = _entry_of(started)

    rows = _places(client, league_id, headers, monster)["rows"]

    # The pairs that share 3rd come in the order of the drawn matches (#94 A),
    # each pair's two players next to each other.
    shared = [row["entry_id"] for row in rows if row["place"] == 3]
    drawn_order = [
        {entry_of[p] for p in match["sides"][1]["player_ids"]} for match in round_1
    ]
    assert [set(shared[0:2]), set(shared[2:4])] == drawn_order
    assert _places(client, league_id, headers, monster)["rows"] == rows


def test_br112_season_standings_count_a_lord_have_mercy_tournament(
    client: TestClient, league_id: UUID, headers: dict[str, str], monster: Json
) -> None:
    started, _, drawn = _knockout_played(client, league_id, headers, monster)
    season = f"/seasons/{monster['season_id']}/standings"
    before = client.get(_url(league_id, season), headers=headers)
    _play(client, league_id, headers, started, drawn["rounds"][1]["matches"])
    entry_of = _entry_of(started)

    after = client.get(_url(league_id, season), headers=headers)

    assert before.json() == []
    rows = after.json()
    places = _places(client, league_id, headers, monster)["rows"]
    points = {row["entry_id"]: row["points_per_player"] for row in places}
    assert {row["player_id"]: row["points"] for row in rows} == {
        player: points[entry] for player, entry in entry_of.items()
    }
    assert sorted(row["points"] for row in rows) == [4, 4, 6, 6, 8, 8, 10, 10]
    assert {row["tournaments_played"] for row in rows} == {1}
    assert sorted(row["tournament_wins"] for row in rows) == [0] * 6 + [1, 1]


# ---------------------------------------------------------------- round by round


def _rounds_view(
    client: TestClient, league_id: UUID, headers: dict[str, str], tournament: Json
) -> Json:
    return _get(client, league_id, tournament["id"], "/knockout/rounds", headers)


def _public(league: League, tournament_id: str, rest: str = "") -> str:
    return f"/api/v1/public/{league.share_token}/tournaments/{tournament_id}{rest}"


def test_br155_rounds_view_lists_each_round_with_its_pairs(
    client: TestClient, league_id: UUID, headers: dict[str, str], monster: Json
) -> None:
    _, started = _started(client, league_id, headers, monster)
    round_1 = _round_one(started)
    _play(client, league_id, headers, started, round_1)
    status, drawn = _draw_round(client, league_id, headers, started, 2)
    assert status == 201, drawn

    view = _rounds_view(client, league_id, headers, monster)

    assert view == drawn  # what the draw answered is what the read answers
    assert (view["size"], view["round_count"], view["third_place_match"]) == (
        4,
        2,
        True,
    )
    assert view["phase_id"] == _knockout(started)["id"]
    assert view["can_draw_next"] is False
    assert view["left_player_ids"] == []
    assert [(r["round_no"], r["name"]) for r in view["rounds"]] == [
        (1, "semifinal"),
        (2, "final"),
    ]
    first, second = view["rounds"]
    assert [m["match_id"] for m in first["matches"]] == [m["id"] for m in round_1]
    assert first["result_count"] == 2
    assert second["result_count"] == 0
    for match in first["matches"]:
        assert match["state"] == "played"
        assert match["score"] == [10, 5]
        assert all(len(side["player_ids"]) == 2 for side in match["sides"])
        assert all(side["entry_id"] is not None for side in match["sides"])
    final, third = second["matches"]
    assert (final["kind"], third["kind"]) == ("standard", "third_place")
    assert {m["state"] for m in (final, third)} <= {"on_field", "ready"}
    # A later round's pair is not an entry (D4).
    assert all(side["entry_id"] is None for side in final["sides"])
    assert [m["winner_locked"] for m in first["matches"]] == [True, True]
    assert [m["winner_locked"] for m in second["matches"]] == [False, False]


def test_br155_rounds_view_shows_byes_and_draws_the_next_round_flag(
    client: TestClient,
    league: League,
    league_id: UUID,
    headers: dict[str, str],
    make_player: Callable[..., Player],
) -> None:
    twelve = [str(make_player(league=league, name=f"Q{n}").id) for n in range(12)]
    big = _monster_of(client, league_id, headers, twelve)
    _, started = _started(client, league_id, headers, big, 12, third_place_match=False)
    round_1 = _round_one(started)
    before = _rounds_view(client, league_id, headers, big)
    _play(client, league_id, headers, started, round_1)

    after = _rounds_view(client, league_id, headers, big)

    matches = before["rounds"][0]["matches"]
    byes = [m for m in matches if m["state"] == "bye"]
    assert len(byes) == 2
    for bye in byes:
        assert [side["is_bye"] for side in bye["sides"]].count(True) == 1
        assert bye["number"] is None
        assert bye["winner_locked"] is False
        assert bye["field_number"] is None
    assert before["can_draw_next"] is False
    assert after["can_draw_next"] is True
    assert after["rounds"][0]["result_count"] == 2  # a bye has no result


def test_br155_the_view_marks_players_who_left(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    monster: Json,
    disable: Callable[[str], None],
) -> None:
    _, started = _started(client, league_id, headers, monster)
    order = _order(client, league_id, headers, monster)
    player_of = {
        e["id"]: e["player_ids"][0] for e in started["entries"] if e["stage"] == "main"
    }
    gone = player_of[order[0]]
    disable(order[0])

    view = _rounds_view(client, league_id, headers, monster)

    assert view["left_player_ids"] == [gone]
    sides = [s for m in view["rounds"][0]["matches"] for s in m["sides"]]
    marked = [side for side in sides if side["left_player_ids"]]
    assert [side["left_player_ids"] for side in marked] == [[gone]]
    assert gone in marked[0]["player_ids"]


def test_br146_view_marks_locked_winners_and_result_count(
    client: TestClient, league_id: UUID, headers: dict[str, str], monster: Json
) -> None:
    started, _, drawn = _two_rounds(client, league_id, headers, monster)
    final, third = drawn["rounds"][1]["matches"]
    _play(client, league_id, headers, started, [final])

    view = _rounds_view(client, league_id, headers, monster)

    first, second = view["rounds"]
    assert [m["winner_locked"] for m in first["matches"]] == [True, True]
    assert [m["winner_locked"] for m in second["matches"]] == [False, False]
    assert (first["result_count"], second["result_count"]) == (2, 1)
    states = {m["match_id"]: m["state"] for m in second["matches"]}
    assert states[final["match_id"]] == "played"
    assert states[third["match_id"]] in {"on_field", "ready"}
    # Deleting round 2 unlocks round 1 again (BR-146).
    deleted = _delete_round(
        client, league_id, headers, started, drawn["rounds"][1]["round_id"]
    )
    assert deleted == (204, None)
    again = _rounds_view(client, league_id, headers, monster)
    assert [m["winner_locked"] for m in again["rounds"][0]["matches"]] == [False] * 2


def test_br155_match_numbers_count_the_group_phase_first_and_skip_byes(
    client: TestClient,
    league: League,
    league_id: UUID,
    headers: dict[str, str],
    make_player: Callable[..., Player],
) -> None:
    twelve = [str(make_player(league=league, name=f"Q{n}").id) for n in range(12)]
    big = _monster_of(client, league_id, headers, twelve)
    _, started = _started(client, league_id, headers, big, 12)
    _play(client, league_id, headers, started, _round_one(started))
    status, second = _draw_round(client, league_id, headers, started, 2)
    assert status == 201, second
    _play(client, league_id, headers, started, second["rounds"][1]["matches"])
    status, drawn = _draw_round(client, league_id, headers, started, 3)
    assert status == 201, drawn
    group = [r for r in started["rounds"] if r["phase_id"] != _knockout(started)["id"]]
    group_matches = sum(not _is_bye(m) for r in group for m in r["matches"])

    view = _rounds_view(client, league_id, headers, big)

    assert view == drawn
    numbers = [
        m["number"] for r in view["rounds"] for m in r["matches"] if m["state"] != "bye"
    ]
    assert numbers == list(range(group_matches + 1, group_matches + 1 + len(numbers)))
    assert all(
        m["number"] is None
        for r in view["rounds"]
        for m in r["matches"]
        if m["state"] == "bye"
    )
    # The third-place match comes after the final.
    final, third = view["rounds"][2]["matches"]
    assert (final["kind"], third["kind"]) == ("standard", "third_place")
    assert third["number"] == final["number"] + 1


def test_br155_share_link_shows_the_rounds(
    client: TestClient,
    league: League,
    league_id: UUID,
    headers: dict[str, str],
    monster: Json,
    disable: Callable[[str], None],
) -> None:
    _, started = _started(client, league_id, headers, monster)
    disable(_order(client, league_id, headers, monster)[0])
    _play(client, league_id, headers, started, _round_one(started))
    status, drawn = _draw_round(client, league_id, headers, started, 2)
    assert status == 201, drawn

    response = client.get(_public(league, monster["id"], "/knockout/rounds"))

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    shown: Json = response.json()
    assert set(shown) == {
        "phase_id",
        "size",
        "round_count",
        "third_place_match",
        "match_format",
        "final_match_format",
        "left_player_ids",
        "rounds",
    }
    assert shown["left_player_ids"] == drawn["left_player_ids"] != []
    for round_ in shown["rounds"]:
        assert set(round_) == {"round_id", "round_no", "name", "matches"}
        for match in round_["matches"]:
            assert set(match) == {
                "match_id",
                "number",
                "position",
                "kind",
                "state",
                "sides",
                "outcome",
                "is_walkover",
                "score",
                "match_format",
                "field_number",
            }
            for side in match["sides"]:
                assert set(side) == {
                    "player_ids",
                    "entry_id",
                    "is_bye",
                    "left_player_ids",
                }
    # The same rounds and matches as the organizer sees.
    assert [[m["match_id"] for m in r["matches"]] for r in shown["rounds"]] == [
        [m["match_id"] for m in r["matches"]] for r in drawn["rounds"]
    ]


def test_br155_share_link_rounds_need_a_started_tournament(
    client: TestClient,
    league: League,
    league_id: UUID,
    headers: dict[str, str],
    monster: Json,
) -> None:
    created = client.post(
        _url(league_id, "/tournaments"),
        json={"id": str(uuid7()), **MONSTER_DYP},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    in_setup = created.json()["tournament_id"]

    setup = client.get(_public(league, in_setup, "/knockout/rounds"))
    none = client.get(_public(league, monster["id"], "/knockout/rounds"))
    unknown = client.get(_public(league, str(uuid7()), "/knockout/rounds"))
    token = client.get(
        _public(league, monster["id"], "/knockout/rounds").replace(
            league.share_token, "nope"
        )
    )

    assert setup.status_code == 404
    assert setup.json() == {"code": "tournament_not_found", "detail": {}}
    assert setup.json() == unknown.json()
    assert (none.status_code, none.json()) == (
        404,
        {"code": "knockout_not_found", "detail": {}},
    )
    assert token.json() == {"code": "share_link_not_found", "detail": {}}


def test_br155_bracket_of_lord_have_mercy_is_422(
    client: TestClient,
    league: League,
    league_id: UUID,
    headers: dict[str, str],
    monster: Json,
) -> None:
    _started(client, league_id, headers, monster)
    expected = {
        "code": "format_not_supported",
        "detail": {"format": "single_elimination", "mode": "lord_have_mercy"},
    }

    organizer = client.get(
        _t_url(league_id, monster["id"], "/bracket"), headers=headers
    )
    public = client.get(_public(league, monster["id"], "/bracket"))

    assert (organizer.status_code, organizer.json()) == (422, expected)
    assert (public.status_code, public.json()) == (422, expected)


def test_br155_rounds_view_of_a_fixed_pair_knockout_is_422(
    client: TestClient,
    league: League,
    league_id: UUID,
    headers: dict[str, str],
    monster: Json,
) -> None:
    shown = _get(
        client,
        league_id,
        monster["id"],
        "/knockout/preview?qualifiers=8&third_place_match=false&mode=seeded_pairs",
        headers,
    )
    body = _start_body(monster, shown)
    body["mode"] = "seeded_pairs"
    started = client.put(
        _t_url(league_id, monster["id"], "/knockout"), json=body, headers=headers
    )
    assert started.status_code == 200, started.text
    expected = {
        "code": "format_not_supported",
        "detail": {"format": "single_elimination", "mode": "seeded_pairs"},
    }

    organizer = client.get(
        _t_url(league_id, monster["id"], "/knockout/rounds"), headers=headers
    )
    public = client.get(_public(league, monster["id"], "/knockout/rounds"))

    assert (organizer.status_code, organizer.json()) == (422, expected)
    assert (public.status_code, public.json()) == (422, expected)


def test_br155_rounds_view_without_a_knockout_is_404(
    client: TestClient, league_id: UUID, headers: dict[str, str], monster: Json
) -> None:
    response = client.get(
        _t_url(league_id, monster["id"], "/knockout/rounds"), headers=headers
    )

    assert (response.status_code, response.json()) == (
        404,
        {"code": "knockout_not_found", "detail": {}},
    )


def test_lord_have_mercy_reads_without_errors(
    client: TestClient,
    league: League,
    league_id: UUID,
    headers: dict[str, str],
    monster: Json,
) -> None:
    started, _, drawn = _knockout_played(client, league_id, headers, monster)

    def reads() -> list[int]:
        organizer = [
            client.get(_t_url(league_id, monster["id"], rest), headers=headers)
            for rest in ("", "/play", "/places", "/knockout/rounds")
        ]
        public = [
            client.get(_public(league, monster["id"], rest))
            for rest in ("", "/standings", "/places", "/knockout/rounds")
        ]
        return [r.status_code for r in (*organizer, *public)]

    after_round_two = reads()
    # The final and the third-place match swap fields by hand (FR-093).
    tournament = _get(client, league_id, monster["id"], "", headers)
    field_of = {f["match_id"]: f["id"] for f in tournament["fields"] if f["match_id"]}
    final, third = drawn["rounds"][1]["matches"]
    swap = client.put(
        _t_url(league_id, monster["id"], "/fields/placements"),
        json={
            "placements": [
                {
                    "match_id": final["match_id"],
                    "field_id": field_of[third["match_id"]],
                    "from_field_id": field_of[final["match_id"]],
                },
                {
                    "match_id": third["match_id"],
                    "field_id": field_of[final["match_id"]],
                    "from_field_id": field_of[third["match_id"]],
                },
            ]
        },
        headers=headers,
    )
    after_placement = reads()
    _play(client, league_id, headers, started, drawn["rounds"][1]["matches"])
    finished = reads()

    assert after_round_two == [200] * 8
    assert swap.status_code == 200, swap.text
    assert after_placement == [200] * 8
    assert finished == [200] * 8
    assert _state(client, league_id, headers, monster) == "finished"
