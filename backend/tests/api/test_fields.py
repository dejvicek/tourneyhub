"""Fields while the tournament runs: add, remove and place by hand (FR-090 to FR-094)."""

import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid7

import httpx2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from tourneyhub.app import create_app
from tourneyhub.db.models.accounts import User
from tourneyhub.db.models.leagues import League, Player
from tourneyhub.db.models.matches import Match
from tourneyhub.engine.accounts import Language
from tourneyhub.engine.results import Game
from tourneyhub.engine.tournaments import (
    GroupPhase,
    Outcome,
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
    "sit_out_points": 0,
    "group_match_format": "bo1",
    "knockout_match_format": None,
    "final_match_format": None,
    "third_place_match": None,
    "goals_per_game": 10,
    "field_count": 2,
}
S1_WINS: Json = {
    "walkover_winner": None,
    "games": [{"winner": "side_1", "score_1": 10, "score_2": 7}],
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
def league_id(league: League) -> UUID:
    """The league's id, read before a request expires the row."""
    return league.id


@pytest.fixture
def headers(
    league: League, auth_header: Callable[..., dict[str, str]]
) -> dict[str, str]:
    return auth_header(league.owner_user_id)


@pytest.fixture
def players(league: League, make_player: Callable[..., Player]) -> list[str]:
    return [str(make_player(league=league, name=f"P{n}").id) for n in range(1, 7)]


@pytest.fixture
def create(
    client: TestClient, league_id: UUID, headers: dict[str, str]
) -> Callable[..., Json]:
    """Create and pick a round robin in setup; returns the setup."""

    def create(player_ids: list[str], **values: object) -> Json:
        body = {"id": str(uuid7()), **ROUND_ROBIN, **values}
        created = client.post(
            _url(league_id, "/tournaments"), json=body, headers=headers
        )
        assert created.status_code == 201, created.text
        tournament_id = created.json()["tournament_id"]
        picked = client.put(
            _t_url(league_id, tournament_id, "/setup/players"),
            json={"player_ids": player_ids},
            headers=headers,
        )
        assert picked.status_code == 200, picked.text
        setup: Json = picked.json()
        return setup

    return create


@pytest.fixture
def start(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    create: Callable[..., Json],
) -> Callable[..., Json]:
    """Create, pick and start a round robin of Singles; returns the tournament."""

    def start(player_ids: list[str], **values: object) -> Json:
        setup = create(player_ids, **values)
        started = client.post(
            _t_url(league_id, setup["tournament_id"], "/start"),
            json={"expected_draw_counter": setup["draw_counter"]},
            headers=headers,
        )
        assert started.status_code == 200, started.text
        tournament: Json = started.json()
        return tournament

    return start


@pytest.fixture
def read(
    client: TestClient, league_id: UUID, headers: dict[str, str]
) -> Callable[[Json], Json]:
    def read(tournament: Json, rest: str = "") -> Json:
        response = client.get(
            _t_url(league_id, tournament["id"], rest), headers=headers
        )
        assert response.status_code == 200, response.text
        body: Json = response.json()
        return body

    return read


@pytest.fixture
def send(
    client: TestClient, league_id: UUID, headers: dict[str, str]
) -> Callable[..., tuple[int, Json]]:
    """Send a request to a tournament's route; returns the status and the body."""

    def send(
        method: str, tournament: Json, rest: str, body: Json | None = None
    ) -> tuple[int, Json]:
        response = client.request(
            method,
            _t_url(league_id, tournament["id"], rest),
            json=body,
            headers=headers,
        )
        result: Json = response.json() if response.content else {}
        return response.status_code, result

    return send


@pytest.fixture
def place(send: Callable[..., tuple[int, Json]]) -> Callable[..., tuple[int, Json]]:
    """PUT …/fields/placements with (match id, field id or None) pairs.

    The `from_field_id` of each is the field `tournament`, the screen the
    request comes from, shows the match on.
    """

    def place(tournament: Json, *pairs: tuple[str, str | None]) -> tuple[int, Json]:
        body = {
            "placements": [
                {
                    "match_id": match_id,
                    "field_id": field_id,
                    "from_field_id": seen_on(tournament, match_id),
                }
                for match_id, field_id in pairs
            ]
        }
        return send("PUT", tournament, "/fields/placements", body)

    return place


@pytest.fixture
def put_result(
    send: Callable[..., tuple[int, Json]],
) -> Callable[[Json, str], None]:
    def put_result(tournament: Json, match_id: str) -> None:
        status, body = send("PUT", tournament, f"/matches/{match_id}/result", S1_WINS)
        assert status == 200, body

    return put_result


def round_matches(tournament: Json, round_no: int) -> list[str]:
    """The ids of a round's matches, in schedule order."""
    (round_,) = [r for r in tournament["rounds"] if r["round_no"] == round_no]
    return [m["id"] for m in sorted(round_["matches"], key=lambda m: m["position"])]


def on_fields(tournament: Json) -> dict[int, str | None]:
    """Each field's number with its match."""
    return {f["number"]: f["match_id"] for f in tournament["fields"]}


def seen_on(tournament: Json, match_id: str) -> str | None:
    """The id of the field a match is on in a read, None while it waits."""
    return next(
        (f["id"] for f in tournament["fields"] if f["match_id"] == match_id), None
    )


def field_id(tournament: Json, number: int) -> str:
    (field,) = [f for f in tournament["fields"] if f["number"] == number]
    return str(field["id"])


def players_of(tournament: Json, match_id: str) -> set[str]:
    (match,) = [
        m for r in tournament["rounds"] for m in r["matches"] if m["id"] == match_id
    ]
    return {player for side in match["sides"] for player in side["player_ids"]}


def assert_nobody_on_two_fields(tournament: Json) -> None:
    """BR-131 over the whole tournament as a read returns it."""
    seen = [
        player
        for match_id in on_fields(tournament).values()
        if match_id is not None
        for player in players_of(tournament, match_id)
    ]
    assert len(seen) == len(set(seen))


# 4 players on 3 fields: round 1's two matches hold everyone, so Field 3 is
# free and every later match waits for a player on a field (BR-131).
# 6 players on 2 fields: round 1's third match waits and could be played.


# ---------------------------------------------------------------- adding


def test_br132_a_new_field_takes_the_next_waiting_match_at_once(
    start: Callable[..., Json],
    send: Callable[..., tuple[int, Json]],
    read: Callable[..., Json],
    players: list[str],
) -> None:
    tournament = start(players)
    third = round_matches(tournament, 1)[2]
    assert tournament["waiting"][0] == third

    status, body = send("POST", tournament, "/fields", {"number": 3})

    assert status == 201
    assert body == {"id": body["id"], "number": 3, "match_id": third}
    after = read(tournament)
    assert on_fields(after)[3] == third
    assert third not in after["waiting"]
    assert third not in [w["match_id"] for w in read(tournament, "/play")["waiting"]]


def test_br132_a_new_field_stays_free_while_no_waiting_match_can_be_played(
    start: Callable[..., Json],
    send: Callable[..., tuple[int, Json]],
    players: list[str],
) -> None:
    tournament = start(players[:4], field_count=3)

    status, body = send("POST", tournament, "/fields", {"number": 4})

    assert status == 201
    assert body["match_id"] is None


def test_br132_a_new_field_takes_the_number_a_removed_one_left(
    start: Callable[..., Json],
    send: Callable[..., tuple[int, Json]],
    read: Callable[..., Json],
    players: list[str],
) -> None:
    tournament = start(players[:4], field_count=3)
    removed, _ = send("DELETE", tournament, f"/fields/{field_id(tournament, 1)}")
    assert removed == 204

    status, body = send("POST", tournament, "/fields", {"number": 1})

    assert status == 201
    assert sorted(on_fields(read(tournament))) == [1, 2, 3]
    assert body["number"] == 1


@pytest.mark.parametrize(
    ("number", "first"),
    [
        pytest.param(3, True, id="a-repeat"),
        pytest.param(4, False, id="not-the-lowest-free"),
    ],
)
def test_adr008_a_stale_field_number_is_409_with_the_current_one(
    start: Callable[..., Json],
    send: Callable[..., tuple[int, Json]],
    read: Callable[..., Json],
    players: list[str],
    number: int,
    first: bool,
) -> None:
    tournament = start(players)
    if first:
        assert send("POST", tournament, "/fields", {"number": number})[0] == 201
    before = read(tournament)

    status, body = send("POST", tournament, "/fields", {"number": number})

    assert status == 409
    assert body == {
        "code": "field_number_changed",
        "detail": {"number": 4 if first else 3},
    }
    assert read(tournament) == before


def test_br132_no_field_is_added_beyond_32(
    start: Callable[..., Json],
    send: Callable[..., tuple[int, Json]],
    players: list[str],
) -> None:
    tournament = start(players[:2], field_count=32)

    status, body = send("POST", tournament, "/fields", {"number": 32})

    assert status == 409
    assert body == {"code": "field_number_changed", "detail": {"number": None}}


@pytest.mark.parametrize("number", [0, 33])
def test_adr008_a_field_number_outside_1_to_32_is_invalid(
    start: Callable[..., Json],
    send: Callable[..., tuple[int, Json]],
    players: list[str],
    number: int,
) -> None:
    tournament = start(players[:2])

    status, body = send("POST", tournament, "/fields", {"number": number})

    assert status == 422
    assert body["code"] == "validation_failed"


# ---------------------------------------------------------------- removing


def test_br132_removing_a_field_keeps_the_other_numbers(
    start: Callable[..., Json],
    send: Callable[..., tuple[int, Json]],
    read: Callable[..., Json],
    players: list[str],
) -> None:
    tournament = start(players[:4], field_count=3)
    before = on_fields(tournament)

    status, body = send("DELETE", tournament, f"/fields/{field_id(tournament, 2)}")

    assert status == 204
    assert body == {}
    after = on_fields(read(tournament))
    assert sorted(after) == [1, 3]
    assert after[1] == before[1]


def test_br132_the_match_of_a_removed_field_waits_first(
    start: Callable[..., Json],
    send: Callable[..., tuple[int, Json]],
    read: Callable[..., Json],
    put_result: Callable[[Json, str], None],
    players: list[str],
) -> None:
    tournament = start(players)
    first, second, _ = round_matches(tournament, 1)

    status, _ = send("DELETE", tournament, f"/fields/{field_id(tournament, 1)}")

    assert status == 204
    after = read(tournament)
    assert after["waiting"][0] == first
    assert on_fields(after) == {2: second}
    # It goes ahead of the schedule order when the next field frees up.
    put_result(tournament, second)
    assert on_fields(read(tournament)) == {2: first}


def test_br132_the_match_of_a_removed_field_takes_a_free_field_at_once(
    start: Callable[..., Json],
    send: Callable[..., tuple[int, Json]],
    read: Callable[..., Json],
    session: Session,
    players: list[str],
) -> None:
    tournament = start(players[:4], field_count=3)
    first, second = round_matches(tournament, 1)

    status, _ = send("DELETE", tournament, f"/fields/{field_id(tournament, 1)}")

    assert status == 204
    assert on_fields(read(tournament)) == {2: second, 3: first}
    requeued = session.scalar(select(Match.requeued_at).where(Match.id == UUID(first)))
    assert requeued is None


def test_br132_the_last_field_cannot_be_removed(
    start: Callable[..., Json],
    send: Callable[..., tuple[int, Json]],
    read: Callable[..., Json],
    players: list[str],
) -> None:
    tournament = start(players[:2], field_count=1)

    status, body = send("DELETE", tournament, f"/fields/{field_id(tournament, 1)}")

    assert status == 422
    assert body == {"code": "last_field", "detail": {}}
    assert read(tournament)["fields"] == tournament["fields"]


@pytest.mark.parametrize("which", ["unknown", "repeat", "another-tournament"])
def test_adr008_a_field_that_is_not_there_is_404(
    start: Callable[..., Json],
    send: Callable[..., tuple[int, Json]],
    players: list[str],
    which: str,
) -> None:
    tournament = start(players[:4], field_count=3)
    target = str(uuid7())
    if which == "repeat":
        target = field_id(tournament, 3)
        assert send("DELETE", tournament, f"/fields/{target}")[0] == 204
    elif which == "another-tournament":
        target = field_id(start(players[4:]), 1)

    status, body = send("DELETE", tournament, f"/fields/{target}")

    assert status == 404
    assert body == {"code": "field_not_found", "detail": {}}


# ---------------------------------------------------------------- by hand


def test_fr093_a_match_moves_to_a_free_field_and_a_repeat_is_409(
    start: Callable[..., Json],
    place: Callable[..., tuple[int, Json]],
    read: Callable[..., Json],
    players: list[str],
) -> None:
    tournament = start(players[:4], field_count=3)
    first, second = round_matches(tournament, 1)
    move = (first, field_id(tournament, 3))

    status, moved = place(tournament, move)
    again, repeated = place(tournament, move)

    assert status == 200
    # Field 1 stays free: every waiting match has a player on a field (BR-131).
    assert on_fields(moved) == {1: None, 2: second, 3: first}
    # The repeat comes from the screen that saw the match on Field 1.
    assert (again, repeated["code"]) == (409, "placement_changed")
    assert read(tournament) == moved


def test_fr093_a_swap_names_both_matches_and_a_repeat_is_409(
    start: Callable[..., Json],
    place: Callable[..., tuple[int, Json]],
    read: Callable[..., Json],
    players: list[str],
) -> None:
    tournament = start(players)
    first, second, _ = round_matches(tournament, 1)
    swap = ((first, field_id(tournament, 2)), (second, field_id(tournament, 1)))

    status, swapped = place(tournament, *swap)
    again, repeated = place(tournament, *swap)

    assert status == 200
    assert on_fields(swapped) == {1: second, 2: first}
    assert swapped["waiting"] == tournament["waiting"]
    assert (again, repeated["code"]) == (409, "placement_changed")
    assert read(tournament) == swapped


def test_fr093_a_match_sent_back_waits_and_its_field_takes_the_next_one(
    start: Callable[..., Json],
    place: Callable[..., tuple[int, Json]],
    read: Callable[..., Json],
    players: list[str],
) -> None:
    tournament = start(players)
    first, second, third = round_matches(tournament, 1)

    status, after = place(tournament, (first, None))

    assert status == 200
    assert on_fields(after) == {1: third, 2: second}
    # It waits in schedule order, which puts it first here (DATA-MODEL §4.6).
    assert after["waiting"][0] == first
    assert read(tournament, "/play")["waiting"][0] == {"match_id": first, "busy": []}


def test_fr093_a_match_sent_back_takes_a_field_only_at_the_next_fill(
    start: Callable[..., Json],
    place: Callable[..., tuple[int, Json]],
    read: Callable[..., Json],
    put_result: Callable[[Json, str], None],
    players: list[str],
) -> None:
    tournament = start(players[:4], field_count=3)
    first, second = round_matches(tournament, 1)

    status, after = place(tournament, (first, None))

    assert status == 200
    assert on_fields(after) == {1: None, 2: second, 3: None}
    put_result(tournament, second)
    assert on_fields(read(tournament))[1] == first


def test_fr093_a_waiting_match_goes_on_a_free_field(
    start: Callable[..., Json],
    place: Callable[..., tuple[int, Json]],
    players: list[str],
) -> None:
    tournament = start(players[:4], field_count=3)
    first, second = round_matches(tournament, 1)
    sent_back = place(tournament, (first, None))[1]

    status, after = place(sent_back, (first, field_id(tournament, 3)))

    assert status == 200
    assert on_fields(after) == {1: None, 2: second, 3: first}
    assert first not in after["waiting"]


def test_br133_a_match_placed_by_hand_stays_until_its_result(
    start: Callable[..., Json],
    place: Callable[..., tuple[int, Json]],
    read: Callable[..., Json],
    put_result: Callable[[Json, str], None],
    players: list[str],
) -> None:
    tournament = start(players[:4], field_count=3)
    first, second = round_matches(tournament, 1)
    sent_back = place(tournament, (first, None))[1]
    place(sent_back, (first, field_id(tournament, 3)))

    put_result(tournament, second)

    # Fields 1 and 2 are free and lower, yet the match stays on Field 3.
    assert on_fields(read(tournament)) == {1: None, 2: None, 3: first}
    put_result(tournament, first)
    after = read(tournament)
    # Now the order fills the free fields again, lowest number first (BR-130).
    assert on_fields(after) == {
        1: round_matches(after, 2)[0],
        2: round_matches(after, 2)[1],
        3: None,
    }
    assert_nobody_on_two_fields(after)


def test_br131_a_placement_that_puts_a_player_on_two_fields_is_422(
    start: Callable[..., Json],
    place: Callable[..., tuple[int, Json]],
    read: Callable[..., Json],
    players: list[str],
) -> None:
    tournament = start(players[:4], field_count=3)
    later = round_matches(tournament, 2)[0]
    free = field_id(tournament, 3)

    status, body = place(tournament, (later, free))

    assert status == 422
    assert body["code"] == "player_on_another_field"
    assert set(body["detail"]["player_ids"]) == players_of(tournament, later)
    assert body["detail"]["player_ids"] == sorted(body["detail"]["player_ids"])
    assert body["detail"]["field_ids"][-1] == free
    assert read(tournament) == tournament


def test_adr008_a_field_another_match_took_is_409(
    start: Callable[..., Json],
    place: Callable[..., tuple[int, Json]],
    players: list[str],
) -> None:
    tournament = start(players)
    first, _, third = round_matches(tournament, 1)

    status, body = place(tournament, (third, field_id(tournament, 1)))

    assert status == 409
    assert body == {
        "code": "field_not_free",
        "detail": {"field_id": field_id(tournament, 1), "match_id": first},
    }


def test_adr008_a_match_with_a_result_is_409(
    start: Callable[..., Json],
    place: Callable[..., tuple[int, Json]],
    put_result: Callable[[Json, str], None],
    players: list[str],
) -> None:
    tournament = start(players[:4], field_count=3)
    first, _ = round_matches(tournament, 1)
    put_result(tournament, first)

    status, body = place(tournament, (first, field_id(tournament, 3)))

    assert status == 409
    assert body == {"code": "match_has_result", "detail": {"match_id": first}}


def test_adr008_a_match_that_is_not_where_the_screen_saw_it_is_409(
    start: Callable[..., Json],
    send: Callable[..., tuple[int, Json]],
    read: Callable[..., Json],
    players: list[str],
) -> None:
    tournament = start(players[:4], field_count=3)
    first, _ = round_matches(tournament, 1)

    # The screen saw the first match waiting; it is on Field 1.
    status, body = send(
        "PUT",
        tournament,
        "/fields/placements",
        {
            "placements": [
                {
                    "match_id": first,
                    "field_id": field_id(tournament, 3),
                    "from_field_id": None,
                }
            ]
        },
    )

    assert status == 409
    assert body == {"code": "placement_changed", "detail": {}}
    assert read(tournament) == tournament


def test_adr008_a_match_where_the_screen_saw_it_is_placed(
    start: Callable[..., Json],
    send: Callable[..., tuple[int, Json]],
    players: list[str],
) -> None:
    tournament = start(players[:4], field_count=3)
    first, second = round_matches(tournament, 1)
    one, three = field_id(tournament, 1), field_id(tournament, 3)

    status, moved = send(
        "PUT",
        tournament,
        "/fields/placements",
        {"placements": [{"match_id": first, "field_id": three, "from_field_id": one}]},
    )

    assert status == 200
    assert on_fields(moved) == {1: None, 2: second, 3: first}


def test_adr008_from_field_id_is_required(
    start: Callable[..., Json],
    send: Callable[..., tuple[int, Json]],
    players: list[str],
) -> None:
    tournament = start(players[:4], field_count=3)
    first, _ = round_matches(tournament, 1)

    status, body = send(
        "PUT",
        tournament,
        "/fields/placements",
        {"placements": [{"match_id": first, "field_id": field_id(tournament, 3)}]},
    )

    assert (status, body["code"]) == (422, "validation_failed")


def test_adr008_a_swap_with_one_stale_match_is_409_and_changes_nothing(
    start: Callable[..., Json],
    send: Callable[..., tuple[int, Json]],
    read: Callable[..., Json],
    players: list[str],
) -> None:
    tournament = start(players)
    first, second, _ = round_matches(tournament, 1)
    one, two = field_id(tournament, 1), field_id(tournament, 2)

    status, body = send(
        "PUT",
        tournament,
        "/fields/placements",
        {
            "placements": [
                {"match_id": first, "field_id": two, "from_field_id": one},
                {"match_id": second, "field_id": one, "from_field_id": one},
            ]
        },
    )

    assert (status, body["code"]) == (409, "placement_changed")
    assert read(tournament) == tournament


def test_fr093_a_waiting_match_cannot_replace_the_match_on_a_field(
    start: Callable[..., Json],
    place: Callable[..., tuple[int, Json]],
    read: Callable[..., Json],
    players: list[str],
) -> None:
    tournament = start(players)
    first, _, third = round_matches(tournament, 1)

    # The third match takes Field 1 and sends the first back to waiting.
    status, body = place(tournament, (third, field_id(tournament, 1)), (first, None))

    assert status == 422
    assert body == {"code": "placement_not_allowed", "detail": {}}
    assert read(tournament) == tournament


def test_fr093_matches_cannot_rotate_onto_a_free_field(
    start: Callable[..., Json],
    place: Callable[..., tuple[int, Json]],
    read: Callable[..., Json],
    players: list[str],
) -> None:
    tournament = start(players[:4], field_count=3)
    first, second = round_matches(tournament, 1)

    # The first match takes Field 2 while the second leaves it for Field 3.
    status, body = place(
        tournament,
        (first, field_id(tournament, 2)),
        (second, field_id(tournament, 3)),
    )

    assert status == 422
    assert body["code"] == "placement_not_allowed"
    assert read(tournament) == tournament


def test_fr093_two_changes_in_one_request_that_are_no_swap_are_422(
    start: Callable[..., Json],
    place: Callable[..., tuple[int, Json]],
    players: list[str],
) -> None:
    tournament = start(players[:4], field_count=3)
    first, second = round_matches(tournament, 1)

    status, body = place(tournament, (first, None), (second, None))

    assert (status, body["code"]) == (422, "placement_not_allowed")


def test_fr093_a_match_placed_where_it_already_is_is_422(
    start: Callable[..., Json],
    place: Callable[..., tuple[int, Json]],
    players: list[str],
) -> None:
    tournament = start(players)
    first, *_ = round_matches(tournament, 1)

    status, body = place(tournament, (first, field_id(tournament, 1)))

    assert (status, body["code"]) == (422, "placement_not_allowed")


@pytest.mark.parametrize("which", ["match", "field", "match-of-another-tournament"])
def test_adr008_unknown_ids_in_a_placement_are_404(
    start: Callable[..., Json],
    place: Callable[..., tuple[int, Json]],
    players: list[str],
    which: str,
) -> None:
    tournament = start(players[:4], field_count=3)
    match_id, target = round_matches(tournament, 1)[0], field_id(tournament, 3)
    if which == "match":
        match_id = str(uuid7())
    elif which == "field":
        target = str(uuid7())
    else:
        match_id = round_matches(start(players[4:]), 1)[0]

    status, body = place(tournament, (match_id, target))

    assert status == 404
    code = "field_not_found" if which == "field" else "match_not_found"
    assert body == {"code": code, "detail": {}}


@pytest.mark.parametrize("shape", ["empty", "three", "match-twice", "field-twice"])
def test_adr008_a_placement_list_must_name_one_or_two_distinct_matches(
    start: Callable[..., Json],
    send: Callable[..., tuple[int, Json]],
    players: list[str],
    shape: str,
) -> None:
    tournament = start(players)
    first, second, third = round_matches(tournament, 1)
    one, two = field_id(tournament, 1), field_id(tournament, 2)
    shapes: dict[str, list[tuple[str, str | None]]] = {
        "empty": [],
        "three": [(first, None), (second, None), (third, None)],
        "match-twice": [(first, one), (first, two)],
        "field-twice": [(first, one), (second, one)],
    }
    placements = shapes[shape]

    status, body = send(
        "PUT",
        tournament,
        "/fields/placements",
        {"placements": [{"match_id": m, "field_id": f} for m, f in placements]},
    )

    assert status == 422
    assert body["code"] == "validation_failed"


# ---------------------------------------------------------------- state


ROUTES = [
    pytest.param("POST", "/fields", {"number": 2}, id="add"),
    pytest.param("DELETE", "/fields/{field_id}", None, id="remove"),
    pytest.param(
        "PUT",
        "/fields/placements",
        {
            "placements": [
                {"match_id": "{match_id}", "field_id": None, "from_field_id": None}
            ]
        },
        id="place",
    ),
]


def _fill_in(rest: str, body: Json | None, tournament: Json) -> tuple[str, Json | None]:
    matches = [m["id"] for r in tournament.get("rounds", []) for m in r["matches"]]
    ids = {
        "field_id": tournament["fields"][0]["id"]
        if tournament.get("fields")
        else str(uuid7()),
        "match_id": matches[0] if matches else str(uuid7()),
    }
    if body is not None and "placements" in body:
        body = {
            "placements": [
                {"match_id": ids["match_id"], "field_id": None, "from_field_id": None}
            ]
        }
    return rest.format(**ids), body


@pytest.mark.parametrize(("method", "rest", "body"), ROUTES)
def test_fr090_fields_change_only_while_the_tournament_runs(
    start: Callable[..., Json],
    send: Callable[..., tuple[int, Json]],
    put_result: Callable[[Json, str], None],
    players: list[str],
    method: str,
    rest: str,
    body: Json | None,
) -> None:
    tournament = start(players[:2], field_count=1)
    (match_id,) = round_matches(tournament, 1)
    put_result(tournament, match_id)
    finished, _ = send("POST", tournament, "/finish", {"expected_state": "in_progress"})
    assert finished == 200
    rest, body = _fill_in(rest, body, tournament)

    status, response = send(method, tournament, rest, body)

    assert status == 409
    assert response == {
        "code": "tournament_not_in_progress",
        "detail": {"state": "finished"},
    }


@pytest.mark.parametrize(("method", "rest", "body"), ROUTES)
def test_fr090_setup_sets_the_number_of_fields_instead(
    create: Callable[..., Json],
    send: Callable[..., tuple[int, Json]],
    read: Callable[..., Json],
    players: list[str],
    method: str,
    rest: str,
    body: Json | None,
) -> None:
    setup = create(players[:2])
    tournament = read({"id": setup["tournament_id"]})
    rest, body = _fill_in(rest, body, tournament)

    status, response = send(method, tournament, rest, body)

    assert status == 409
    assert response == {
        "code": "tournament_not_in_progress",
        "detail": {"state": "setup"},
    }


# ---------------------------------------------------------------- reads


def test_fr070_the_public_read_shows_the_fields_placed_by_hand(
    start: Callable[..., Json],
    place: Callable[..., tuple[int, Json]],
    client: TestClient,
    league: League,
    players: list[str],
) -> None:
    tournament = start(players)
    first, second, _ = round_matches(tournament, 1)
    _, swapped = place(
        tournament, (first, field_id(tournament, 2)), (second, field_id(tournament, 1))
    )

    response = client.get(
        f"/api/v1/public/{league.share_token}/tournaments/{tournament['id']}"
    )

    assert response.status_code == 200
    assert response.json()["fields"] == swapped["fields"]
    assert response.json()["waiting"] == swapped["waiting"]


# ---------------------------------------------------------------- authorization


@pytest.fixture
def other_league(league: League, make_league: Callable[..., League]) -> UUID:
    """A second league of the same organizer."""
    return make_league(owner_user_id=league.owner_user_id).id


@pytest.mark.parametrize(("method", "rest", "body"), ROUTES)
def test_owasp_api1_another_organizer_finds_neither_league_nor_tournament(
    start: Callable[..., Json],
    read: Callable[..., Json],
    client: TestClient,
    league_id: UUID,
    auth_header: Callable[..., dict[str, str]],
    make_user: Callable[..., User],
    players: list[str],
    method: str,
    rest: str,
    body: Json | None,
) -> None:
    tournament = start(players[:4], field_count=3)
    stranger = auth_header(make_user().id)
    rest, body = _fill_in(rest, body, tournament)

    response = client.request(
        method,
        _t_url(league_id, tournament["id"], rest),
        json=body,
        headers=stranger,
    )

    assert response.status_code == 404
    assert response.json() == {"code": "league_not_found", "detail": {}}
    assert read(tournament) == tournament


@pytest.mark.parametrize(("method", "rest", "body"), ROUTES)
def test_owasp_api1_a_tournament_of_another_league_is_not_found(
    start: Callable[..., Json],
    client: TestClient,
    headers: dict[str, str],
    other_league: UUID,
    players: list[str],
    method: str,
    rest: str,
    body: Json | None,
) -> None:
    tournament = start(players[:4], field_count=3)
    rest, body = _fill_in(rest, body, tournament)

    response = client.request(
        method, _t_url(other_league, tournament["id"], rest), json=body, headers=headers
    )

    assert response.status_code == 404
    assert response.json() == {"code": "tournament_not_found", "detail": {}}


@pytest.mark.parametrize(("method", "rest", "body"), ROUTES)
def test_owasp_api1_an_unknown_tournament_is_not_found(
    client: TestClient,
    headers: dict[str, str],
    league_id: UUID,
    method: str,
    rest: str,
    body: Json | None,
) -> None:
    rest, body = _fill_in(rest, body, {})

    response = client.request(
        method, _t_url(league_id, str(uuid7()), rest), json=body, headers=headers
    )

    assert response.status_code == 404
    assert response.json() == {"code": "tournament_not_found", "detail": {}}


# ---------------------------------------------------------------- races


type Ids = tuple[UUID, UUID, UUID]

_WIN = tournament_service.MatchResult(
    walkover_winner=None, games=(Game(winner=Outcome.SIDE_1, score_1=10, score_2=7),)
)


def _commit_started(
    engine: Engine, now: datetime, *, player_count: int, field_count: int
) -> Ids:
    """A committed league with a started round robin; its owner, league and tournament."""
    with Session(engine) as setup:
        owner = User(
            email="fields@example.test",
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
            for n in range(player_count)
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
                field_count=field_count,
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
        counter = tournament_service.set_seeding_method(
            setup,
            league_id=league.id,
            tournament_id=tournament_id,
            user_id=owner.id,
            method=SeedingMethod.RANDOM,
            clock=lambda: now,
        ).draw_counter
        tournament_service.start_tournament(
            setup,
            league_id=league.id,
            tournament_id=tournament_id,
            user_id=owner.id,
            expected_draw_counter=counter,
            clock=lambda: now,
        )
        setup.commit()
        return owner.id, league.id, tournament_id


def _view(engine: Engine, ids: Ids) -> tournament_service.TournamentView:
    owner_id, league_id, tournament_id = ids
    with Session(engine) as check:
        return tournament_service.read_tournament(
            check, league_id=league_id, tournament_id=tournament_id, user_id=owner_id
        )


def _assert_consistent(engine: Engine, ids: Ids) -> tournament_service.TournamentView:
    """BR-131 and BR-132 after a race: one match per field, nobody on two fields."""
    view = _view(engine, ids)
    players = {
        m.id: [p for side in m.sides for p in side.player_ids]
        for r in view.rounds
        for m in r.matches
    }
    on = [f.match_id for f in view.fields if f.match_id is not None]
    seen = [p for match_id in on for p in players[match_id]]
    assert len(on) == len(set(on))
    assert len(seen) == len(set(seen))
    with Session(engine) as check:
        requeued_on_a_field = check.scalars(
            select(Match.id).where(Match.id.in_(on), Match.requeued_at.is_not(None))
        ).all()
    assert requeued_on_a_field == []
    return view


def _match_ids(view: tournament_service.TournamentView, round_no: int) -> list[UUID]:
    (round_,) = [r for r in view.rounds if r.round_no == round_no]
    return [m.id for m in sorted(round_.matches, key=lambda m: m.position)]


def _field(view: tournament_service.TournamentView, number: int) -> UUID:
    (field,) = [f for f in view.fields if f.number == number]
    return field.id


def _race(
    settings: Settings,
    engine: Engine,
    ids: Ids,
    first: Callable[[Session], object],
    second: Callable[[TestClient, dict[str, str]], tuple[int, Json]],
    headers: Callable[..., dict[str, str]],
    wait: Callable[[], None],
) -> tuple[int, Json]:
    """Run `first` in a transaction while `second` waits for its lock, then commit."""
    outcome: list[tuple[int, Json]] = []
    with Session(engine) as session, TestClient(create_app(settings)) as client:
        first(session)

        def racing() -> None:
            outcome.append(second(client, headers(ids[0], issued_at=datetime.now(UTC))))

        thread = threading.Thread(target=racing)
        thread.start()
        wait()  # it waits for the league lock the first one holds
        session.commit()
        thread.join()
    (result,) = outcome
    return result


def _placements_body(*triples: tuple[UUID, UUID | None, UUID | None]) -> Json:
    """Placements as (match, new field, field the screen saw it on)."""
    return {
        "placements": [
            {
                "match_id": str(m),
                "field_id": None if f is None else str(f),
                "from_field_id": None if seen is None else str(seen),
            }
            for m, f, seen in triples
        ]
    }


def _place_in(
    session: Session,
    ids: Ids,
    now: datetime,
    *triples: tuple[UUID, UUID | None, UUID | None],
) -> None:
    owner_id, league_id, tournament_id = ids
    tournament_service.place_matches(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        user_id=owner_id,
        placements=[
            tournament_service.FieldPlacement(
                match_id=m, field_id=f, from_field_id=seen
            )
            for m, f, seen in triples
        ],
        clock=lambda: now,
    )


def _result_in(session: Session, ids: Ids, now: datetime, match_id: UUID) -> None:
    owner_id, league_id, tournament_id = ids
    tournament_service.set_match_result(
        session,
        league_id=league_id,
        tournament_id=tournament_id,
        match_id=match_id,
        user_id=owner_id,
        result=_WIN,
        clock=lambda: now,
    )


def _t(ids: Ids, rest: str) -> str:
    return _t_url(ids[1], str(ids[2]), rest)


@pytest.mark.concurrency
def test_adr008_two_moves_to_one_free_field_at_once_place_one_match(
    committing_settings: Settings,
    committing_engine: Engine,
    now: datetime,
    committed_auth_header: Callable[..., dict[str, str]],
    wait_for_a_lock_wait: Callable[[], None],
) -> None:
    ids = _commit_started(committing_engine, now, player_count=4, field_count=3)
    started = _view(committing_engine, ids)
    first, second = _match_ids(started, 1)
    free = _field(started, 3)

    status, body = _race(
        committing_settings,
        committing_engine,
        ids,
        lambda session: _place_in(session, ids, now, (first, free, _field(started, 1))),
        lambda client, headers: _response(
            client.put(
                _t(ids, "/fields/placements"),
                json=_placements_body((second, free, _field(started, 2))),
                headers=headers,
            )
        ),
        committed_auth_header,
        wait_for_a_lock_wait,
    )

    assert status == 409
    assert body["code"] == "field_not_free"
    after = _assert_consistent(committing_engine, ids)
    assert {f.number: f.match_id for f in after.fields}[3] == first


def _response(response: httpx2.Response) -> tuple[int, Json]:
    body: Json = response.json() if response.content else {}
    return response.status_code, body


@pytest.mark.concurrency
@pytest.mark.parametrize(
    "result_first", [True, False], ids=["result-first", "move-first"]
)
def test_adr008_a_move_racing_a_result_ends_in_one_consistent_state(
    committing_settings: Settings,
    committing_engine: Engine,
    now: datetime,
    committed_auth_header: Callable[..., dict[str, str]],
    wait_for_a_lock_wait: Callable[[], None],
    result_first: bool,
) -> None:
    ids = _commit_started(committing_engine, now, player_count=4, field_count=3)
    started = _view(committing_engine, ids)
    first, _ = _match_ids(started, 1)
    free = _field(started, 3)

    if result_first:
        status, body = _race(
            committing_settings,
            committing_engine,
            ids,
            lambda session: _result_in(session, ids, now, first),
            lambda client, headers: _response(
                client.put(
                    _t(ids, "/fields/placements"),
                    json=_placements_body((first, free, _field(started, 1))),
                    headers=headers,
                )
            ),
            committed_auth_header,
            wait_for_a_lock_wait,
        )
        # The move saw the result: the screen that sent it is stale.
        assert (status, body["code"]) == (409, "match_has_result")
    else:
        status, body = _race(
            committing_settings,
            committing_engine,
            ids,
            lambda session: _place_in(
                session, ids, now, (first, free, _field(started, 1))
            ),
            lambda client, headers: _response(
                client.put(
                    _t(ids, f"/matches/{first}/result"), json=S1_WINS, headers=headers
                )
            ),
            committed_auth_header,
            wait_for_a_lock_wait,
        )
        # The result freed the field the match had moved to.
        assert (status, body["id"]) == (200, str(first))

    after = _assert_consistent(committing_engine, ids)
    assert first not in [f.match_id for f in after.fields]
    assert first not in after.waiting


@pytest.mark.concurrency
@pytest.mark.parametrize(
    "remove_first", [True, False], ids=["remove-first", "result-first"]
)
def test_br132_removing_a_field_racing_its_result_ends_consistent(
    committing_settings: Settings,
    committing_engine: Engine,
    now: datetime,
    committed_auth_header: Callable[..., dict[str, str]],
    wait_for_a_lock_wait: Callable[[], None],
    remove_first: bool,
) -> None:
    ids = _commit_started(committing_engine, now, player_count=6, field_count=2)
    started = _view(committing_engine, ids)
    first, second, _ = _match_ids(started, 1)
    field_1 = _field(started, 1)
    owner_id, league_id, tournament_id = ids

    def remove(session: Session) -> None:
        tournament_service.remove_field(
            session,
            league_id=league_id,
            tournament_id=tournament_id,
            field_id=field_1,
            user_id=owner_id,
            clock=lambda: now,
        )

    if remove_first:
        status, body = _race(
            committing_settings,
            committing_engine,
            ids,
            remove,
            lambda client, headers: _response(
                client.put(
                    _t(ids, f"/matches/{first}/result"), json=S1_WINS, headers=headers
                )
            ),
            committed_auth_header,
            wait_for_a_lock_wait,
        )
        # The requeued match got its result: it no longer waits (FR-094).
        assert (status, body["id"]) == (200, str(first))
    else:
        status, body = _race(
            committing_settings,
            committing_engine,
            ids,
            lambda session: _result_in(session, ids, now, first),
            lambda client, headers: _response(
                client.delete(_t(ids, f"/fields/{field_1}"), headers=headers)
            ),
            committed_auth_header,
            wait_for_a_lock_wait,
        )
        assert status == 204

    after = _assert_consistent(committing_engine, ids)
    assert [f.number for f in after.fields] == [2]
    assert {f.match_id for f in after.fields} == {second}
    assert first not in after.waiting
    with Session(committing_engine) as check:
        assert check.scalar(select(Match.requeued_at).where(Match.id == first)) is None


_CLEAR = tournament_service.MatchResult(walkover_winner=None, games=())


@pytest.mark.concurrency
def test_br132_two_adds_at_once_give_distinct_numbers(
    committing_settings: Settings,
    committing_engine: Engine,
    now: datetime,
    committed_auth_header: Callable[..., dict[str, str]],
    wait_for_a_lock_wait: Callable[[], None],
) -> None:
    ids = _commit_started(committing_engine, now, player_count=4, field_count=2)
    owner_id, league_id, tournament_id = ids

    def add(session: Session) -> None:
        tournament_service.add_field(
            session,
            league_id=league_id,
            tournament_id=tournament_id,
            user_id=owner_id,
            number=3,
            clock=lambda: now,
        )

    status, body = _race(
        committing_settings,
        committing_engine,
        ids,
        add,
        lambda client, headers: _response(
            client.post(_t(ids, "/fields"), json={"number": 3}, headers=headers)
        ),
        committed_auth_header,
        wait_for_a_lock_wait,
    )

    # The second add expected Field 3 too: it gets the number that is next now.
    assert (status, body["code"], body["detail"]) == (
        409,
        "field_number_changed",
        {"number": 4},
    )
    after = _assert_consistent(committing_engine, ids)
    assert sorted(f.number for f in after.fields) == [1, 2, 3]


@pytest.mark.concurrency
@pytest.mark.parametrize(
    "clear_first", [True, False], ids=["clear-first", "move-first"]
)
def test_fr094_clearing_a_result_while_a_move_runs_ends_consistent(
    committing_settings: Settings,
    committing_engine: Engine,
    now: datetime,
    committed_auth_header: Callable[..., dict[str, str]],
    wait_for_a_lock_wait: Callable[[], None],
    clear_first: bool,
) -> None:
    ids = _commit_started(committing_engine, now, player_count=4, field_count=3)
    started = _view(committing_engine, ids)
    first, second = _match_ids(started, 1)
    field_2, field_3 = _field(started, 2), _field(started, 3)
    with Session(committing_engine) as setup:
        _result_in(setup, ids, now, first)
        setup.commit()
    move = (second, field_3, field_2)

    if clear_first:
        status, body = _race(
            committing_settings,
            committing_engine,
            ids,
            lambda session: tournament_service.set_match_result(
                session,
                league_id=ids[1],
                tournament_id=ids[2],
                match_id=first,
                user_id=ids[0],
                result=_CLEAR,
                clock=lambda: now,
            ),
            lambda client, headers: _response(
                client.put(
                    _t(ids, "/fields/placements"),
                    json=_placements_body(move),
                    headers=headers,
                )
            ),
            committed_auth_header,
            wait_for_a_lock_wait,
        )
        assert status == 200, body
    else:
        status, body = _race(
            committing_settings,
            committing_engine,
            ids,
            lambda session: _place_in(session, ids, now, move),
            lambda client, headers: _response(
                client.put(
                    _t(ids, f"/matches/{first}/result"),
                    json={"walkover_winner": None, "games": []},
                    headers=headers,
                )
            ),
            committed_auth_header,
            wait_for_a_lock_wait,
        )
        assert (status, body["id"]) == (200, str(first))

    after = _assert_consistent(committing_engine, ids)
    # The cleared match waits again and took the free Field 1; the move held.
    assert {f.number: f.match_id for f in after.fields} == {
        1: first,
        2: None,
        3: second,
    }


@pytest.mark.concurrency
@pytest.mark.parametrize("swap_first", [True, False], ids=["swap-first", "move-first"])
def test_adr008_a_swap_racing_a_move_of_one_of_its_matches_is_409(
    committing_settings: Settings,
    committing_engine: Engine,
    now: datetime,
    committed_auth_header: Callable[..., dict[str, str]],
    wait_for_a_lock_wait: Callable[[], None],
    swap_first: bool,
) -> None:
    ids = _commit_started(committing_engine, now, player_count=4, field_count=3)
    started = _view(committing_engine, ids)
    first, second = _match_ids(started, 1)
    field_1, field_2, field_3 = (_field(started, n) for n in (1, 2, 3))
    swap = ((first, field_2, field_1), (second, field_1, field_2))
    move = (first, field_3, field_1)

    if swap_first:
        status, body = _race(
            committing_settings,
            committing_engine,
            ids,
            lambda session: _place_in(session, ids, now, *swap),
            lambda client, headers: _response(
                client.put(
                    _t(ids, "/fields/placements"),
                    json=_placements_body(move),
                    headers=headers,
                )
            ),
            committed_auth_header,
            wait_for_a_lock_wait,
        )
        expected = {1: second, 2: first, 3: None}
    else:
        status, body = _race(
            committing_settings,
            committing_engine,
            ids,
            lambda session: _place_in(session, ids, now, move),
            lambda client, headers: _response(
                client.put(
                    _t(ids, "/fields/placements"),
                    json=_placements_body(*swap),
                    headers=headers,
                )
            ),
            committed_auth_header,
            wait_for_a_lock_wait,
        )
        expected = {1: None, 2: second, 3: first}

    # The second request comes from a screen that saw the first match elsewhere.
    assert (status, body["code"]) == (409, "placement_changed")
    after = _assert_consistent(committing_engine, ids)
    assert {f.number: f.match_id for f in after.fields} == expected
