"""Replacements in a Lord have mercy knockout through the API (#63, step 2).

A player who left is disabled through the participants route; the organizer's
rounds view previews the next draw's replacements, the draw stores them and
marks them on the sides, deleting the round undoes them, and a replaced player
is placed by the seat they took (FR-044, FR-049, BR-147 to BR-149, BR-151,
BR-153 to BR-155).

The knockout here has 4 pairs without a third-place match: round 1 is the
semifinals, and their losers are the candidates for the final (BR-148).
"""

from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid7

import pytest
from fastapi.testclient import TestClient

from tourneyhub.db.models.leagues import League, Player
from tourneyhub.engine.tournaments import MonsterKnockoutMode

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


def _t_url(league_id: UUID, tournament_id: str, rest: str = "") -> str:
    return f"/api/v1/leagues/{league_id}/tournaments/{tournament_id}{rest}"


def _public(league: League, tournament_id: str, rest: str = "") -> str:
    return f"/api/v1/public/{league.share_token}/tournaments/{tournament_id}{rest}"


def _win(side: str, score: tuple[int, int] = (10, 5)) -> Json:
    """A BO1 result with a score, which a Monster DYP requires (BR-092)."""
    winner, loser = score
    scores = (winner, loser) if side == "side_1" else (loser, winner)
    return {
        "walkover_winner": None,
        "games": [{"winner": side, "score_1": scores[0], "score_2": scores[1]}],
    }


@pytest.fixture
def league(make_league: Callable[..., League]) -> League:
    return make_league()


@pytest.fixture
def headers(
    league: League, auth_header: Callable[..., dict[str, str]]
) -> dict[str, str]:
    return auth_header(league.owner_user_id)


class Knockout:
    """A Lord have mercy knockout of 4 pairs, its round 1 played, side 1 winning."""

    def __init__(
        self,
        client: TestClient,
        league: League,
        headers: dict[str, str],
        players: list[Player],
    ) -> None:
        self.client = client
        self.league = league
        self.headers = headers
        self.id = ""
        self.id = self._start_monster([str(player.id) for player in players])
        self._start_knockout()
        for match in self.view()["rounds"][0]["matches"]:
            self.result(match["match_id"], _win("side_1"))

    def url(self, rest: str = "") -> str:
        return _t_url(self.league.id, self.id, rest)

    def get(self, rest: str) -> Json:
        response = self.client.get(self.url(rest), headers=self.headers)
        assert response.status_code == 200, response.text
        body: Json = response.json()
        return body

    def _start_monster(self, players: list[str]) -> str:
        created = self.client.post(
            f"/api/v1/leagues/{self.league.id}/tournaments",
            json={"id": str(uuid7()), **MONSTER_DYP},
            headers=self.headers,
        )
        assert created.status_code == 201, created.text
        self.id = created.json()["tournament_id"]
        picked = self.client.put(
            self.url("/setup/players"),
            json={"player_ids": players},
            headers=self.headers,
        )
        assert picked.status_code == 200, picked.text
        preview = self.get("/setup/preview")
        started = self.client.post(
            self.url("/start"),
            json={
                "expected_draw_counter": preview["draw_counter"],
                "expected_seed_order": preview["seed_order"],
            },
            headers=self.headers,
        )
        assert started.status_code == 200, started.text
        [round_] = started.json()["rounds"]
        for index, match in enumerate(round_["matches"]):
            self.result(match["id"], _win("side_1", (10, 1 + index)))
        return str(self.id)

    def _start_knockout(self) -> None:
        tournament = self.get("")
        shown = self.get(
            f"/knockout/preview?qualifiers=8&third_place_match=false&mode={MODE}"
        )
        response = self.client.put(
            self.url("/knockout"),
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
            headers=self.headers,
        )
        assert response.status_code == 200, response.text

    def result(self, match_id: str, body: Json) -> None:
        response = self.client.put(
            self.url(f"/matches/{match_id}/result"), json=body, headers=self.headers
        )
        assert response.status_code == 200, response.text

    def view(self) -> Json:
        return self.get("/knockout/rounds")

    def players(self) -> list[Json]:
        players: list[Json] = self.view()["players"]
        return players

    def player(self, player_id: str) -> Json:
        return next(p for p in self.players() if p["player_id"] == player_id)

    def set_disabled(self, player_id: str, *, disabled: bool) -> None:
        response = self.client.put(
            self.url(f"/entries/{self.player(player_id)['entry_id']}/disabled"),
            json={"disabled": disabled},
            headers=self.headers,
        )
        assert response.status_code == 200, response.text

    def draw(self, round_no: int) -> Json:
        response = self.client.post(
            self.url("/knockout/rounds"),
            json={"expected_round_no": round_no},
            headers=self.headers,
        )
        assert response.status_code == 201, response.text
        body: Json = response.json()
        return body

    def delete_round(self, round_no: int) -> None:
        round_id = self.view()["rounds"][round_no - 1]["round_id"]
        response = self.client.delete(
            self.url(f"/knockout/rounds/{round_id}"), headers=self.headers
        )
        assert response.status_code == 204, response.text


@pytest.fixture
def knockout(
    client: TestClient,
    league: League,
    headers: dict[str, str],
    make_player: Callable[..., Player],
) -> Knockout:
    players = [make_player(league=league, name=f"P{n}") for n in range(1, 9)]
    return Knockout(client, league, headers, players)


def _with_status(knockout: Knockout, status: str) -> list[str]:
    """The players of that status, best group-phase standing first."""
    return [p["player_id"] for p in knockout.players() if p["status"] == status]


def _final(view: Json) -> Json:
    final: Json = view["rounds"][1]["matches"][0]
    return final


def _marks(match: Json) -> list[list[Json]]:
    return [side["replacements"] for side in match["sides"]]


def _players(match: Json) -> set[str]:
    return {p for side in match["sides"] for p in side["player_ids"]}


def test_fr049_br148_the_preview_names_the_best_placed_replacement(
    knockout: Knockout,
) -> None:
    leaving = _with_status(knockout, "still_in")[0]
    best_loser = _with_status(knockout, "knocked_out")[0]
    knockout.set_disabled(leaving, disabled=True)

    view = knockout.view()

    assert view["next_draw"] == {
        "replacements": [{"player_id": best_loser, "replaced_player_id": leaving}],
        "staying_player_ids": [],
    }
    assert view["left_player_ids"] == [leaving]
    assert knockout.player(leaving) | {"entry_id": None} == {
        "player_id": leaving,
        "entry_id": None,
        "status": "still_in",
        "is_disabled": True,
    }


def test_fr049_the_knockout_players_and_their_status(knockout: Knockout) -> None:
    players = knockout.players()

    assert len(players) == 8
    assert (
        sorted(p["status"] for p in players) == ["knocked_out"] * 4 + ["still_in"] * 4
    )
    assert not any(p["is_disabled"] for p in players)
    assert knockout.view()["next_draw"] == {
        "replacements": [],
        "staying_player_ids": [],
    }


def test_br149_fr049_with_nobody_available_the_preview_keeps_the_player(
    knockout: Knockout,
) -> None:
    leaving = _with_status(knockout, "still_in")[0]
    for player_id in [leaving, *_with_status(knockout, "knocked_out")]:
        knockout.set_disabled(player_id, disabled=True)

    view = knockout.view()

    assert view["next_draw"] == {
        "replacements": [],
        "staying_player_ids": [leaving],
    }


def test_br148_br155_the_draw_brings_the_replacement_in_and_marks_it(
    knockout: Knockout,
) -> None:
    leaving = _with_status(knockout, "still_in")[0]
    knockout.set_disabled(leaving, disabled=True)
    preview = knockout.view()["next_draw"]
    [planned] = preview["replacements"]

    drawn = knockout.draw(2)

    final = _final(drawn)
    assert planned["player_id"] in _players(final)
    assert leaving not in _players(final)
    assert sorted(_marks(final), key=len) == [[], [planned]]
    assert drawn["next_draw"] is None
    assert drawn["left_player_ids"] == []
    assert knockout.player(leaving)["status"] == "replaced"
    assert knockout.player(planned["player_id"])["status"] == "still_in"


def test_br155_the_share_link_marks_the_replacement(
    knockout: Knockout, client: TestClient, league: League
) -> None:
    leaving = _with_status(knockout, "still_in")[0]
    knockout.set_disabled(leaving, disabled=True)
    drawn = knockout.draw(2)

    response = client.get(_public(league, knockout.id, "/knockout/rounds"))

    assert response.status_code == 200, response.text
    shown: Json = response.json()
    assert _marks(_final(shown)) == _marks(_final(drawn))
    assert "next_draw" not in shown
    assert "players" not in shown


def test_br153_re_enabling_a_replaced_player_changes_nothing(
    knockout: Knockout,
) -> None:
    leaving = _with_status(knockout, "still_in")[0]
    knockout.set_disabled(leaving, disabled=True)
    drawn = knockout.draw(2)

    knockout.set_disabled(leaving, disabled=False)

    view = knockout.view()
    assert _final(view)["sides"] == _final(drawn)["sides"]
    assert knockout.player(leaving) | {"entry_id": None} == {
        "player_id": leaving,
        "entry_id": None,
        "status": "replaced",
        "is_disabled": False,
    }


def test_br154_deleting_the_round_undoes_the_replacement(knockout: Knockout) -> None:
    leaving = _with_status(knockout, "still_in")[0]
    knockout.set_disabled(leaving, disabled=True)
    knockout.draw(2)
    knockout.set_disabled(leaving, disabled=False)

    knockout.delete_round(2)

    assert knockout.view()["next_draw"] == {
        "replacements": [],
        "staying_player_ids": [],
    }
    assert knockout.player(leaving)["status"] == "still_in"
    final = _final(knockout.draw(2))
    assert leaving in _players(final)
    assert _marks(final) == [[], []]


def test_br154_a_player_still_disabled_is_replaced_again(knockout: Knockout) -> None:
    leaving = _with_status(knockout, "still_in")[0]
    knockout.set_disabled(leaving, disabled=True)
    first = _final(knockout.draw(2))

    knockout.delete_round(2)
    again = _final(knockout.draw(2))

    assert again["sides"] == first["sides"]
    assert leaving not in _players(again)


def test_br151_br111_a_replaced_player_takes_the_seat_given_up(
    knockout: Knockout, client: TestClient, league: League
) -> None:
    leaving = _with_status(knockout, "still_in")[0]
    knockout.set_disabled(leaving, disabled=True)
    [planned] = knockout.view()["next_draw"]["replacements"]
    came_in = planned["player_id"]
    semifinal = next(
        m
        for m in knockout.view()["rounds"][0]["matches"]
        if came_in in m["sides"][1]["player_ids"]
    )
    [seat_partner] = [p for p in semifinal["sides"][1]["player_ids"] if p != came_in]
    final = _final(knockout.draw(2))

    knockout.result(final["match_id"], _win("side_1"))

    assert knockout.get("")["state"] == "finished"
    assert knockout.view()["next_draw"] is None
    places = knockout.get("/places")
    assert [row["place"] for row in places["rows"]] == [1, 1, 2, 2, 3, 3, 3, 3]
    entry_of = {p["player_id"]: p["entry_id"] for p in knockout.players()}
    by_entry = {row["entry_id"]: row for row in places["rows"]}
    replaced = by_entry[entry_of[leaving]]
    assert (replaced["place"], replaced["reason"]) == (
        3,
        replaced["reason"] | {"kind": "replaced", "round": "semifinal", "score": None},
    )
    assert replaced["reason"]["partner_entry_id"] == entry_of[seat_partner]
    assert (
        by_entry[entry_of[seat_partner]]["reason"]["partner_entry_id"]
        == (entry_of[leaving])
    )
    assert by_entry[entry_of[came_in]]["reason"]["kind"] in {"won_final", "lost_final"}
    assert (
        replaced["points_per_player"]
        == (by_entry[entry_of[seat_partner]]["points_per_player"])
    )
    public = client.get(_public(league, knockout.id, "/places"))
    assert public.status_code == 200, public.text
    assert {row["entry_id"]: row["reason"]["kind"] for row in public.json()["rows"]}[
        entry_of[leaving]
    ] == "replaced"
