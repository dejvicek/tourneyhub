import re
import time
from collections.abc import Callable, Iterator
from typing import Any
from uuid import UUID, uuid7

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event, func, select
from sqlalchemy.orm import Session

from tourneyhub.db.models.leagues import League, Player
from tourneyhub.db.models.matches import Match, Round
from tourneyhub.db.models.tournaments import Tournament

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


def _seed_order(setup: Json) -> list[str]:
    """The entries of a setup in seed order, as the review's start carries them."""
    return [e["id"] for e in sorted(setup["entries"], key=lambda e: e["seed"] or 0)]


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


def _preview(
    client: TestClient, league: League | UUID, tournament_id: str, headers: Json
) -> tuple[int, Json]:
    response = client.get(
        _t_url(league, tournament_id, "/setup/preview"), headers=headers
    )
    result: Json = response.json()
    return response.status_code, result


def _start(
    client: TestClient, league: League, setup: Json, headers: dict[str, str]
) -> tuple[int, Json]:
    response = client.post(
        _t_url(league, setup["tournament_id"], "/start"),
        json={
            "expected_draw_counter": setup["draw_counter"],
            "expected_seed_order": _seed_order(setup),
        },
        headers=headers,
    )
    result: Json = response.json()
    return response.status_code, result


def _shown(tournament: Json) -> list[tuple[list[list[str]], list[list[str]]]]:
    """The rounds of a started tournament as the preview shows them."""
    members = {e["id"]: e["player_ids"] for e in tournament["entries"]}
    return [
        (
            [[s["player_ids"] for s in m["sides"]] for m in r["matches"]],
            [members[entry_id] for entry_id in r["sitting_out"]],
        )
        for r in tournament["rounds"]
    ]


@pytest.mark.parametrize(
    ("values", "picked", "pairs"),
    [
        pytest.param({}, 5, None, id="singles-odd"),
        pytest.param({}, 6, None, id="singles-even"),
        pytest.param({"round_robin_legs": 2}, 3, None, id="two-legs"),
        pytest.param({"type": "dyp"}, 6, None, id="dyp"),
        pytest.param({"type": "dyp"}, 5, None, id="dyp-one-left-out"),
        pytest.param({"type": "doubles"}, 6, [(0, 1), (2, 3), (4, 5)], id="doubles"),
    ],
)
def test_fr035_the_preview_is_the_schedule_the_start_creates(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    players: list[str],
    values: Json,
    picked: int,
    pairs: list[tuple[int, int]] | None,
) -> None:
    setup = _setup(client, league, headers, players[:picked], **values)
    if pairs is not None:
        setup = client.put(
            _t_url(league, setup["tournament_id"], "/setup/pairs"),
            json={"pairs": [[players[a], players[b]] for a, b in pairs]},
            headers=headers,
        ).json()

    status, preview = _preview(client, league, setup["tournament_id"], headers)
    started_status, started = _start(client, league, setup, headers)

    assert (status, started_status) == (200, 200)
    assert preview["can_start"] is True
    assert preview["problem"] is None
    assert preview["draw_counter"] == setup["draw_counter"]
    assert [r["round_no"] for r in preview["rounds"]] == [
        r["round_no"] for r in started["rounds"]
    ]
    assert [
        (
            [[m["sides"][0], m["sides"][1]] for m in r["matches"]],
            r["sitting_out"],
        )
        for r in preview["rounds"]
    ] == _shown(started)
    assert preview["round_count"] == len(started["rounds"])
    assert preview["match_count"] == sum(len(r["matches"]) for r in started["rounds"])
    assert preview["bracket_size"] is None


def test_br051_the_preview_names_the_players_who_sit_out_each_round(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    setup = _setup(client, league, headers, players[:5])
    seeds = {e["id"]: e["player_ids"] for e in setup["entries"]}

    _, preview = _preview(client, league, setup["tournament_id"], headers)

    sitting = [r["sitting_out"] for r in preview["rounds"]]
    assert sorted(s[0][0] for s in sitting) == sorted(ids[0] for ids in seeds.values())
    assert all(len(s) == 1 for s in sitting)
    assert preview["match_count"] == 10
    assert preview["round_count"] == 5


@pytest.mark.parametrize(
    ("values", "picked"),
    [
        pytest.param({}, 1, id="FR-032"),
        pytest.param({"type": "dyp"}, 3, id="BR-031"),
        pytest.param({"group_phase": "swiss", "round_robin_legs": None}, 4, id="swiss"),
        pytest.param(
            {
                "group_phase": "none",
                "round_robin_legs": None,
                "sit_out_points": None,
                "group_match_format": None,
                "knockout_match_format": "bo1",
                "third_place_match": True,
            },
            3,
            id="knockout-third-place-FR-032",
        ),
        pytest.param(
            {
                "type": "monster_dyp",
                "group_phase": "monster_dyp",
                "round_robin_legs": None,
            },
            4,
            id="monster-dyp",
        ),
    ],
)
def test_fr035_a_setup_that_cannot_start_names_the_reason_the_start_gives(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    players: list[str],
    values: Json,
    picked: int,
) -> None:
    setup = _setup(client, league, headers, players[:picked], **values)

    status, preview = _preview(client, league, setup["tournament_id"], headers)
    _, refusal = _start(client, league, setup, headers)

    assert status == 200
    assert preview["problem"] == refusal
    assert refusal["code"] in {
        "not_enough_entries",
        "not_enough_players",
        "format_not_supported",
    }
    assert preview["can_start"] is False
    assert preview["rounds"] == []
    assert (preview["match_count"], preview["round_count"]) == (None, None)
    assert preview["draw_counter"] == setup["draw_counter"]


def test_fr033_a_doubles_player_without_a_partner_is_the_reason(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    setup = _setup(client, league, headers, players[:5], type="doubles")
    paired = client.put(
        _t_url(league, setup["tournament_id"], "/setup/pairs"),
        json={"pairs": [players[:2], players[2:4]]},
        headers=headers,
    ).json()

    _, preview = _preview(client, league, paired["tournament_id"], headers)
    _, refusal = _start(client, league, paired, headers)

    assert preview["problem"] == refusal
    assert refusal == {"code": "players_without_partner", "detail": {"unpaired": 1}}
    assert preview["can_start"] is False


def test_br032_incomplete_hand_halves_are_the_reason(
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

    _, preview = _preview(client, league, halves["tournament_id"], headers)

    assert preview["problem"] == {
        "code": "dyp_halves_incomplete",
        "detail": {"missing": 3},
    }


def test_fr032_a_round_robin_of_65_entries_is_not_previewed(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    make_player: Callable[..., Player],
) -> None:
    ids = [str(make_player(league=league, name=f"Q{n}").id) for n in range(65)]
    setup = _setup(client, league, headers, ids)

    _, preview = _preview(client, league, setup["tournament_id"], headers)
    _, refusal = _start(client, league, setup, headers)

    assert preview["problem"] == refusal
    assert refusal == {
        "code": "too_many_entries_for_round_robin",
        "detail": {"limit": 64},
    }
    assert preview["can_start"] is False
    assert preview["rounds"] == []


def test_fr032_a_round_robin_of_64_entries_previews_both_legs(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    make_player: Callable[..., Player],
) -> None:
    ids = [str(make_player(league=league, name=f"Q{n}").id) for n in range(64)]
    setup = _setup(client, league, headers, ids, round_robin_legs=2)

    began = time.perf_counter()
    status, preview = _preview(client, league, setup["tournament_id"], headers)
    took = time.perf_counter() - began

    assert status == 200
    assert preview["can_start"] is True
    assert (preview["round_count"], preview["match_count"]) == (126, 64 * 63)
    assert took < 10


def test_adr008_a_started_tournament_has_no_schedule_to_preview(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    setup = _setup(client, league, headers, players[:4])
    _start(client, league, setup, headers)

    status, preview = _preview(client, league, setup["tournament_id"], headers)
    _, refusal = _start(client, league, setup, headers)

    assert status == 200
    assert preview["problem"] == {
        "code": "tournament_not_in_setup",
        "detail": {"state": "in_progress"},
    }
    assert refusal["code"] == "tournament_not_in_setup"
    assert preview["rounds"] == []


def test_adr010_the_preview_carries_the_draw_counter_the_start_expects(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    setup = _setup(client, league, headers, players[:6], type="dyp")
    drawn = client.post(
        _t_url(league, setup["tournament_id"], "/setup/draw"),
        json={
            "expected_draw_counter": setup["draw_counter"],
            "target": "pairs",
        },
        headers=headers,
    ).json()
    assert drawn["draw_counter"] == setup["draw_counter"] + 1

    _, preview = _preview(client, league, setup["tournament_id"], headers)
    started = client.post(
        _t_url(league, setup["tournament_id"], "/start"),
        json={
            "expected_draw_counter": preview["draw_counter"],
            "expected_seed_order": preview["seed_order"],
        },
        headers=headers,
    )

    assert preview["draw_counter"] == drawn["draw_counter"]
    assert started.status_code == 200


@pytest.fixture
def statements(engine: Engine) -> Iterator[list[str]]:
    seen: list[str] = []

    def record(*args: Any) -> None:  # noqa: ANN401  (SQLAlchemy's event signature)
        seen.append(args[2])

    event.listen(engine, "before_cursor_execute", record)
    yield seen
    event.remove(engine, "before_cursor_execute", record)


def test_fr035_the_preview_writes_nothing(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    players: list[str],
    session: Session,
    statements: list[str],
) -> None:
    setup = _setup(client, league, headers, players[:6])
    tournament = session.get_one(Tournament, UUID(setup["tournament_id"]))
    session.refresh(tournament)
    before = (tournament.state, tournament.draw_counter, tournament.updated_at)
    statements.clear()

    status, _ = _preview(client, league, setup["tournament_id"], headers)

    session.refresh(tournament)
    assert status == 200
    assert (tournament.state, tournament.draw_counter, tournament.updated_at) == before
    assert session.scalar(select(func.count()).select_from(Round)) == 0
    assert session.scalar(select(func.count()).select_from(Match)) == 0
    assert statements
    writes = [
        s
        for s in statements
        if not re.match(
            r"\s*(SELECT|SAVEPOINT|RELEASE|SET CONSTRAINTS)\b", s, re.IGNORECASE
        )
        or re.search(r"\bFOR UPDATE\b", s, re.IGNORECASE)
    ]
    assert writes == []


def test_owasp_api1_a_tournament_of_another_league_has_no_preview(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    players: list[str],
    make_league: Callable[..., League],
) -> None:
    other = make_league(owner_user_id=league.owner_user_id)
    setup = _setup(client, league, headers, players[:4])

    status, body = _preview(client, other, setup["tournament_id"], headers)
    unknown_status, unknown = _preview(client, league, str(uuid7()), headers)

    assert (status, unknown_status) == (404, 404)
    assert body == unknown == {"code": "tournament_not_found", "detail": {}}


def test_owasp_api1_another_organizers_league_has_no_preview(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    players: list[str],
    make_league: Callable[..., League],
    auth_header: Callable[..., dict[str, str]],
) -> None:
    setup = _setup(client, league, headers, players[:4])
    intruder = auth_header(make_league().owner_user_id)

    status, body = _preview(client, league, setup["tournament_id"], intruder)
    missing_status, missing = _preview(client, uuid7(), setup["tournament_id"], headers)

    assert (status, missing_status) == (404, 404)
    assert body == missing == {"code": "league_not_found", "detail": {}}


def test_adr006_the_preview_needs_a_signed_in_organizer(
    client: TestClient, league: League, headers: dict[str, str], players: list[str]
) -> None:
    setup = _setup(client, league, headers, players[:4])

    response = client.get(_t_url(league, setup["tournament_id"], "/setup/preview"))

    assert response.status_code == 401
