"""The knockout after Monster DYP rounds and its contract with the draw counter
(FR-045, BR-081 to BR-083, BR-085, BR-086, ADR-008, ADR-010).
"""

from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid7

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tourneyhub.db.models.entries import Entry
from tourneyhub.db.models.leagues import League, Player
from tourneyhub.db.models.tournaments import Tournament, TournamentPhase
from tourneyhub.engine.ids import PlayerId
from tourneyhub.engine.monster_dyp import MonsterStanding, select_monster_knockout
from tourneyhub.engine.tournaments import EntryStage, MonsterKnockoutMode, PhaseKind

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


# ---------------------------------------------------------------- after Monster DYP

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

MODES = [
    pytest.param("seeded_pairs", 8, id="BR-081"),
    pytest.param("singles", 4, id="BR-082"),
    pytest.param("a_little_mercy", 8, id="BR-083"),
]


def win(side: str, score: tuple[int, int] = (10, 5)) -> Json:
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
            json=win("side_1", (10, 1 + index)),
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


def _player_of(tournament: Json) -> dict[str, str]:
    """Each main entry's one player (DATA-MODEL §4.4)."""
    return {
        e["id"]: e["player_ids"][0]
        for e in tournament["entries"]
        if e["stage"] == "main"
    }


def _monster_preview(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    tournament: Json,
    *,
    mode: str,
    qualifiers: int,
) -> Json:
    return _get(
        client,
        league_id,
        tournament["id"],
        f"/knockout/preview?qualifiers={qualifiers}&third_place_match=false"
        f"&mode={mode}",
        headers,
    )


def _members(shown: Json) -> list[list[str]]:
    """Each previewed entry's group-phase entries, seed 1 first."""
    return [[m["entry_id"] for m in e["members"]] for e in shown["entries"]]


def _start_monster(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    tournament: Json,
    *,
    mode: str,
    qualifiers: int,
) -> tuple[Json, Json]:
    """Start the knockout the preview shows; the preview and the tournament."""
    shown = _monster_preview(
        client, league_id, headers, tournament, mode=mode, qualifiers=qualifiers
    )
    response = client.put(
        _t_url(league_id, tournament["id"], "/knockout"),
        json={
            "expected_current_phase_id": tournament["current_phase_id"],
            "expected_qualifier_ids": [
                member for members in _members(shown) for member in members
            ],
            "expected_draw_counter": shown["draw_counter"],
            "qualifiers": qualifiers,
            "third_place_match": False,
            "match_format": "bo1",
            "final_match_format": None,
            "mode": mode,
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    started: Json = response.json()
    return shown, started


def _knockout_entries(tournament: Json) -> list[Json]:
    return sorted(
        (e for e in tournament["entries"] if e["stage"] == "knockout"),
        key=lambda e: e["seed"],
    )


def test_br081_seeded_pairs_preview_partners_1st_with_the_half_plus_1st(
    client: TestClient, league_id: UUID, headers: dict[str, str], monster: Json
) -> None:
    order = _order(client, league_id, headers, monster)
    play = _get(client, league_id, monster["id"], "/play", headers)
    place = {row["entry_id"]: row["place"] for row in play["standings"]}

    shown = _monster_preview(
        client, league_id, headers, monster, mode="seeded_pairs", qualifiers=8
    )

    assert _members(shown) == [[order[i], order[i + 4]] for i in range(4)]
    assert [[m["place"] for m in e["members"]] for e in shown["entries"]] == [
        [place[order[i]], place[order[i + 4]]] for i in range(4)
    ]
    assert [e["seed"] for e in shown["entries"]] == [1, 2, 3, 4]
    assert (shown["bracket_size"], shown["first_round"]) == (4, [[1, 4], [2, 3]])
    assert (shown["problem"], shown["qualifiers"], shown["max_qualifiers"]) == (
        None,
        8,
        8,
    )
    assert shown["skipped_entry_ids"] == []


def test_br081_seeded_pairs_start_creates_pair_entries(
    client: TestClient,
    session: Session,
    league_id: UUID,
    headers: dict[str, str],
    monster: Json,
) -> None:
    order = _order(client, league_id, headers, monster)
    player_of = _player_of(monster)

    _, started = _start_monster(
        client, league_id, headers, monster, mode="seeded_pairs", qualifiers=8
    )

    phase = next(p for p in started["phases"] if p["kind"] == "knockout")
    assert (phase["monster_knockout_mode"], phase["qualifiers"]) == ("seeded_pairs", 8)
    entries = _knockout_entries(started)
    assert [(e["kind"], len(e["player_ids"])) for e in entries] == [("pair", 2)] * 4
    assert [set(e["player_ids"]) for e in entries] == [
        {player_of[order[i]], player_of[order[i + 4]]} for i in range(4)
    ]
    rows = session.scalars(
        select(Entry).where(
            Entry.tournament_id == UUID(monster["id"]),
            Entry.stage == EntryStage.KNOCKOUT,
        )
    ).all()
    assert sorted(str(row.id) for row in rows) == sorted(e["id"] for e in entries)
    assert all(row.source_entry_id is None for row in rows)
    round_1 = next(
        r
        for r in started["rounds"]
        if r["phase_id"] == phase["id"] and r["round_no"] == 1
    )
    sides = [side for match in round_1["matches"] for side in match["sides"]]
    by_id = {e["id"]: set(e["player_ids"]) for e in entries}
    assert {side["entry_id"] for side in sides} == set(by_id)
    assert all(set(side["player_ids"]) == by_id[side["entry_id"]] for side in sides)


def test_br082_singles_entries_continue_the_players(
    client: TestClient,
    session: Session,
    league_id: UUID,
    headers: dict[str, str],
    monster: Json,
) -> None:
    order = _order(client, league_id, headers, monster)

    shown, started = _start_monster(
        client, league_id, headers, monster, mode="singles", qualifiers=4
    )

    assert _members(shown) == [[order[i]] for i in range(4)]
    entries = _knockout_entries(started)
    assert [e["kind"] for e in entries] == ["player"] * 4
    source = {
        str(row.id): row.source_entry_id
        for row in session.scalars(
            select(Entry).where(
                Entry.tournament_id == UUID(monster["id"]),
                Entry.stage == EntryStage.KNOCKOUT,
            )
        )
    }
    assert [source[e["id"]] for e in entries] == [
        UUID(order[e["seed"] - 1]) for e in entries
    ]


def test_br083_a_little_mercy_pairs_a_top_half_player_with_a_bottom_half_player(
    client: TestClient,
    session: Session,
    league_id: UUID,
    headers: dict[str, str],
    monster: Json,
) -> None:
    play = _get(client, league_id, monster["id"], "/play", headers)
    order = [row["entry_id"] for row in play["standings"]]
    player_of = _player_of(monster)
    entry_of = {player: entry for entry, player in player_of.items()}

    shown = _monster_preview(
        client, league_id, headers, monster, mode="a_little_mercy", qualifiers=8
    )

    members = _members(shown)
    assert [pair[0] for pair in members] == order[:4]
    assert {pair[1] for pair in members} == set(order[4:8])
    assert all(e["decided_by_lot"] for e in shown["entries"])
    stored = session.get_one(Tournament, UUID(monster["id"]))
    drawn = select_monster_knockout(
        [
            MonsterStanding(
                player_id=PlayerId(UUID(player_of[row["entry_id"]])),
                position=position,
                place=row["place"],
                points=row["points"],
                bh1=row["bh1"],
                bh2=row["bh2"],
                score_difference=row["score_difference"],
                played=row["played"],
                won=row["won"],
                drawn=row["drawn"],
                lost=row["lost"],
                sat_out=row["sat_out"],
                is_decided_by_lot=False,
            )
            for position, row in enumerate(play["standings"], start=1)
        ],
        qualifiers=8,
        mode=MonsterKnockoutMode.A_LITTLE_MERCY,
        rng_seed=stored.rng_seed,
        draw_counter=stored.draw_counter,
    )
    assert members == [
        [entry_of[str(player)] for player in entry.player_ids]
        for entry in drawn.entries
    ]


@pytest.mark.parametrize(("mode", "qualifiers"), MODES)
def test_fr045_the_start_writes_the_previewed_pairs(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    monster: Json,
    mode: str,
    qualifiers: int,
) -> None:
    shown, started = _start_monster(
        client, league_id, headers, monster, mode=mode, qualifiers=qualifiers
    )

    player_of = _player_of(started)
    assert [(e["seed"], set(e["player_ids"])) for e in _knockout_entries(started)] == [
        (e["seed"], {player_of[m["entry_id"]] for m in e["members"]})
        for e in shown["entries"]
    ]
    bracket = _get(client, league_id, monster["id"], "/bracket", headers)
    assert [
        sorted(side["seed"] for side in match["sides"])
        for match in bracket["rounds"][0]["matches"]
    ] == shown["first_round"]


def test_br086_pairs_stay_together(
    client: TestClient, league_id: UUID, headers: dict[str, str], monster: Json
) -> None:
    _, started = _start_monster(
        client, league_id, headers, monster, mode="seeded_pairs", qualifiers=8
    )
    players = {e["id"]: e["player_ids"] for e in _knockout_entries(started)}
    bracket = _get(client, league_id, monster["id"], "/bracket", headers)
    semis = bracket["rounds"][0]["matches"]

    for semi, side in zip(semis, ("side_1", "side_2"), strict=True):
        result = client.put(
            _t_url(league_id, monster["id"], f"/matches/{semi['match_id']}/result"),
            json=win(side),
            headers=headers,
        )
        assert result.status_code == 200, result.text

    after = _get(client, league_id, monster["id"], "/bracket", headers)
    final = next(m for m in after["rounds"][1]["matches"] if m["kind"] == "standard")
    winners = [semis[0]["sides"][0]["entry_id"], semis[1]["sides"][1]["entry_id"]]
    assert [side["entry_id"] for side in final["sides"]] == winners
    now = _get(client, league_id, monster["id"], "", headers)
    assert {e["id"]: e["player_ids"] for e in _knockout_entries(now)} == players


@pytest.mark.parametrize(("mode", "qualifiers"), MODES)
def test_monster_knockout_reads_without_errors(
    client: TestClient,
    league: League,
    league_id: UUID,
    headers: dict[str, str],
    monster: Json,
    mode: str,
    qualifiers: int,
) -> None:
    _start_monster(
        client, league_id, headers, monster, mode=mode, qualifiers=qualifiers
    )

    public = f"/api/v1/public/{league.share_token}/tournaments/{monster['id']}"
    reads = [
        client.get(_t_url(league_id, monster["id"]), headers=headers),
        client.get(_t_url(league_id, monster["id"], "/play"), headers=headers),
        client.get(_t_url(league_id, monster["id"], "/bracket"), headers=headers),
        client.get(public),
        client.get(f"{public}/bracket"),
    ]

    assert [r.status_code for r in reads] == [200] * len(reads), [r.text for r in reads]
