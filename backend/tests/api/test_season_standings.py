"""Season standings, the tournament's season effect and the share link's reads.

FR-060, FR-061, FR-070, BR-002, BR-110 to BR-113.
"""

from collections import Counter
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid7

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tourneyhub.db.models.leagues import League, Player
from tourneyhub.db.models.tournaments import Tournament
from tourneyhub.engine.lots import lot_digest

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
    "field_count": 1,
}
S1_WINS: Json = {
    "walkover_winner": None,
    "games": [{"winner": "side_1", "score_1": 10, "score_2": 7}],
}
DRAW: Json = {
    "walkover_winner": None,
    "games": [{"winner": "draw", "score_1": None, "score_2": None}],
}


def _seed_order(setup: Json) -> list[str]:
    """The entries of a setup in seed order, as the review's start carries them."""
    return [e["id"] for e in sorted(setup["entries"], key=lambda e: e["seed"] or 0)]


class Evening:
    """One league with its organizer, and the calls an evening needs."""

    def __init__(
        self,
        client: TestClient,
        league: League,
        headers: dict[str, str],
        players: list[Player],
    ) -> None:
        self.client = client
        self.league_id = league.id
        self.token = league.share_token
        self.season_id = str(league.seasons[0].id)
        self.headers = headers
        self.players = [str(p.id) for p in players]

    def url(self, rest: str = "") -> str:
        return f"/api/v1/leagues/{self.league_id}{rest}"

    def public(self, rest: str = "") -> str:
        return f"/api/v1/public/{self.token}{rest}"

    def get(self, rest: str) -> Json | list[Json]:
        response = self.client.get(self.url(rest), headers=self.headers)
        assert response.status_code == 200, response.text
        body: Json | list[Json] = response.json()
        return body

    def create(self, player_ids: list[str], **values: object) -> Json:
        """A tournament in setup with these players picked."""
        base = self.url("/tournaments")
        body = {"id": str(uuid7()), **ROUND_ROBIN, **values}
        created = self.client.post(base, json=body, headers=self.headers)
        assert created.status_code == 201, created.text
        tournament_id = created.json()["tournament_id"]
        picked = self.client.put(
            f"{base}/{tournament_id}/setup/players",
            json={"player_ids": player_ids},
            headers=self.headers,
        )
        assert picked.status_code == 200, picked.text
        setup: Json = picked.json()
        return setup

    def start(self, player_ids: list[str], **values: object) -> Json:
        setup = self.create(player_ids, **values)
        started = self.client.post(
            self.url(f"/tournaments/{setup['tournament_id']}/start"),
            json={
                "expected_draw_counter": setup["draw_counter"],
                "expected_seed_order": _seed_order(setup),
            },
            headers=self.headers,
        )
        assert started.status_code == 200, started.text
        tournament: Json = started.json()
        return tournament

    def play(self, tournament: Json, body: Json = S1_WINS, *, matches: int = 0) -> None:
        """Enter `body` as the result of the matches, all of them by default."""
        every = [m for r in tournament["rounds"] for m in r["matches"]]
        for match in every[: matches or len(every)]:
            response = self.client.put(
                self.url(
                    f"/tournaments/{tournament['id']}/matches/{match['id']}/result"
                ),
                json=body,
                headers=self.headers,
            )
            assert response.status_code == 200, response.text

    def finish(self, tournament: Json) -> None:
        response = self.client.post(
            self.url(f"/tournaments/{tournament['id']}/finish"),
            json={"expected_state": "in_progress"},
            headers=self.headers,
        )
        assert response.status_code == 200, response.text

    def finished(
        self, player_ids: list[str], body: Json = S1_WINS, **values: object
    ) -> Json:
        tournament = self.start(player_ids, **values)
        self.play(tournament, body)
        self.finish(tournament)
        return tournament

    def play_by_seed(self, tournament: Json) -> None:
        """Every match of a round robin goes to the side with the better seed."""
        seed = {e["id"]: e["seed"] for e in tournament["entries"]}
        every = [m for r in tournament["rounds"] for m in r["matches"]]
        for match in every:
            one, two = (side["entry_id"] for side in match["sides"])
            body = {
                "walkover_winner": None,
                "games": [
                    {
                        "winner": "side_1" if seed[one] < seed[two] else "side_2",
                        "score_1": 10 if seed[one] < seed[two] else 7,
                        "score_2": 7 if seed[one] < seed[two] else 10,
                    }
                ],
            }
            self.put_result(tournament["id"], match["id"], body)

    def put_result(self, tournament_id: str, match_id: str, body: Json) -> None:
        response = self.client.put(
            self.url(f"/tournaments/{tournament_id}/matches/{match_id}/result"),
            json=body,
            headers=self.headers,
        )
        assert response.status_code == 200, response.text

    def knockout_after_round_robin(
        self, player_ids: list[str], *, qualifiers: int, **values: object
    ) -> Json:
        """A round robin of these players and a knockout of the top `qualifiers`.

        The better seed wins every group match, and side 1 every knockout match,
        until the last one finishes the tournament by itself (FR-037).
        """
        tournament = self.start(player_ids, **values)
        self.play_by_seed(tournament)
        tournament_id = tournament["id"]
        group_done = self.get(f"/tournaments/{tournament_id}")
        assert isinstance(group_done, dict)
        query = f"qualifiers={qualifiers}&third_place_match=false"
        shown = self.get(f"/tournaments/{tournament_id}/knockout/preview?{query}")
        assert isinstance(shown, dict)
        drawn = self.client.put(
            self.url(f"/tournaments/{tournament_id}/knockout"),
            json={
                "expected_current_phase_id": group_done["current_phase_id"],
                "expected_qualifier_ids": [
                    e["members"][0]["entry_id"] for e in shown["entries"]
                ],
                "qualifiers": qualifiers,
                "third_place_match": False,
                "match_format": None,
                "final_match_format": None,
                "mode": None,
            },
            headers=self.headers,
        )
        assert drawn.status_code == 200, drawn.text
        while True:
            bracket = self.get(f"/tournaments/{tournament_id}/bracket")
            assert isinstance(bracket, dict)
            ready = [
                m
                for round_ in bracket["rounds"]
                for m in round_["matches"]
                if m["state"] in ("ready", "on_field")
            ]
            if not ready:
                break
            match = ready[0]
            sides = [side["entry_id"] for side in match["sides"]]
            self.put_result(
                tournament_id, match["match_id"], {**S1_WINS, "expected_sides": sides}
            )
        done = self.get(f"/tournaments/{tournament_id}")
        assert isinstance(done, dict)
        assert done["state"] == "finished"
        return done

    def places_of(self, tournament: Json) -> dict[str, int]:
        """The place each player took in a finished tournament."""
        places = self.get(f"/tournaments/{tournament['id']}/places")
        assert isinstance(places, dict)
        place_of = {r["entry_id"]: r["place"] for r in places["rows"]}
        read = self.get(f"/tournaments/{tournament['id']}")
        assert isinstance(read, dict)
        return {
            player: place_of[entry["id"]]
            for entry in read["entries"]
            if entry["id"] in place_of
            for player in entry["player_ids"]
        }

    def points_of(self, tournament: Json) -> dict[str, int]:
        """What each player earned in a finished tournament, from its places."""
        places = self.get(f"/tournaments/{tournament['id']}/places")
        assert isinstance(places, dict)
        per_entry = {r["entry_id"]: r["points_per_player"] for r in places["rows"]}
        read = self.get(f"/tournaments/{tournament['id']}")
        assert isinstance(read, dict)
        return {
            player: per_entry[entry["id"]]
            for entry in read["entries"]
            for player in entry["player_ids"]
        }

    def standings(self, season_id: str | None = None) -> list[Json]:
        rows = self.get(f"/seasons/{season_id or self.season_id}/standings")
        assert isinstance(rows, list)
        return rows


@pytest.fixture
def league(make_league: Callable[..., League]) -> League:
    return make_league(name="Thursday Foosball")


@pytest.fixture
def evening(
    client: TestClient,
    league: League,
    make_player: Callable[..., Player],
    auth_header: Callable[..., dict[str, str]],
) -> Evening:
    players = [make_player(league=league, name=f"P{n}") for n in range(1, 6)]
    return Evening(client, league, auth_header(league.owner_user_id), players)


@pytest.fixture
def six_evening(
    client: TestClient,
    league: League,
    make_player: Callable[..., Player],
    auth_header: Callable[..., dict[str, str]],
) -> Evening:
    players = [make_player(league=league, name=f"P{n}") for n in range(1, 7)]
    return Evening(client, league, auth_header(league.owner_user_id), players)


def _tuple(row: Json) -> tuple[int, str, int, int, int]:
    return (
        row["place"],
        row["player_id"],
        row["points"],
        row["tournaments_played"],
        row["tournament_wins"],
    )


def _start_season(evening: Evening) -> str:
    """Close the season and start the next one; its id."""
    started = evening.client.post(
        evening.url("/seasons"),
        json={"expected_current_number": 1},
        headers=evening.headers,
    )
    assert started.status_code == 201, started.text
    return str(started.json()["id"])


# ---------------------------------------------------------------- organizer


def test_fr061_an_empty_season_has_no_standings(evening: Evening) -> None:
    assert evening.standings() == []


def test_br112_the_standings_add_up_the_points_of_the_finished_tournaments(
    evening: Evening,
) -> None:
    everyone = evening.players
    first = evening.finished(everyone[:4])
    second = evening.finished(everyone[1:], name="Second")  # P1 sits this one out
    expected = Counter(evening.points_of(first)) + Counter(evening.points_of(second))

    rows = evening.standings()

    assert {r["player_id"]: r["points"] for r in rows} == {
        player: expected[player] for player in everyone
    } | {player: 0 for player in everyone if player not in expected}
    assert [r["tournaments_played"] for r in rows if r["player_id"] == everyone[0]] == [
        1
    ]
    assert [r["tournaments_played"] for r in rows if r["player_id"] == everyone[1]] == [
        2
    ]
    keys = [(-r["points"], -r["tournament_wins"]) for r in rows]
    assert keys == sorted(keys)  # BR-113
    winners = [
        player
        for tournament in (first, second)
        for player, points in evening.points_of(tournament).items()
        if points == 10
    ]
    assert Counter(winners) == {
        r["player_id"]: r["tournament_wins"] for r in rows if r["tournament_wins"]
    }


def test_br113_players_level_on_points_and_wins_share_the_place(
    evening: Evening, league: League, session: Session
) -> None:
    league.draws_allowed = True
    session.flush()
    evening.finished(evening.players[:3], DRAW)

    rows = evening.standings()

    # Three players level share 1st: (10 + 8 + 6) / 3 = 8 each, a win each.
    assert [(r["place"], r["points"], r["tournament_wins"]) for r in rows] == [
        (1, 8, 1)
    ] * 3
    assert [r["player_id"] for r in rows] == sorted(evening.players[:3])


def test_br112_a_tournament_still_playing_does_not_count(evening: Evening) -> None:
    finished = evening.finished(evening.players[:3])
    running = evening.start(evening.players[:3], name="Running")
    evening.play(running, matches=2)
    evening.create(evening.players[:3], name="In setup")

    rows = evening.standings()

    assert sum(r["points"] for r in rows) == sum(evening.points_of(finished).values())
    assert {r["tournaments_played"] for r in rows} == {1}


def test_br095_clearing_a_result_takes_the_tournament_out_of_the_standings(
    evening: Evening,
) -> None:
    tournament = evening.finished(evening.players[:3])
    match = tournament["rounds"][0]["matches"][0]

    cleared = evening.client.put(
        evening.url(f"/tournaments/{tournament['id']}/matches/{match['id']}/result"),
        json={"walkover_winner": None, "games": []},
        headers=evening.headers,
    )

    assert cleared.status_code == 200
    assert evening.standings() == []


def test_br112_deleting_a_tournament_recalculates_the_standings(
    evening: Evening,
) -> None:
    keep = evening.finished(evening.players[:3])
    drop = evening.finished(evening.players[:3], name="Dropped")
    assert evening.standings()[0]["tournaments_played"] == 2

    deleted = evening.client.delete(
        evening.url(f"/tournaments/{drop['id']}"), headers=evening.headers
    )

    assert deleted.status_code == 204
    rows = evening.standings()
    assert {r["tournaments_played"] for r in rows} == {1}
    assert {r["player_id"]: r["points"] for r in rows} == evening.points_of(keep)


def test_br012_a_new_table_changes_the_active_seasons_points(
    evening: Evening,
) -> None:
    evening.finished(evening.players[:3])

    table = evening.client.put(
        evening.url(f"/seasons/{evening.season_id}/placement-points"),
        json={"placement_points": [3, 2, 1]},
        headers=evening.headers,
    )

    assert table.status_code == 200
    assert sorted(r["points"] for r in evening.standings()) == [1, 2, 3]


def test_br011_a_closed_season_keeps_its_standings_and_its_table(
    evening: Evening,
) -> None:
    evening.finished(evening.players[:3])
    before = evening.standings()
    next_season = _start_season(evening)

    assert evening.standings() == before
    assert evening.standings(next_season) == []


def test_br002_a_removed_player_keeps_their_place_in_the_standings(
    evening: Evening,
) -> None:
    evening.finished(evening.players[:3])
    before = evening.standings()
    removed = evening.client.put(
        evening.url(f"/players/{evening.players[0]}/removed"),
        json={"removed": True},
        headers=evening.headers,
    )
    assert removed.status_code == 200, removed.text

    assert evening.standings() == before
    assert evening.players[0] in {r["player_id"] for r in before}


def test_adr008_a_season_of_another_league_is_not_found(
    evening: Evening, make_league: Callable[..., League]
) -> None:
    foreign = str(make_league().seasons[0].id)

    for season in (foreign, str(uuid7())):
        response = evening.client.get(
            evening.url(f"/seasons/{season}/standings"), headers=evening.headers
        )
        assert (response.status_code, response.json()) == (
            404,
            {"code": "season_not_found", "detail": {}},
        )


def test_owasp_api1_another_organizers_league_is_not_found(
    evening: Evening,
    make_league: Callable[..., League],
    auth_header: Callable[..., dict[str, str]],
) -> None:
    stranger = auth_header(make_league().owner_user_id)

    response = evening.client.get(
        evening.url(f"/seasons/{evening.season_id}/standings"), headers=stranger
    )

    assert response.status_code == 404
    assert response.json()["code"] == "league_not_found"


def test_the_standings_need_a_login(evening: Evening) -> None:
    response = evening.client.get(
        evening.url(f"/seasons/{evening.season_id}/standings")
    )

    assert response.status_code == 401


# ---------------------------------------------------------------- season effect


def test_br112_the_effect_compares_the_standings_with_and_without_the_tournament(
    evening: Evening,
) -> None:
    players = evening.players
    first = evening.finished(players[:3])
    second = evening.finished(players[2:], name="Second")  # P3 plays again
    before = evening.points_of(first)  # 10, 8, 6: three different places
    earned = evening.points_of(second)

    effect = evening.get(f"/tournaments/{second['id']}/season-effect")

    standings = evening.standings()
    assert isinstance(effect, list)
    assert [(e["player_id"], e["place"], e["points"]) for e in effect] == [
        (r["player_id"], r["place"], r["points"]) for r in standings
    ]
    assert {e["player_id"]: e["earned"] for e in effect} == {
        p: earned.get(p, 0) for p in players
    }
    assert {e["player_id"]: e["previous_place"] for e in effect} == {
        p: (1 + sum(before[o] > before[p] for o in before)) if p in before else None
        for p in players
    }


def test_br112_the_only_tournament_of_a_season_has_no_previous_places(
    evening: Evening,
) -> None:
    tournament = evening.finished(evening.players[:3])

    effect = evening.get(f"/tournaments/{tournament['id']}/season-effect")

    assert isinstance(effect, list)
    assert [(e["place"], e["earned"], e["previous_place"]) for e in effect] == [
        (1, 10, None),
        (2, 8, None),
        (3, 6, None),
    ]


def test_br112_a_tournament_not_finished_has_no_effect_yet(evening: Evening) -> None:
    running = evening.start(evening.players[:3])
    setup = evening.create(evening.players[:3], name="In setup")

    assert evening.get(f"/tournaments/{running['id']}/season-effect") == []
    assert evening.get(f"/tournaments/{setup['tournament_id']}/season-effect") == []


def test_adr008_the_effect_of_another_leagues_tournament_is_not_found(
    evening: Evening,
) -> None:
    response = evening.client.get(
        evening.url(f"/tournaments/{uuid7()}/season-effect"), headers=evening.headers
    )

    assert (response.status_code, response.json()) == (
        404,
        {"code": "tournament_not_found", "detail": {}},
    )


# ---------------------------------------------------------------- the share link

PUBLIC_STANDING_KEYS = {
    "place",
    "entry_id",
    "played",
    "won",
    "drawn",
    "lost",
    "sat_out",
    "points",
    "game_difference",
    "score_difference",
    "bh1",
    "bh2",
}
SEASON_STANDING_KEYS = {
    "place",
    "player_id",
    "points",
    "tournaments_played",
    "tournament_wins",
}


def test_fr070_the_season_standings_are_the_organizers(evening: Evening) -> None:
    evening.finished(evening.players[:3])
    evening.finished(evening.players[1:4], name="Second")

    response = evening.client.get(
        evening.public(f"/seasons/{evening.season_id}/standings")
    )

    assert response.status_code == 200
    assert response.json() == evening.standings()
    assert {frozenset(row) for row in response.json()} == {
        frozenset(SEASON_STANDING_KEYS)
    }


def test_fr070_a_season_of_another_league_is_not_found_through_the_link(
    evening: Evening, make_league: Callable[..., League]
) -> None:
    foreign = str(make_league().seasons[0].id)

    response = evening.client.get(evening.public(f"/seasons/{foreign}/standings"))

    assert (response.status_code, response.json()) == (
        404,
        {"code": "season_not_found", "detail": {}},
    )


def test_fr070_the_places_are_the_organizers_once_finished(evening: Evening) -> None:
    tournament = evening.start(evening.players[:3])
    path = f"/tournaments/{tournament['id']}/places"
    evening.play(tournament)

    running = evening.client.get(evening.public(path))
    evening.finish(tournament)
    finished = evening.client.get(evening.public(path))

    assert running.json() == {"complete": False, "rows": []}
    assert finished.status_code == 200
    assert finished.json() == evening.get(path)
    assert [r["points_per_player"] for r in finished.json()["rows"]] == [10, 8, 6]


def test_fr070_the_standings_are_those_of_the_play_read(evening: Evening) -> None:
    tournament = evening.start(evening.players[:3])
    evening.play(tournament, matches=2)

    response = evening.client.get(
        evening.public(f"/tournaments/{tournament['id']}/standings")
    )

    play = evening.get(f"/tournaments/{tournament['id']}/play")
    assert isinstance(play, dict)
    assert response.status_code == 200
    assert response.json() == [
        {k: row[k] for k in PUBLIC_STANDING_KEYS} for row in play["standings"]
    ]
    assert {frozenset(row) for row in response.json()} == {
        frozenset(PUBLIC_STANDING_KEYS)
    }


@pytest.mark.parametrize("rest", ["places", "standings"])
def test_fr070_a_tournament_in_setup_is_not_found_through_the_link(
    evening: Evening, rest: str
) -> None:
    setup = evening.create(evening.players[:3])

    in_setup = evening.client.get(
        evening.public(f"/tournaments/{setup['tournament_id']}/{rest}")
    )
    unknown = evening.client.get(evening.public(f"/tournaments/{uuid7()}/{rest}"))

    assert (in_setup.status_code, in_setup.json()) == (
        unknown.status_code,
        unknown.json(),
    )
    assert unknown.json() == {"code": "tournament_not_found", "detail": {}}


@pytest.mark.parametrize("rest", ["places", "standings"])
def test_owasp_api1_another_leagues_tournament_is_not_found_through_the_link(
    evening: Evening,
    make_league: Callable[..., League],
    make_player: Callable[..., Player],
    auth_header: Callable[..., dict[str, str]],
    rest: str,
) -> None:
    other = make_league()
    others = [make_player(league=other, name=f"O{n}") for n in range(3)]
    elsewhere = Evening(
        evening.client, other, auth_header(other.owner_user_id), others
    ).start([str(p.id) for p in others])

    response = evening.client.get(
        evening.public(f"/tournaments/{elsewhere['id']}/{rest}")
    )

    assert response.status_code == 404
    assert response.json()["code"] == "tournament_not_found"


def test_adr005_the_new_public_reads_are_never_cached_and_send_no_referrer(
    evening: Evening,
) -> None:
    tournament = evening.finished(evening.players[:3])
    paths = [
        f"/seasons/{evening.season_id}/standings",
        f"/tournaments/{tournament['id']}/standings",
        f"/tournaments/{tournament['id']}/places",
        f"/tournaments/{uuid7()}/places",  # an error answers the same
    ]

    for path in paths:
        response = evening.client.get(evening.public(path))
        assert response.headers["Cache-Control"] == "no-store", path
        assert response.headers["Referrer-Policy"] == "no-referrer", path


def test_fr072_the_new_public_reads_change_nothing(evening: Evening) -> None:
    for path in (
        f"/seasons/{evening.season_id}/standings",
        f"/tournaments/{uuid7()}/places",
    ):
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            response = evening.client.request(method, evening.public(path))
            assert response.status_code == 405, (method, path)


def test_a_season_id_that_is_not_a_uuid_is_a_validation_error(
    evening: Evening,
) -> None:
    response = evening.client.get(
        evening.url("/seasons/not-a-uuid/standings"), headers=evening.headers
    )

    assert response.status_code == 422


# ---------------------------------------------------------------- ranking


def test_br020_seeding_follows_the_earlier_tournaments_of_the_season(
    evening: Evening,
) -> None:
    evening.finished(evening.players[:3])
    points = {r["player_id"]: r["points"] for r in evening.standings()}

    setup = evening.create(evening.players)

    ranked = [row["player_id"] for row in setup["ranking"]]
    assert set(ranked[:3]) == set(evening.players[:3])  # those with points first
    assert [points.get(player, 0) for player in ranked] == sorted(
        (points.get(player, 0) for player in ranked), reverse=True
    )
    assert setup["player_ids"] == ranked  # BR-021: singles follow the ranking
    assert [e["player_ids"][0] for e in setup["entries"]] == ranked


def test_br020_last_seasons_places_rank_after_this_seasons_points(
    evening: Evening,
) -> None:
    evening.finished(evening.players[:2])
    last = [r["player_id"] for r in evening.standings()]  # 1st, 2nd
    assert [r["place"] for r in evening.standings()] == [1, 2]
    _start_season(evening)

    setup = evening.create(evening.players)

    ranked = [row["player_id"] for row in setup["ranking"]]
    assert ranked[:2] == last  # a place last season beats none

    evening.finished(evening.players[2:4], name="This season")

    setup = evening.create(evening.players, name="Next")
    ranked = [row["player_id"] for row in setup["ranking"]]
    assert set(ranked[:2]) == set(evening.players[2:4])  # points come first
    assert ranked[2:4] == last
    assert [e["player_ids"][0] for e in setup["entries"]] == ranked


def test_br020_a_started_tournament_does_not_rank_by_the_standings(
    evening: Evening,
) -> None:
    running = evening.start(evening.players)
    before = evening.get(f"/tournaments/{running['id']}/setup")
    evening.finished(evening.players[:3], name="Another")

    after = evening.get(f"/tournaments/{running['id']}/setup")

    assert isinstance(before, dict)
    assert isinstance(after, dict)
    assert after["ranking"] == before["ranking"]
    assert {row["points"] for row in after["ranking"]} == {0}


def test_br020_the_setup_ranking_shows_the_real_season_points(
    evening: Evening,
) -> None:
    finished = evening.finished(evening.players[:3])
    earned = evening.points_of(finished)

    setup = evening.create(evening.players)

    shown = {row["player_id"]: row["points"] for row in setup["ranking"]}
    assert shown == {p: earned.get(p, 0) for p in evening.players}
    assert any(shown.values())


def test_br020_equal_points_go_by_wins_then_lot(
    evening: Evening, league: League, session: Session
) -> None:
    p1, p2, p3, p4, p5 = evening.players
    league.draws_allowed = True
    session.flush()
    evening.finished([p3, p4, p5], DRAW, name="Level")  # 8 points and a win each
    evening.finished([p1, p2], name="Two")  # 10 points and a win; 8 and none
    winner, loser = (
        r["player_id"] for r in evening.standings() if r["player_id"] in (p1, p2)
    )
    rows = {r["player_id"]: r for r in evening.standings()}
    assert rows[loser]["points"] == rows[p3]["points"] == 8
    assert rows[loser]["tournament_wins"] == 0

    setup = evening.create(evening.players)
    stored = session.get_one(Tournament, UUID(setup["tournament_id"]))
    stored.rng_seed = bytes(range(16))
    session.flush()

    def ranked() -> list[str]:
        read = evening.get(f"/tournaments/{setup['tournament_id']}/setup")
        assert isinstance(read, dict)
        return [row["player_id"] for row in read["ranking"]]

    lot = sorted(
        (p3, p4, p5),
        key=lambda p: lot_digest(
            rng_seed=bytes(range(16)), purpose="league-ranking", candidate=UUID(p)
        ),
    )
    assert ranked() == [winner, *lot, loser]
    assert ranked() == ranked()


def test_br020_equal_points_and_wins_go_by_last_seasons_place_then_lot(
    evening: Evening, session: Session
) -> None:
    p1, p2, p3, p4, p5 = evening.players
    evening.finished([p2, p1])  # last season: one of them 1st, the other 2nd
    last = [r["player_id"] for r in evening.standings()]
    _start_season(evening)

    tournament = evening.create(evening.players)
    stored = session.get_one(Tournament, UUID(tournament["tournament_id"]))
    stored.rng_seed = bytes(range(16))
    session.flush()

    read = evening.get(f"/tournaments/{tournament['tournament_id']}/setup")
    assert isinstance(read, dict)
    lot = sorted(
        (p3, p4, p5),
        key=lambda p: lot_digest(
            rng_seed=bytes(range(16)),
            purpose="league-ranking",
            candidate=UUID(p),
        ),
    )
    assert [row["player_id"] for row in read["ranking"]] == [*last, *lot]


# ---------------------------------------------------------------- knockout


# The default table is 10, 8, 6, 4, 2; entries sharing a place get the average of
# the places they cover, rounded down, and a place beyond the table earns 0
# (BR-110, BR-111): 3rd and 4th share 3rd, 5th and 6th share 5th.
ROUND_ROBIN_POINTS = {1: 10, 2: 8, 3: 6}
KNOCKOUT_POINTS = {1: 10, 2: 8, 3: 5, 5: 1}


class Season:
    """A season with a round robin of three and a round robin plus knockout of six."""

    def __init__(self, evening: Evening) -> None:
        self.evening = evening
        self.players = evening.players
        self.round_robin = evening.finished(self.players[:3], name="Round robin only")
        self.knockout = evening.knockout_after_round_robin(
            self.players, qualifiers=6, name="With a knockout"
        )
        self.first = evening.places_of(self.round_robin)
        self.second = evening.places_of(self.knockout)

    def points(self) -> dict[str, int]:
        """What each player has in the season, from the places and the table."""
        return {
            player: ROUND_ROBIN_POINTS.get(self.first.get(player, 0), 0)
            + KNOCKOUT_POINTS[self.second[player]]
            for player in self.players
        }

    def wins(self) -> dict[str, int]:
        return {
            player: (self.first.get(player) == 1) + (self.second[player] == 1)
            for player in self.players
        }


@pytest.fixture
def season(six_evening: Evening) -> Season:
    return Season(six_evening)


def test_br102_br111_a_knockout_tournament_places_with_a_shared_fifth(
    season: Season,
) -> None:
    assert sorted(season.second.values()) == [1, 2, 3, 3, 5, 5]
    assert sorted(season.first.values()) == [1, 2, 3]


def test_br112_the_standings_add_up_a_round_robin_and_a_knockout_tournament(
    season: Season,
) -> None:
    expected = season.points()
    wins = season.wins()

    rows = season.evening.standings()

    assert {r["player_id"]: r["points"] for r in rows} == expected
    assert {r["player_id"]: r["tournament_wins"] for r in rows} == wins
    assert {r["player_id"]: r["tournaments_played"] for r in rows} == {
        player: 2 if player in season.first else 1 for player in season.players
    }
    # BR-113: by points, then wins, level players share the place
    keys = [(-expected[r["player_id"]], -wins[r["player_id"]]) for r in rows]
    assert keys == sorted(keys)
    assert [r["place"] for r in rows] == [
        1 + sum(other < key for other in keys) for key in keys
    ]
    assert max(expected.values()) == 20  # 10 + 10: 1st in both


def test_br112_the_knockout_tournament_has_its_effect_on_the_standings(
    season: Season,
) -> None:
    evening = season.evening
    before = {
        player: ROUND_ROBIN_POINTS[place] for player, place in season.first.items()
    }

    effect = evening.get(f"/tournaments/{season.knockout['id']}/season-effect")

    assert isinstance(effect, list)
    assert [(e["player_id"], e["place"], e["points"]) for e in effect] == [
        (r["player_id"], r["place"], r["points"]) for r in evening.standings()
    ]
    assert {e["player_id"]: e["earned"] for e in effect} == {
        player: KNOCKOUT_POINTS[place] for player, place in season.second.items()
    }
    assert {e["player_id"]: e["previous_place"] for e in effect} == {
        player: (1 + sum(before[o] > before[player] for o in before))
        if player in before
        else None
        for player in season.players
    }


def test_br112_the_round_robin_tournament_has_its_effect_beside_the_knockout(
    season: Season,
) -> None:
    effect = season.evening.get(
        f"/tournaments/{season.round_robin['id']}/season-effect"
    )

    assert isinstance(effect, list)
    assert {e["player_id"]: e["earned"] for e in effect} == {
        player: ROUND_ROBIN_POINTS[place] for player, place in season.first.items()
    } | {player: 0 for player in season.players if player not in season.first}


def test_fr070_the_public_season_standings_include_the_knockout_places(
    season: Season,
) -> None:
    evening = season.evening

    response = evening.client.get(
        evening.public(f"/seasons/{evening.season_id}/standings")
    )

    assert response.status_code == 200
    assert response.json() == evening.standings()
    assert {r["player_id"]: r["points"] for r in response.json()} == season.points()


def test_fr070_the_public_places_of_the_knockout_name_why(season: Season) -> None:
    evening = season.evening

    response = evening.client.get(
        evening.public(f"/tournaments/{season.knockout['id']}/places")
    )

    rows = response.json()["rows"]
    assert response.status_code == 200
    assert [(r["place"], r["reason"]["kind"]) for r in rows] == [
        (1, "won_final"),
        (2, "lost_final"),
        (3, "lost_in_round"),
        (3, "lost_in_round"),
        (5, "lost_in_round"),
        (5, "lost_in_round"),
    ]
    assert [r["reason"]["round"] for r in rows] == [
        "final",
        "final",
        "semifinal",
        "semifinal",
        "quarterfinal",
        "quarterfinal",
    ]
    assert [r["points_per_player"] for r in rows] == [10, 8, 5, 5, 1, 1]


def test_br020_the_setup_ranking_uses_the_knockout_tournaments_points_and_wins(
    season: Season,
) -> None:
    evening = season.evening
    expected = season.points()
    wins = season.wins()

    setup = evening.create(evening.players, name="Next")

    ranking = setup["ranking"]
    assert {row["player_id"]: row["points"] for row in ranking} == expected
    keys = [(-expected[row["player_id"]], -wins[row["player_id"]]) for row in ranking]
    assert keys == sorted(keys)  # BR-020: points, then tournament wins
    assert [row["rank"] for row in ranking] == list(range(1, 7))
