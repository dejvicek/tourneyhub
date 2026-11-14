"""The participants of a running tournament and disabling an entry (FR-044,
BR-064, BR-080, BR-147, ADR-008).
"""

import re
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid7

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event, select, update
from sqlalchemy.orm import Session

from tourneyhub.db.models.entries import Entry
from tourneyhub.db.models.leagues import League, Player
from tourneyhub.db.models.matches import Round, RoundParticipation
from tourneyhub.db.models.tournaments import Tournament, TournamentPhase
from tourneyhub.engine.ids import PlayerId
from tourneyhub.engine.tournaments import MonsterKnockoutMode, Participation
from tourneyhub.services.tournaments.remix import left_player_ids, remix_knockout
from tourneyhub.services.tournaments.shared import _load_tournament

type Json = dict[str, Any]

MODE = MonsterKnockoutMode.LORD_HAVE_MERCY.value

FORMAT: Json = {
    "name": "Thursday",
    "date": "2026-11-12",
    "type": "singles",
    "group_phase": "swiss",
    "round_robin_legs": None,
    "sit_out_points": None,
    "group_match_format": "bo1",
    "knockout_match_format": None,
    "final_match_format": None,
    "third_place_match": None,
    "goals_per_game": 10,
    "field_count": 2,
}
MONSTER: Json = {
    "type": "monster_dyp",
    "group_phase": "monster_dyp",
    "sit_out_points": 1,
}
ROUND_ROBIN: Json = {"group_phase": "round_robin", "round_robin_legs": 1}


def _win(side: str = "side_1") -> Json:
    scores = (10, 5) if side == "side_1" else (5, 10)
    return {
        "walkover_winner": None,
        "games": [{"winner": side, "score_1": scores[0], "score_2": scores[1]}],
    }


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
def get(
    client: TestClient, league_id: UUID, headers: dict[str, str]
) -> Callable[[str, str], Json]:
    def get(tournament_id: str, rest: str = "") -> Json:
        response = client.get(
            f"/api/v1/leagues/{league_id}/tournaments/{tournament_id}{rest}",
            headers=headers,
        )
        assert response.status_code == 200, response.text
        result: Json = response.json()
        return result

    return get


@pytest.fixture
def post(
    client: TestClient, league_id: UUID, headers: dict[str, str]
) -> Callable[[str, str, Json], Json]:
    def post(tournament_id: str, rest: str, body: Json) -> Json:
        response = client.post(
            f"/api/v1/leagues/{league_id}/tournaments/{tournament_id}{rest}",
            json=body,
            headers=headers,
        )
        assert response.status_code in {200, 201}, response.text
        result: Json = response.json()
        return result

    return post


@pytest.fixture
def create(
    client: TestClient, league_id: UUID, headers: dict[str, str], players: list[str]
) -> Callable[..., str]:
    def create(count: int = 6, **values: object) -> str:
        """A tournament in setup with the first `count` players picked."""
        created = client.post(
            f"/api/v1/leagues/{league_id}/tournaments",
            json={"id": str(uuid7()), **FORMAT, **values},
            headers=headers,
        )
        assert created.status_code == 201, created.text
        tournament_id: str = created.json()["tournament_id"]
        picked = client.put(
            f"/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/players",
            json={"player_ids": players[:count]},
            headers=headers,
        )
        assert picked.status_code == 200, picked.text
        return tournament_id

    return create


@pytest.fixture
def start(
    get: Callable[[str, str], Json], post: Callable[[str, str, Json], Json]
) -> Callable[[str], Json]:
    def start(tournament_id: str) -> Json:
        """Start the tournament as the review screen does (FR-035)."""
        preview = get(tournament_id, "/setup/preview")
        return post(
            tournament_id,
            "/start",
            {
                "expected_draw_counter": preview["draw_counter"],
                "expected_seed_order": preview["seed_order"],
            },
        )

    return start


@pytest.fixture
def play_round(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    get: Callable[[str, str], Json],
) -> Callable[[str, int], None]:
    def play_round(tournament_id: str, round_no: int) -> None:
        """Side 1 wins every match of the group round."""
        tournament = get(tournament_id, "")
        group = next(p for p in tournament["phases"] if p["kind"] == "group")
        [round_] = [
            r
            for r in tournament["rounds"]
            if r["phase_id"] == group["id"] and r["round_no"] == round_no
        ]
        for match in round_["matches"]:
            response = client.put(
                f"/api/v1/leagues/{league_id}/tournaments/{tournament_id}"
                f"/matches/{match['id']}/result",
                json=_win(),
                headers=headers,
            )
            assert response.status_code == 200, response.text

    return play_round


@pytest.fixture
def add_round(post: Callable[[str, str, Json], Json]) -> Callable[[str, int], Json]:
    def add_round(tournament_id: str, expected_round_no: int) -> Json:
        return post(tournament_id, "/rounds", {"expected_round_no": expected_round_no})

    return add_round


@pytest.fixture
def disable(
    client: TestClient, league_id: UUID, headers: dict[str, str]
) -> Callable[..., tuple[int, Json]]:
    def disable(
        tournament_id: str, entry_id: str, *, disabled: bool = True
    ) -> tuple[int, Json]:
        response = client.put(
            f"/api/v1/leagues/{league_id}/tournaments/{tournament_id}"
            f"/entries/{entry_id}/disabled",
            json={"disabled": disabled},
            headers=headers,
        )
        result: Json = response.json()
        return response.status_code, result

    return disable


@pytest.fixture
def participants(
    client: TestClient, league_id: UUID, headers: dict[str, str]
) -> Callable[[str], list[Json]]:
    def participants(tournament_id: str) -> list[Json]:
        response = client.get(
            f"/api/v1/leagues/{league_id}/tournaments/{tournament_id}/participants",
            headers=headers,
        )
        assert response.status_code == 200, response.text
        shown: list[Json] = response.json()
        return shown

    return participants


def _by_entry(rows: list[Json]) -> dict[str, Json]:
    return {row["entry_id"]: row for row in rows}


def _entry_ids(tournament: Json) -> list[str]:
    main = [e for e in tournament["entries"] if e["stage"] == "main"]
    return [e["id"] for e in sorted(main, key=lambda e: e["seed"])]


# ------------------------------------------------------------ disabling


def test_fr044_br064_disable_and_enable_in_a_swiss_and_the_next_round_leaves_it_out(
    create: Callable[..., str],
    start: Callable[[str], Json],
    play_round: Callable[[str, int], None],
    add_round: Callable[[str, int], Json],
    disable: Callable[..., tuple[int, Json]],
    get: Callable[[str, str], Json],
    session: Session,
) -> None:
    tournament_id = create(6)
    entry_id = _entry_ids(start(tournament_id))[0]
    play_round(tournament_id, 1)

    status, body = disable(tournament_id, entry_id)

    assert status == 200
    assert body == {
        "entry_id": entry_id,
        "state": "disabled",
        "joined_round": None,
        "disabled_since_round": 2,
        "sat_out_round": None,
    }
    round_2 = add_round(tournament_id, 2)
    in_play = {s["entry_id"] for m in round_2["matches"] for s in m["sides"]}
    assert entry_id not in in_play
    status_of = session.scalars(
        select(RoundParticipation.status).where(
            RoundParticipation.round_id == UUID(round_2["id"]),
            RoundParticipation.entry_id == UUID(entry_id),
        )
    ).one()
    assert status_of is Participation.DISABLED

    status, body = disable(tournament_id, entry_id, disabled=False)

    assert (status, body["state"], body["disabled_since_round"]) == (
        200,
        "playing",
        None,
    )
    play_round(tournament_id, 2)
    add_round(tournament_id, 3)
    round_3 = next(r for r in get(tournament_id, "")["rounds"] if r["round_no"] == 3)
    assert entry_id in {s["entry_id"] for m in round_3["matches"] for s in m["sides"]}


def test_fr044_br064_a_monster_dyp_entry_can_be_disabled(
    create: Callable[..., str],
    start: Callable[[str], Json],
    disable: Callable[..., tuple[int, Json]],
    participants: Callable[[str], list[Json]],
) -> None:
    tournament_id = create(8, **MONSTER)
    start(tournament_id)
    entry_id = participants(tournament_id)[0]["entry_id"]

    status, body = disable(tournament_id, entry_id)

    assert (status, body["state"]) == (200, "disabled")
    assert _by_entry(participants(tournament_id))[entry_id]["state"] == "disabled"


def test_fr044_a_swiss_whose_knockout_is_only_previewed_is_still_in_its_group_phase(
    create: Callable[..., str],
    start: Callable[[str], Json],
    get: Callable[[str, str], Json],
    disable: Callable[..., tuple[int, Json]],
) -> None:
    tournament_id = create(6)
    entry_id = _entry_ids(start(tournament_id))[0]
    get(tournament_id, "/knockout/preview?qualifiers=4&third_place_match=false")

    status, body = disable(tournament_id, entry_id)

    assert (status, body["state"]) == (200, "disabled")


def test_br147_a_disabled_player_has_left_a_lord_have_mercy_knockout(
    client: TestClient,
    session: Session,
    league: League,
    league_id: UUID,
    headers: dict[str, str],
    create: Callable[..., str],
    start: Callable[[str], Json],
    play_round: Callable[[str, int], None],
    get: Callable[[str, str], Json],
    disable: Callable[..., tuple[int, Json]],
) -> None:
    tournament_id = create(8, **MONSTER)
    start(tournament_id)
    play_round(tournament_id, 1)
    tournament = get(tournament_id, "")
    query = f"?qualifiers=8&third_place_match=false&mode={MODE}"
    shown = get(tournament_id, f"/knockout/preview{query}")
    started = client.put(
        f"/api/v1/leagues/{league_id}/tournaments/{tournament_id}/knockout",
        json={
            "expected_current_phase_id": tournament["current_phase_id"],
            "expected_qualifier_ids": [
                m["entry_id"] for e in shown["entries"] for m in e["members"]
            ],
            "expected_draw_counter": shown["draw_counter"],
            "qualifiers": 8,
            "third_place_match": False,
            "match_format": "bo1",
            "final_match_format": None,
            "mode": MODE,
        },
        headers=headers,
    )
    assert started.status_code == 200, started.text
    entry_id = next(e["id"] for e in tournament["entries"] if e["stage"] == "main")

    status, body = disable(tournament_id, entry_id)

    assert (status, body["state"]) == (200, "disabled")
    loaded = _load_tournament(session, league=league, tournament_id=UUID(tournament_id))
    remix = remix_knockout(loaded)
    assert remix is not None
    entry = next(e for e in loaded.entries if str(e.id) == entry_id)
    players_of_entry = {PlayerId(m.player_id) for m in entry.members}
    assert players_of_entry
    assert players_of_entry <= left_player_ids(loaded, remix)


def test_fr044_a_round_robin_has_no_disabling(
    create: Callable[..., str],
    start: Callable[[str], Json],
    disable: Callable[..., tuple[int, Json]],
) -> None:
    tournament_id = create(4, **ROUND_ROBIN)
    entry_id = _entry_ids(start(tournament_id))[0]

    status, body = disable(tournament_id, entry_id)

    assert (status, body["code"]) == (422, "disable_not_allowed")


def test_br080_fr044_a_started_knockout_that_is_not_lord_have_mercy_refuses(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    create: Callable[..., str],
    start: Callable[[str], Json],
    play_round: Callable[[str, int], None],
    add_round: Callable[[str, int], Json],
    get: Callable[[str, str], Json],
    disable: Callable[..., tuple[int, Json]],
) -> None:
    tournament_id = create(4)
    entry_id = _entry_ids(start(tournament_id))[0]
    play_round(tournament_id, 1)
    add_round(tournament_id, 2)
    play_round(tournament_id, 2)
    tournament = get(tournament_id, "")
    shown = get(tournament_id, "/knockout/preview?qualifiers=4&third_place_match=false")
    started = client.put(
        f"/api/v1/leagues/{league_id}/tournaments/{tournament_id}/knockout",
        json={
            "expected_current_phase_id": tournament["current_phase_id"],
            "expected_draw_counter": shown["draw_counter"],
            "expected_qualifier_ids": [
                e["members"][0]["entry_id"] for e in shown["entries"]
            ],
            "qualifiers": 4,
            "third_place_match": False,
            "match_format": None,
            "final_match_format": None,
            "mode": None,
        },
        headers=headers,
    )
    assert started.status_code == 200, started.text

    status, body = disable(tournament_id, entry_id)

    assert (status, body["code"]) == (422, "disable_not_allowed")


def test_fr044_adr008_disabling_locks_the_league_before_the_tournament(
    engine: Engine,
    create: Callable[..., str],
    start: Callable[[str], Json],
    disable: Callable[..., tuple[int, Json]],
) -> None:
    tournament_id = create(6)
    entry_id = _entry_ids(start(tournament_id))[0]
    seen: list[str] = []

    def record(*args: object) -> None:  # the statement is the third argument
        statement = args[2]
        assert isinstance(statement, str)
        seen.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        status, _ = disable(tournament_id, entry_id)
    finally:
        event.remove(engine, "before_cursor_execute", record)

    locked = [
        m.group(1)
        for s in seen
        if re.search(r"\bFOR UPDATE\b", s, re.IGNORECASE)
        and (m := re.search(r"\bFROM\s+(\w+)", s, re.IGNORECASE))
    ]
    assert status == 200
    assert locked[:2] == ["leagues", "tournaments"]


def test_br080_fr044_a_disabled_entry_does_not_qualify_for_the_knockout(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    create: Callable[..., str],
    start: Callable[[str], Json],
    play_round: Callable[[str, int], None],
    get: Callable[[str, str], Json],
    disable: Callable[..., tuple[int, Json]],
) -> None:
    tournament_id = create(6)
    start(tournament_id)
    play_round(tournament_id, 1)
    url = "/knockout/preview?qualifiers=2&third_place_match=false"
    before = [e["members"][0]["entry_id"] for e in get(tournament_id, url)["entries"]]
    status, _ = disable(tournament_id, before[0])
    assert status == 200
    shown = get(tournament_id, url)
    qualifiers = [e["members"][0]["entry_id"] for e in shown["entries"]]
    tournament = get(tournament_id, "")

    started = client.put(
        f"/api/v1/leagues/{league_id}/tournaments/{tournament_id}/knockout",
        json={
            "expected_current_phase_id": tournament["current_phase_id"],
            "expected_draw_counter": shown["draw_counter"],
            "expected_qualifier_ids": qualifiers,
            "qualifiers": 2,
            "third_place_match": False,
            "match_format": None,
            "final_match_format": None,
            "mode": None,
        },
        headers=headers,
    )

    assert started.status_code == 200, started.text
    assert before[0] not in qualifiers
    assert len(qualifiers) == 2
    assert qualifiers[0] == before[1]
    knockout = [
        e for e in get(tournament_id, "")["entries"] if e["stage"] == "knockout"
    ]
    assert len(knockout) == 2


def test_fr044_a_tournament_in_setup_is_409(
    create: Callable[..., str],
    get: Callable[[str, str], Json],
    disable: Callable[..., tuple[int, Json]],
) -> None:
    tournament_id = create(4)
    entry_id = get(tournament_id, "/setup/preview")["seed_order"][0]

    status, body = disable(tournament_id, entry_id)

    assert (status, body["code"]) == (409, "tournament_not_in_progress")


def test_fr044_a_finished_tournament_is_409(
    create: Callable[..., str],
    start: Callable[[str], Json],
    play_round: Callable[[str, int], None],
    post: Callable[[str, str, Json], Json],
    disable: Callable[..., tuple[int, Json]],
) -> None:
    tournament_id = create(4)
    entry_id = _entry_ids(start(tournament_id))[0]
    play_round(tournament_id, 1)
    post(tournament_id, "/finish", {"expected_state": "in_progress"})

    status, body = disable(tournament_id, entry_id)

    assert (status, body["code"]) == (409, "tournament_not_in_progress")


def test_fr044_an_unknown_entry_and_one_of_another_tournament_are_404(
    create: Callable[..., str],
    start: Callable[[str], Json],
    disable: Callable[..., tuple[int, Json]],
) -> None:
    first = create(4)
    second = create(4)
    start(first)
    other_entry = _entry_ids(start(second))[0]

    unknown = disable(first, str(uuid7()))
    foreign = disable(first, other_entry)

    assert unknown[0] == foreign[0] == 404
    assert unknown[1]["code"] == foreign[1]["code"] == "entry_not_found"


def test_fr044_another_organizers_tournament_is_404(
    client: TestClient,
    league_id: UUID,
    make_league: Callable[..., League],
    auth_header: Callable[..., dict[str, str]],
    create: Callable[..., str],
    start: Callable[[str], Json],
) -> None:
    tournament_id = create(4)
    entry_id = _entry_ids(start(tournament_id))[0]
    other = auth_header(make_league().owner_user_id)
    base = f"/api/v1/leagues/{league_id}/tournaments/{tournament_id}"

    listed = client.get(f"{base}/participants", headers=other)
    changed = client.put(
        f"{base}/entries/{entry_id}/disabled", json={"disabled": True}, headers=other
    )

    assert (listed.status_code, listed.json()["code"]) == (404, "league_not_found")
    assert (changed.status_code, changed.json()["code"]) == (404, "league_not_found")


def test_fr044_adr008_a_repeat_changes_nothing_not_even_updated_at(
    create: Callable[..., str],
    start: Callable[[str], Json],
    disable: Callable[..., tuple[int, Json]],
    travel: Callable[[timedelta], datetime],
    session: Session,
    now: datetime,
) -> None:
    tournament_id = create(6)
    entry_id = _entry_ids(start(tournament_id))[0]
    first = travel(timedelta(minutes=1))
    disable(tournament_id, entry_id)
    travel(timedelta(minutes=2))

    status, body = disable(tournament_id, entry_id)

    assert (status, body["state"]) == (200, "disabled")
    assert session.get_one(Tournament, UUID(tournament_id)).updated_at == first
    assert first > now


def test_fr044_a_change_moves_the_tournament_updated_at(
    create: Callable[..., str],
    start: Callable[[str], Json],
    disable: Callable[..., tuple[int, Json]],
    travel: Callable[[timedelta], datetime],
    session: Session,
) -> None:
    tournament_id = create(6)
    entry_id = _entry_ids(start(tournament_id))[0]
    later = travel(timedelta(minutes=5))

    disable(tournament_id, entry_id)

    assert session.get_one(Tournament, UUID(tournament_id)).updated_at == later


# --------------------------------------------------------- participants


def test_fr044_before_a_swiss_round_everyone_is_playing_in_seed_order(
    create: Callable[..., str],
    start: Callable[[str], Json],
    participants: Callable[[str], list[Json]],
) -> None:
    tournament_id = create(4)
    order = _entry_ids(start(tournament_id))

    shown = participants(tournament_id)

    assert [p["entry_id"] for p in shown] == order
    assert all(
        (p["state"], p["joined_round"], p["disabled_since_round"], p["sat_out_round"])
        == ("playing", None, None, None)
        for p in shown
    )


def test_br058_the_entry_that_sat_out_the_latest_round_is_marked(
    create: Callable[..., str],
    start: Callable[[str], Json],
    participants: Callable[[str], list[Json]],
) -> None:
    tournament_id = create(5)
    sitting = start(tournament_id)["rounds"][0]["sitting_out"]

    shown = participants(tournament_id)

    assert [p["entry_id"] for p in shown if p["state"] == "sat_out"] == sitting
    assert [p["sat_out_round"] for p in shown if p["state"] == "sat_out"] == [1]


def test_br064_disabled_since_round_follows_the_last_round_the_entry_was_in(
    create: Callable[..., str],
    start: Callable[[str], Json],
    play_round: Callable[[str, int], None],
    add_round: Callable[[str, int], Json],
    disable: Callable[..., tuple[int, Json]],
    participants: Callable[[str], list[Json]],
) -> None:
    tournament_id = create(6)
    entry_id = _entry_ids(start(tournament_id))[0]
    play_round(tournament_id, 1)
    add_round(tournament_id, 2)
    play_round(tournament_id, 2)
    add_round(tournament_id, 3)

    disable(tournament_id, entry_id)
    before_draw = _by_entry(participants(tournament_id))[entry_id]
    play_round(tournament_id, 3)
    add_round(tournament_id, 4)
    after_draw = _by_entry(participants(tournament_id))[entry_id]

    assert before_draw["disabled_since_round"] == 4
    assert after_draw["disabled_since_round"] == 4


def test_br064_an_entry_disabled_before_it_ever_played_is_disabled_since_round_1(
    create: Callable[..., str],
    start: Callable[[str], Json],
    session: Session,
    participants: Callable[[str], list[Json]],
) -> None:
    tournament_id = create(5)
    [entry_id] = start(tournament_id)["rounds"][0]["sitting_out"]
    session.get_one(Entry, UUID(entry_id)).is_disabled = True
    session.execute(
        update(RoundParticipation)
        .where(RoundParticipation.entry_id == UUID(entry_id))
        .values(status=Participation.DISABLED)
    )
    session.expire_all()

    shown = _by_entry(participants(tournament_id))[entry_id]

    assert (shown["state"], shown["disabled_since_round"]) == ("disabled", 1)


def test_fr044_joined_round_comes_from_the_not_joined_rows(
    create: Callable[..., str],
    start: Callable[[str], Json],
    play_round: Callable[[str, int], None],
    add_round: Callable[[str, int], Json],
    session: Session,
    participants: Callable[[str], list[Json]],
) -> None:
    tournament_id = create(5)
    [late] = start(tournament_id)["rounds"][0]["sitting_out"]
    session.execute(
        update(RoundParticipation)
        .where(RoundParticipation.entry_id == UUID(late))
        .values(status=Participation.NOT_JOINED)
    )
    session.expire_all()

    before = participants(tournament_id)
    play_round(tournament_id, 1)
    add_round(tournament_id, 2)
    after = participants(tournament_id)

    # Joined no round yet: the round after the latest one. Then it joined round 2.
    assert _by_entry(before)[late]["joined_round"] == 2
    assert _by_entry(after)[late]["joined_round"] == 2
    assert all(p["joined_round"] is None for p in before if p["entry_id"] != late)


def _round_id(session: Session, tournament_id: str, round_no: int) -> UUID:
    return session.scalars(
        select(Round.id)
        .join(TournamentPhase, Round.phase_id == TournamentPhase.id)
        .where(
            TournamentPhase.tournament_id == UUID(tournament_id),
            Round.round_no == round_no,
        )
    ).one()
