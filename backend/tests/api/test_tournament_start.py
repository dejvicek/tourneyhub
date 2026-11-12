import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid7

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session

from tourneyhub.app import create_app
from tourneyhub.db.models.accounts import User
from tourneyhub.db.models.entries import Entry
from tourneyhub.db.models.leagues import League, Player
from tourneyhub.db.models.matches import Match, MatchGame, Round
from tourneyhub.db.models.tournaments import Field, Tournament, TournamentPhase
from tourneyhub.engine.accounts import Language
from tourneyhub.engine.tournaments import (
    DEFAULT_TIEBREAKERS,
    GroupPhase,
    Outcome,
    PhaseFormat,
    SeedingMethod,
    TournamentType,
)
from tourneyhub.services import leagues as league_service
from tourneyhub.services import players as player_service
from tourneyhub.services import tournaments as tournament_service
from tourneyhub.settings import Settings

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


def _url(league: League | UUID, rest: str = "") -> str:
    league_id = league.id if isinstance(league, League) else league
    return f"/api/v1/leagues/{league_id}{rest}"


def _t_url(league: League | UUID, tournament_id: str, rest: str = "") -> str:
    return _url(league, f"/tournaments/{tournament_id}{rest}")


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


def _setup(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    player_ids: list[str],
    **values: object,
) -> Json:
    """A tournament in setup with these players picked; returns its setup."""
    body = {"id": str(uuid7()), **ROUND_ROBIN, **values}
    created = client.post(_url(league, "/tournaments"), json=body, headers=headers)
    assert created.status_code == 201, created.text
    picked = client.put(
        _t_url(league, created.json()["tournament_id"], "/setup/players"),
        json={"player_ids": player_ids},
        headers=headers,
    )
    assert picked.status_code == 200, picked.text
    setup: Json = picked.json()
    return setup


def _start(
    client: TestClient,
    league: League | UUID,
    setup: Json,
    headers: dict[str, str],
    *,
    counter: int | None = None,
) -> tuple[int, Json]:
    response = client.post(
        _t_url(league, setup["tournament_id"], "/start"),
        json={
            "expected_draw_counter": setup["draw_counter"]
            if counter is None
            else counter
        },
        headers=headers,
    )
    result: Json = response.json()
    return response.status_code, result


def _started(
    client: TestClient, league: League, setup: Json, headers: dict[str, str]
) -> Json:
    status, body = _start(client, league, setup, headers)
    assert status == 200, body
    return body


def _back(
    client: TestClient, league: League, tournament_id: str, headers: dict[str, str]
) -> tuple[int, Json]:
    response = client.post(
        _t_url(league, tournament_id, "/back-to-setup"),
        json={"expected_state": "in_progress"},
        headers=headers,
    )
    result: Json = response.json()
    return response.status_code, result


def _sides(match: Json) -> tuple[str | None, str | None]:
    return match["sides"][0]["entry_id"], match["sides"][1]["entry_id"]


def _record_result(session: Session, match_id: str, now: datetime) -> None:
    """A BO1 result written directly, until results have their route (P8)."""
    match = session.get_one(Match, UUID(match_id))
    match.outcome = Outcome.SIDE_1
    match.result_entered_at = now
    session.add(
        MatchGame(match_id=match.id, game_no=1, winner=Outcome.SIDE_1, created_at=now)
    )
    for field in session.scalars(select(Field).where(Field.match_id == match.id)):
        field.match_id = None
    session.flush()


# ---------------------------------------------------------------- start


def test_fr035_start_generates_the_round_robin_by_seed(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    setup = _setup(client, league, headers, players[:5])
    seeds = [entry["id"] for entry in setup["entries"]]

    body = _started(client, league, setup, headers)

    assert body["state"] == "in_progress"
    assert body["current_phase_id"] == body["phases"][0]["id"]
    assert body["current_phase_done"] is False
    assert [r["round_no"] for r in body["rounds"]] == [1, 2, 3, 4, 5]
    first = body["rounds"][0]
    assert [_sides(m) for m in first["matches"]] == [
        (seeds[1], seeds[4]),
        (seeds[2], seeds[3]),
    ]
    assert first["sitting_out"] == [seeds[0]]
    assert [m["position"] for m in first["matches"]] == [1, 2]
    assert all(r["phase_id"] == body["phases"][0]["id"] for r in body["rounds"])
    assert [e["id"] for e in body["entries"]] == seeds


def test_br050_every_entry_meets_every_other_once(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    setup = _setup(client, league, headers, players[:6])

    body = _started(client, league, setup, headers)

    pairs = [frozenset(_sides(m)) for r in body["rounds"] for m in r["matches"]]
    assert len(pairs) == len(set(pairs)) == 15
    assert all(r["sitting_out"] == [] for r in body["rounds"])


def test_br052_twice_repeats_the_rounds_with_the_sides_swapped(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    setup = _setup(client, league, headers, players[:3], round_robin_legs=2)

    body = _started(client, league, setup, headers)

    rounds = body["rounds"]
    assert len(rounds) == 6
    for first, second in zip(rounds[:3], rounds[3:], strict=True):
        assert [_sides(m)[::-1] for m in first["matches"]] == [
            _sides(m) for m in second["matches"]
        ]
        assert first["sitting_out"] == second["sitting_out"]


def test_d2_match_sides_list_the_players_of_their_entry(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    setup = _setup(
        client, league, headers, players[:5], type="dyp", group_phase="round_robin"
    )

    body = _started(client, league, setup, headers)

    members = {e["id"]: e["player_ids"] for e in body["entries"]}
    (match,) = body["rounds"][0]["matches"]
    assert [s["player_ids"] for s in match["sides"]] == [
        members[s["entry_id"]] for s in match["sides"]
    ]
    assert not any(s["is_bye"] for s in match["sides"])
    playing = {p for s in match["sides"] for p in s["player_ids"]}
    assert len(playing) == 4  # BR-031: the left-out player plays no match


def test_br130_the_first_matches_take_the_fields_and_the_rest_wait(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    setup = _setup(client, league, headers, players[:4], field_count=3)

    body = _started(client, league, setup, headers)

    round_1, round_2, round_3 = (
        [m["id"] for m in r["matches"]] for r in body["rounds"]
    )
    # BR-131: field 3 stays free, since every round-2 match has a player on a field.
    assert [f["match_id"] for f in body["fields"]] == [*round_1, None]
    assert body["waiting"] == [*round_2, *round_3]


def test_adr008_a_repeated_start_is_a_conflict(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    setup = _setup(client, league, headers, players[:4])
    _started(client, league, setup, headers)

    status, body = _start(client, league, setup, headers)

    assert (status, body) == (
        409,
        {"code": "tournament_not_in_setup", "detail": {"state": "in_progress"}},
    )


def test_adr008_a_stale_draw_counter_does_not_start(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    players: list[str],
    session: Session,
) -> None:
    setup = _setup(client, league, headers, players[:4])

    status, body = _start(client, league, setup, headers, counter=0)

    assert (status, body) == (
        409,
        {"code": "draw_counter_changed", "detail": {"draw_counter": 1}},
    )
    tournament = session.get_one(Tournament, UUID(setup["tournament_id"]))
    session.refresh(tournament)
    assert tournament.state == "setup"


@pytest.mark.parametrize(
    ("values", "picked", "code", "detail"),
    [
        pytest.param(
            {}, 1, "not_enough_entries", {"minimum": 2, "given": 1}, id="FR-032"
        ),
        pytest.param(
            {"type": "dyp"},
            3,
            "not_enough_players",
            {"minimum": 4, "given": 3},
            id="BR-031",
        ),
        pytest.param(
            {"group_phase": "swiss", "round_robin_legs": None},
            4,
            "format_not_supported",
            {"format": "swiss"},
            id="swiss-later",
        ),
        pytest.param(
            {
                "group_phase": "none",
                "round_robin_legs": None,
                "sit_out_points": None,
                "group_match_format": None,
                "knockout_match_format": "bo1",
                "third_place_match": False,
            },
            4,
            "format_not_supported",
            {"format": "single_elimination"},
            id="knockout-later",
        ),
        pytest.param(
            {
                "type": "monster_dyp",
                "group_phase": "monster_dyp",
                "round_robin_legs": None,
            },
            4,
            "format_not_supported",
            {"format": "monster_dyp"},
            id="monster-dyp-later",
        ),
    ],
)
def test_fr035_an_incomplete_setup_does_not_start(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    players: list[str],
    values: Json,
    picked: int,
    code: str,
    detail: Json,
) -> None:
    setup = _setup(client, league, headers, players[:picked], **values)

    status, body = _start(client, league, setup, headers)

    assert (status, body) == (422, {"code": code, "detail": detail})


def test_fr033_a_doubles_player_without_a_partner_does_not_start(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    setup = _setup(client, league, headers, players[:5], type="doubles")
    paired = client.put(
        _t_url(league, setup["tournament_id"], "/setup/pairs"),
        json={"pairs": [players[:2], players[2:4]]},
        headers=headers,
    ).json()

    status, body = _start(client, league, paired, headers)

    assert (status, body) == (
        422,
        {"code": "players_without_partner", "detail": {"unpaired": 1}},
    )


def test_fr033_doubles_pairs_play_the_round_robin_as_entries(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    setup = _setup(client, league, headers, players[:6], type="doubles")
    paired = client.put(
        _t_url(league, setup["tournament_id"], "/setup/pairs"),
        json={"pairs": [players[:2], players[2:4], players[4:6]]},
        headers=headers,
    ).json()

    body = _started(client, league, paired, headers)

    assert len(body["rounds"]) == 3
    sides = [s for r in body["rounds"] for m in r["matches"] for s in m["sides"]]
    assert all(len(side["player_ids"]) == 2 for side in sides)


def test_br032_hand_halves_must_be_complete_to_start(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    setup = _setup(client, league, headers, players[:4], type="dyp")
    halves = client.put(
        _t_url(league, setup["tournament_id"], "/setup/halves"),
        json={
            "method": "by_hand",
            "halves": [{"player_id": players[0], "half": "top"}],
        },
        headers=headers,
    ).json()

    status, body = _start(client, league, halves, headers)

    assert (status, body) == (
        422,
        {"code": "dyp_halves_incomplete", "detail": {"missing": 3}},
    )


def test_owasp_api1_a_tournament_of_another_league_does_not_start(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    players: list[str],
    make_league: Callable[..., League],
) -> None:
    other = make_league(owner_user_id=league.owner_user_id)
    setup = _setup(client, league, headers, players[:4])

    status, body = _start(client, other, setup, headers)
    read = client.get(_t_url(other, setup["tournament_id"]), headers=headers)
    back_status, back = _back(client, other, setup["tournament_id"], headers)

    assert status == read.status_code == back_status == 404
    assert body == read.json() == back == {"code": "tournament_not_found", "detail": {}}


# ---------------------------------------------------------------- the read


S1_WINS: Json = {
    "walkover_winner": None,
    "games": [{"winner": "side_1", "score_1": 10, "score_2": 7}],
}


def _as_swiss(session: Session, setup: Json, *, points: int) -> None:
    """Make the started tournament's phase a Swiss one that has these sit-out points.

    The backend does not generate Swiss rounds yet, so a running Swiss phase is made
    from a started round robin: its rounds and matches stay, the phase's settings
    change (BR-071: Swiss and Monster DYP score a sit-out, a round robin does not).
    """
    phase = session.scalars(
        select(TournamentPhase)
        .where(TournamentPhase.tournament_id == UUID(setup["tournament_id"]))
        .execution_options(populate_existing=True)
    ).one()
    phase.format = PhaseFormat.SWISS
    phase.round_robin_legs = None
    phase.tiebreakers = list(DEFAULT_TIEBREAKERS)
    phase.sit_out_points = points
    session.flush()


def _sit_out(
    client: TestClient, league: League, headers: dict[str, str], tournament: Json
) -> int | None:
    read = client.get(_t_url(league, tournament["tournament_id"]), headers=headers)
    [phase] = read.json()["phases"]
    points: int | None = phase["sit_out_points"]
    return points


def _first_result(
    client: TestClient, league: League, headers: dict[str, str], started: Json
) -> None:
    match = next(
        m
        for r in started["rounds"]
        for m in r["matches"]
        if not any(side["is_bye"] for side in m["sides"])
    )
    response = client.put(
        _t_url(league, started["id"], f"/matches/{match['id']}/result"),
        json=S1_WINS,
        headers=headers,
    )
    assert response.status_code == 200, response.text


def test_br075_the_sit_out_points_cannot_change_while_the_phase_has_a_result(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    players: list[str],
    session: Session,
) -> None:
    setup = _setup(client, league, headers, players[:3])
    started = _started(client, league, setup, headers)
    _as_swiss(session, setup, points=2)
    _first_result(client, league, headers, started)

    refused = client.put(
        _t_url(league, setup["tournament_id"], "/format"),
        json={
            **ROUND_ROBIN,
            "group_phase": "swiss",
            "round_robin_legs": None,
            "sit_out_points": 0,
        },
        headers=headers,
    )

    assert refused.status_code == 409
    assert refused.json()["code"] == "tournament_not_in_setup"
    assert _sit_out(client, league, headers, setup) == 2


def test_br071_a_running_round_robin_keeps_no_sit_out_points(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    setup = _setup(client, league, headers, players[:3])
    _started(client, league, setup, headers)

    assert _sit_out(client, league, headers, setup) is None


def test_fr030_a_tournament_in_setup_reads_without_rounds(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    setup = _setup(client, league, headers, players[:3])

    response = client.get(_t_url(league, setup["tournament_id"]), headers=headers)

    body = response.json()
    assert response.status_code == 200
    assert body["state"] == "setup"
    assert body["rounds"] == body["waiting"] == []
    assert [f["match_id"] for f in body["fields"]] == [None, None]
    assert body["current_phase_id"] is None
    assert body["entries"] == setup["entries"]
    assert body["phases"] == [
        {
            "id": body["phases"][0]["id"],
            "position": 1,
            "kind": "group",
            "format": "round_robin",
            "round_robin_legs": 1,
            "sit_out_points": None,
            "tiebreakers": None,
            "qualifiers": None,
            "third_place_match": None,
            "monster_knockout_mode": None,
            "match_format": "bo1",
            "final_match_format": None,
        }
    ]


def test_fr035_the_read_returns_what_the_start_returned(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    setup = _setup(client, league, headers, players[:4])
    started = _started(client, league, setup, headers)

    read = client.get(_t_url(league, setup["tournament_id"]), headers=headers)

    assert read.json() == started


def test_d11_a_result_shows_with_its_games_and_leaves_the_waiting_list(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    players: list[str],
    session: Session,
    now: datetime,
) -> None:
    setup = _setup(client, league, headers, players[:4], field_count=1)
    started = _started(client, league, setup, headers)
    first = started["fields"][0]["match_id"]
    _record_result(session, first, now)

    body = client.get(_t_url(league, setup["tournament_id"]), headers=headers).json()

    played = next(m for r in body["rounds"] for m in r["matches"] if m["id"] == first)
    assert played["outcome"] == "side_1"
    assert played["games"] == [
        {"game_no": 1, "winner": "side_1", "score_1": None, "score_2": None}
    ]
    assert first not in body["waiting"]
    assert body["fields"][0]["match_id"] is None


def test_fr022_the_list_shows_the_progress_of_a_started_tournament(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    players: list[str],
    session: Session,
    now: datetime,
) -> None:
    setup = _setup(client, league, headers, players[:3])
    started = _started(client, league, setup, headers)
    for round_ in started["rounds"][:2]:
        for match in round_["matches"]:
            _record_result(session, match["id"], now)

    listed = client.get(
        _url(league, f"/seasons/{started['season_id']}/tournaments"), headers=headers
    ).json()

    assert listed[0]["current_phase_id"] == started["phases"][0]["id"]
    assert listed[0]["current_phase_done"] is False
    assert listed[0]["progress"] == {
        "round_no": 3,
        "round_count": 3,
        "matches_played": 2,
        "match_count": 3,
        "in_knockout": False,
    }


def test_fr040_the_group_phase_is_done_once_every_match_has_a_result(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    players: list[str],
    session: Session,
    now: datetime,
) -> None:
    setup = _setup(client, league, headers, players[:2])
    started = _started(client, league, setup, headers)
    _record_result(session, started["rounds"][0]["matches"][0]["id"], now)

    body = client.get(_t_url(league, setup["tournament_id"]), headers=headers).json()
    listed = client.get(
        _url(league, f"/seasons/{started['season_id']}/tournaments"), headers=headers
    ).json()

    assert body["current_phase_done"] is listed[0]["current_phase_done"] is True
    assert body["waiting"] == []
    assert listed[0]["progress"]["round_no"] == 1


# ---------------------------------------------------------------- back to setup


def test_fr036_back_to_setup_deletes_the_schedule_and_keeps_the_draws(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    players: list[str],
    session: Session,
) -> None:
    setup = _setup(client, league, headers, players[:5])
    _started(client, league, setup, headers)
    session.execute(
        update(Entry)
        .where(Entry.tournament_id == UUID(setup["tournament_id"]))
        .values(is_disabled=True)
    )

    status, body = _back(client, league, setup["tournament_id"], headers)

    assert status == 200
    assert body["state"] == "setup"
    assert body["rounds"] == body["waiting"] == []
    assert [f["match_id"] for f in body["fields"]] == [None, None]
    assert body["entries"] == setup["entries"]  # seeds kept, disabled cleared
    again = client.get(
        _t_url(league, setup["tournament_id"], "/setup"), headers=headers
    ).json()
    assert again["draw_counter"] == setup["draw_counter"]
    assert session.scalar(select(func.count()).select_from(Round)) == 0
    assert session.scalar(select(func.count()).select_from(Match)) == 0


def test_fr036_after_back_to_setup_the_tournament_starts_again(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    setup = _setup(client, league, headers, players[:4], field_count=3)
    first = _started(client, league, setup, headers)
    _back(client, league, setup["tournament_id"], headers)

    second = _started(client, league, setup, headers)

    assert [[_sides(m) for m in r["matches"]] for r in second["rounds"]] == [
        [_sides(m) for m in r["matches"]] for r in first["rounds"]
    ]
    assert {r["id"] for r in second["rounds"]}.isdisjoint(
        r["id"] for r in first["rounds"]
    )


def test_adr008_back_to_setup_twice_is_a_conflict(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    setup = _setup(client, league, headers, players[:4])
    _started(client, league, setup, headers)
    _back(client, league, setup["tournament_id"], headers)

    status, body = _back(client, league, setup["tournament_id"], headers)

    assert (status, body) == (
        409,
        {"code": "tournament_not_in_progress", "detail": {"state": "setup"}},
    )


def test_fr036_back_to_setup_ends_with_the_first_result(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    players: list[str],
    session: Session,
    now: datetime,
) -> None:
    setup = _setup(client, league, headers, players[:4])
    started = _started(client, league, setup, headers)
    _record_result(session, started["rounds"][1]["matches"][0]["id"], now)

    status, body = _back(client, league, setup["tournament_id"], headers)

    assert (status, body) == (
        422,
        {"code": "tournament_has_results", "detail": {"results": 1}},
    )


def test_fr036_back_to_setup_expects_a_tournament_in_progress(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    setup = _setup(client, league, headers, players[:4])

    response = client.post(
        _t_url(league, setup["tournament_id"], "/back-to-setup"),
        json={"expected_state": "setup"},
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_failed"


def test_fr038_a_started_tournament_is_deleted_with_its_schedule(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    players: list[str],
    session: Session,
) -> None:
    setup = _setup(client, league, headers, players[:4])
    _started(client, league, setup, headers)

    response = client.delete(_t_url(league, setup["tournament_id"]), headers=headers)

    assert response.status_code == 204
    assert session.scalar(select(func.count()).select_from(Match)) == 0
    assert session.scalar(select(func.count()).select_from(Player)) == 9


# ---------------------------------------------------------------- races


def _commit_setup(engine: Engine, now: datetime) -> tuple[UUID, UUID, UUID, int]:
    """A committed league with a Singles round robin of four picked players."""
    with Session(engine) as setup:
        owner = User(
            email="start@example.test",
            display_name="Racer",
            password_hash="!",
            language=Language.EN,
            created_at=now,
        )
        setup.add(owner)
        setup.flush()
        league = league_service.create_league(
            setup, league_id=uuid7(), owner_user_id=owner.id, name="Race", now=now
        )
        player_ids = [
            player_service.add_player(
                setup,
                league_id=league.id,
                user_id=owner.id,
                name=f"P{n}",
                clock=lambda: now,
            ).id
            for n in range(4)
        ]
        tournament_id = uuid7()
        tournament_service.create_tournament(
            setup,
            league_id=league.id,
            user_id=owner.id,
            tournament_id=tournament_id,
            request=tournament_service.FormatRequest(
                name="Race",
                date=now.date(),
                type=TournamentType.SINGLES,
                group_phase=GroupPhase.ROUND_ROBIN,
            ),
            clock=lambda: now,
        )
        tournament_service.set_tournament_players(
            setup,
            league_id=league.id,
            tournament_id=tournament_id,
            user_id=owner.id,
            player_ids=player_ids,
            clock=lambda: now,
        )
        counter = tournament_service.set_seeding_method(  # a draw has seeds to shuffle
            setup,
            league_id=league.id,
            tournament_id=tournament_id,
            user_id=owner.id,
            method=SeedingMethod.RANDOM,
            clock=lambda: now,
        ).draw_counter
        setup.commit()
        return owner.id, league.id, tournament_id, counter


@pytest.mark.concurrency
def test_adr008_of_two_starts_with_one_counter_exactly_one_starts(
    committing_settings: Settings,
    committing_engine: Engine,
    now: datetime,
    committed_auth_header: Callable[..., dict[str, str]],
    wait_for_a_lock_wait: Callable[[], None],
) -> None:
    owner_id, league_id, tournament_id, counter = _commit_setup(committing_engine, now)
    outcome: list[tuple[int, object]] = []

    with (
        Session(committing_engine) as first,
        TestClient(create_app(committing_settings)) as client,
    ):
        tournament_service.start_tournament(
            first,
            league_id=league_id,
            tournament_id=tournament_id,
            user_id=owner_id,
            expected_draw_counter=counter,
            clock=lambda: now,
        )

        def start_second() -> None:
            response = client.post(
                _t_url(league_id, str(tournament_id), "/start"),
                json={"expected_draw_counter": counter},
                headers=committed_auth_header(owner_id, issued_at=datetime.now(UTC)),
            )
            outcome.append((response.status_code, response.json()))

        second = threading.Thread(target=start_second)
        second.start()
        wait_for_a_lock_wait()  # it waits for the league lock the first one holds
        first.commit()
        second.join()

    assert outcome == [
        (409, {"code": "tournament_not_in_setup", "detail": {"state": "in_progress"}})
    ]
    with Session(committing_engine) as check:
        assert check.scalar(select(func.count()).select_from(Round)) == 3


@pytest.mark.concurrency
def test_fr036_back_to_setup_racing_a_start_waits_and_deletes_its_schedule(
    committing_settings: Settings,
    committing_engine: Engine,
    now: datetime,
    committed_auth_header: Callable[..., dict[str, str]],
    wait_for_a_lock_wait: Callable[[], None],
) -> None:
    owner_id, league_id, tournament_id, counter = _commit_setup(committing_engine, now)
    outcome: list[tuple[int, object]] = []

    with (
        Session(committing_engine) as first,
        TestClient(create_app(committing_settings)) as client,
    ):
        tournament_service.start_tournament(
            first,
            league_id=league_id,
            tournament_id=tournament_id,
            user_id=owner_id,
            expected_draw_counter=counter,
            clock=lambda: now,
        )

        def back() -> None:
            response = client.post(
                _t_url(league_id, str(tournament_id), "/back-to-setup"),
                json={"expected_state": "in_progress"},
                headers=committed_auth_header(owner_id, issued_at=datetime.now(UTC)),
            )
            outcome.append((response.status_code, response.json()["state"]))

        second = threading.Thread(target=back)
        second.start()
        wait_for_a_lock_wait()
        first.commit()
        second.join()

    assert outcome == [(200, "setup")]
    with Session(committing_engine) as check:
        assert check.scalar(select(func.count()).select_from(Match)) == 0
        assert check.scalars(select(Field.match_id)).all() == [None]


@pytest.mark.concurrency
@pytest.mark.parametrize("winner", ["start", "draw"])
def test_adr008_a_start_racing_a_setup_write_has_exactly_one_winner(
    committing_settings: Settings,
    committing_engine: Engine,
    now: datetime,
    committed_auth_header: Callable[..., dict[str, str]],
    wait_for_a_lock_wait: Callable[[], None],
    winner: str,
) -> None:
    owner_id, league_id, tournament_id, counter = _commit_setup(committing_engine, now)
    outcome: list[tuple[int, object]] = []

    with (
        Session(committing_engine) as first,
        TestClient(create_app(committing_settings)) as client,
    ):
        if winner == "start":
            tournament_service.start_tournament(
                first,
                league_id=league_id,
                tournament_id=tournament_id,
                user_id=owner_id,
                expected_draw_counter=counter,
                clock=lambda: now,
            )
            path, body = "/setup/draw", {"target": "seeds"}
        else:
            tournament_service.draw_again(
                first,
                league_id=league_id,
                tournament_id=tournament_id,
                user_id=owner_id,
                target=tournament_service.DrawTarget.SEEDS,
                expected_draw_counter=counter,
                clock=lambda: now,
            )
            path, body = "/start", {}

        def second_request() -> None:
            response = client.post(
                _t_url(league_id, str(tournament_id), path),
                json={"expected_draw_counter": counter, **body},
                headers=committed_auth_header(owner_id, issued_at=datetime.now(UTC)),
            )
            outcome.append((response.status_code, response.json()))

        second = threading.Thread(target=second_request)
        second.start()
        wait_for_a_lock_wait()  # it waits for the league lock the first one holds
        first.commit()
        second.join()

    stale = {
        "start": {
            "code": "tournament_not_in_setup",
            "detail": {"state": "in_progress"},
        },
        "draw": {
            "code": "draw_counter_changed",
            "detail": {"draw_counter": counter + 1},
        },
    }
    assert outcome == [(409, stale[winner])]
    with Session(committing_engine) as check:
        tournament = check.get_one(Tournament, tournament_id)
        rounds = check.scalar(select(func.count()).select_from(Round))
        if winner == "start":
            assert (tournament.state, tournament.draw_counter, rounds) == (
                "in_progress",
                counter,
                3,
            )
        else:
            assert (tournament.state, tournament.draw_counter, rounds) == (
                "setup",
                counter + 1,
                0,
            )


# ---------------------------------------------------------------- the size limit


def test_fr032_a_round_robin_of_64_entries_starts_with_both_legs(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    make_player: Callable[..., Player],
) -> None:
    ids = [str(make_player(league=league, name=f"Q{n}").id) for n in range(64)]
    setup = _setup(client, league, headers, ids, round_robin_legs=2)

    began = time.perf_counter()
    status, body = _start(client, league, setup, headers)
    took = time.perf_counter() - began

    assert status == 200, body
    assert len(body["rounds"]) == 126
    assert sum(len(r["matches"]) for r in body["rounds"]) == 64 * 63
    assert took < 30  # the bulk insert takes a few seconds; one object per row, minutes


def test_fr032_a_round_robin_of_65_entries_is_refused(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    make_player: Callable[..., Player],
    session: Session,
) -> None:
    ids = [str(make_player(league=league, name=f"Q{n}").id) for n in range(65)]
    setup = _setup(client, league, headers, ids)

    status, body = _start(client, league, setup, headers)

    assert (status, body) == (
        422,
        {"code": "too_many_entries_for_round_robin", "detail": {"limit": 64}},
    )
    assert session.scalar(select(func.count()).select_from(Round)) == 0
