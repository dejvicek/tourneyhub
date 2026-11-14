"""Late players in a running Swiss or Monster DYP (FR-047, BR-067, BR-086, ADR-008)."""

from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import UUID, uuid7

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tourneyhub.db.models.leagues import League, Player, Season
from tourneyhub.db.models.matches import Round, RoundParticipation
from tourneyhub.db.models.tournaments import TournamentPhase
from tourneyhub.engine.leagues import SeasonState

type Json = dict[str, Any]

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


@pytest.fixture
def late(
    client: TestClient, league_id: UUID, headers: dict[str, str]
) -> Callable[..., tuple[int, Json]]:
    def late(
        tournament_id: str, player_id: str | UUID, from_round_no: int
    ) -> tuple[int, Json]:
        response = client.post(
            f"/api/v1/leagues/{league_id}/tournaments/{tournament_id}/entries",
            json={"player_id": str(player_id), "from_round_no": from_round_no},
            headers=headers,
        )
        result: Json = response.json()
        return response.status_code, result

    return late


def _entries(tournament: Json) -> list[Json]:
    return [e for e in tournament["entries"] if e["stage"] == "main"]


def _entry_of(tournament: Json, player_id: str) -> Json:
    [entry] = [e for e in _entries(tournament) if e["player_ids"] == [player_id]]
    return entry


def _round(tournament: Json, round_no: int) -> Json:
    [round_] = [r for r in tournament["rounds"] if r["round_no"] == round_no]
    found: Json = round_
    return found


def _in_play(round_: Json) -> set[str]:
    return {p for m in round_["matches"] for s in m["sides"] for p in s["player_ids"]}


def _standing(
    get: Callable[[str, str], Json], tournament_id: str, entry_id: str
) -> Json:
    [row] = [
        r for r in get(tournament_id, "/play")["standings"] if r["entry_id"] == entry_id
    ]
    found: Json = row
    return found


def _statuses(session: Session, tournament_id: str, entry_id: str) -> dict[int, str]:
    rows = session.execute(
        select(Round.round_no, RoundParticipation.status)
        .join(RoundParticipation, RoundParticipation.round_id == Round.id)
        .join(TournamentPhase, Round.phase_id == TournamentPhase.id)
        .where(
            TournamentPhase.tournament_id == UUID(tournament_id),
            RoundParticipation.entry_id == UUID(entry_id),
        )
    )
    return {round_no: status.value for round_no, status in rows}


def test_fr047_br067_a_swiss_late_player_joins_between_rounds_with_the_next_seed(
    create: Callable[..., str],
    start: Callable[[str], Json],
    play_round: Callable[[str, int], None],
    add_round: Callable[[str, int], Json],
    late: Callable[..., tuple[int, Json]],
    get: Callable[[str, str], Json],
    players: list[str],
    session: Session,
) -> None:
    tournament_id = create(6, sit_out_points=2)
    start(tournament_id)
    play_round(tournament_id, 1)
    add_round(tournament_id, 2)
    play_round(tournament_id, 2)

    status, body = late(tournament_id, players[6], 3)

    after = get(tournament_id, "")
    entry = _entry_of(after, players[6])
    assert status == 201, body
    assert body == {
        "entry_id": entry["id"],
        "state": "playing",
        "joined_round": 3,
        "disabled_since_round": None,
        "sat_out_round": None,
    }
    assert entry["seed"] == 7
    assert entry["is_top_player"] is False
    assert sorted(e["seed"] for e in _entries(after)) == list(range(1, 8))
    assert _statuses(session, tournament_id, entry["id"]) == {
        1: "not_joined",
        2: "not_joined",
    }


def test_br067_the_late_player_is_drawn_in_the_next_round_and_starts_on_0_points(
    create: Callable[..., str],
    start: Callable[[str], Json],
    play_round: Callable[[str, int], None],
    add_round: Callable[[str, int], Json],
    late: Callable[..., tuple[int, Json]],
    get: Callable[[str, str], Json],
    players: list[str],
    session: Session,
) -> None:
    tournament_id = create(6, sit_out_points=2)
    start(tournament_id)
    play_round(tournament_id, 1)
    add_round(tournament_id, 2)
    play_round(tournament_id, 2)
    _, body = late(tournament_id, players[6], 3)

    row = _standing(get, tournament_id, body["entry_id"])
    round_3 = add_round(tournament_id, 3)

    # Missed rounds earn nothing, not even sit-out points (BR-067).
    assert (row["points"], row["played"], row["sat_out"]) == (0, 0, 0)
    assert players[6] in _in_play(round_3)
    assert body["entry_id"] not in round_3["sitting_out"]
    assert _statuses(session, tournament_id, body["entry_id"])[3] == "played"


def test_br058_br067_missed_rounds_count_as_sit_outs_for_the_sit_out_order(
    create: Callable[..., str],
    start: Callable[[str], Json],
    play_round: Callable[[str, int], None],
    add_round: Callable[[str, int], Json],
    late: Callable[..., tuple[int, Json]],
    players: list[str],
) -> None:
    tournament_id = create(6)
    start(tournament_id)
    play_round(tournament_id, 1)
    add_round(tournament_id, 2)
    play_round(tournament_id, 2)
    _, first = late(tournament_id, players[6], 3)
    round_3 = add_round(tournament_id, 3)
    play_round(tournament_id, 3)

    # 7 entries: one sits out each round. The late player has the fewest
    # games behind them, but their 2 missed rounds count as sit-outs, so in
    # round 4 they are not the one who sits out (BR-058).
    round_4 = add_round(tournament_id, 4)

    assert len(round_3["sitting_out"]) == 1
    assert len(round_4["sitting_out"]) == 1
    assert first["entry_id"] not in round_4["sitting_out"]


def test_fr047_a_late_player_can_join_while_a_round_is_in_play(
    create: Callable[..., str],
    start: Callable[[str], Json],
    play_round: Callable[[str, int], None],
    add_round: Callable[[str, int], Json],
    late: Callable[..., tuple[int, Json]],
    participants: Callable[[str], list[Json]],
    players: list[str],
    session: Session,
) -> None:
    tournament_id = create(6)
    start(tournament_id)
    play_round(tournament_id, 1)
    add_round(tournament_id, 2)

    status, body = late(tournament_id, players[6], 3)

    assert (status, body["joined_round"]) == (201, 3)
    assert _statuses(session, tournament_id, body["entry_id"]) == {
        1: "not_joined",
        2: "not_joined",
    }
    play_round(tournament_id, 2)
    round_3 = add_round(tournament_id, 3)
    assert players[6] in _in_play(round_3)
    shown = {p["entry_id"]: p for p in participants(tournament_id)}
    assert shown[body["entry_id"]]["joined_round"] == 3


def test_fr047_br063_a_monster_dyp_late_player_has_no_seed_and_is_drawn_next_round(
    create: Callable[..., str],
    start: Callable[[str], Json],
    play_round: Callable[[str, int], None],
    add_round: Callable[[str, int], Json],
    late: Callable[..., tuple[int, Json]],
    get: Callable[[str, str], Json],
    players: list[str],
    session: Session,
) -> None:
    tournament_id = create(7, **MONSTER)
    start(tournament_id)
    play_round(tournament_id, 1)

    status, body = late(tournament_id, players[7], 2)

    entry = _entry_of(get(tournament_id, ""), players[7])
    assert (status, body["joined_round"]) == (201, 2)
    assert entry["seed"] is None
    assert _statuses(session, tournament_id, entry["id"]) == {1: "not_joined"}
    round_2 = add_round(tournament_id, 2)
    assert players[7] in _in_play(round_2)


def test_fr047_a_swiss_late_player_is_listed_and_their_player_cannot_be_removed(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    create: Callable[..., str],
    start: Callable[[str], Json],
    late: Callable[..., tuple[int, Json]],
    participants: Callable[[str], list[Json]],
    players: list[str],
) -> None:
    tournament_id = create(6)
    start(tournament_id)
    _, body = late(tournament_id, players[6], 2)

    removed = client.put(
        f"/api/v1/leagues/{league_id}/players/{players[6]}/removed",
        json={"removed": True},
        headers=headers,
    )

    assert body["entry_id"] in [p["entry_id"] for p in participants(tournament_id)]
    assert (removed.status_code, removed.json()["code"]) == (
        422,
        "player_in_unfinished_tournament",
    )


def test_adr008_deleting_round_1_makes_a_late_player_an_ordinary_picked_player(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    create: Callable[..., str],
    start: Callable[[str], Json],
    late: Callable[..., tuple[int, Json]],
    get: Callable[[str, str], Json],
    players: list[str],
) -> None:
    tournament_id = create(6)
    started = start(tournament_id)
    late(tournament_id, players[6], 2)
    base = f"/api/v1/leagues/{league_id}/tournaments/{tournament_id}"

    deleted = client.delete(
        f"{base}/rounds/{_round(started, 1)['id']}", headers=headers
    )
    restarted = start(tournament_id)

    assert deleted.status_code == 204
    entries = _entries(restarted)
    assert sorted(e["seed"] for e in entries) == list(range(1, 8))
    setup = get(tournament_id, "/setup")
    assert players[6] in setup["player_ids"]


def test_fr047_br021_br058_deleting_round_1_seeds_a_late_player_by_the_ranking_again(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    create: Callable[..., str],
    start: Callable[[str], Json],
    late: Callable[..., tuple[int, Json]],
    get: Callable[[str, str], Json],
    players: list[str],
) -> None:
    tournament_id = create(6)
    base = f"/api/v1/leagues/{league_id}/tournaments/{tournament_id}"
    # Nobody has points yet, so the ranking is the tournament's lot (ADR-010).
    rank = {r["player_id"]: r["rank"] for r in get(tournament_id, "/setup")["ranking"]}
    best = min(players, key=rank.__getitem__)  # the late player: ranked #1
    picked = [p for p in players if p != best][:6]
    repicked = client.put(
        f"{base}/setup/players", json={"player_ids": picked}, headers=headers
    )
    assert repicked.status_code == 200, repicked.text
    started = start(tournament_id)
    status, _ = late(tournament_id, best, 2)
    assert status == 201
    assert _entry_of(get(tournament_id, ""), best)["seed"] == 7  # the next seed

    deleted = client.delete(
        f"{base}/rounds/{_round(started, 1)['id']}", headers=headers
    )
    restarted = start(tournament_id)

    assert deleted.status_code == 204
    entries = _entries(restarted)
    by_rank = sorted(entries, key=lambda e: rank[e["player_ids"][0]])
    assert [e["seed"] for e in by_rank] == list(range(1, 8))
    assert _entry_of(restarted, best)["seed"] == 1
    [sitting_out] = _round(restarted, 1)["sitting_out"]  # the lowest seed (BR-058)
    assert sitting_out == by_rank[-1]["id"]
    assert sitting_out != _entry_of(restarted, best)["id"]


def test_fr036_going_back_to_setup_seeds_a_late_player_by_the_ranking_again(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    create: Callable[..., str],
    start: Callable[[str], Json],
    late: Callable[..., tuple[int, Json]],
    get: Callable[[str, str], Json],
    players: list[str],
) -> None:
    tournament_id = create(6)
    base = f"/api/v1/leagues/{league_id}/tournaments/{tournament_id}"
    rank = {r["player_id"]: r["rank"] for r in get(tournament_id, "/setup")["ranking"]}
    best = min(players, key=rank.__getitem__)
    picked = [p for p in players if p != best][:6]
    client.put(f"{base}/setup/players", json={"player_ids": picked}, headers=headers)
    start(tournament_id)
    late(tournament_id, best, 2)

    back = client.post(
        f"{base}/back-to-setup",
        json={"expected_state": "in_progress"},
        headers=headers,
    )

    assert back.status_code == 200, back.text
    setup = get(tournament_id, "/setup")
    seeds = {e["player_ids"][0]: e["seed"] for e in setup["entries"]}
    assert seeds[best] == 1
    assert sorted(seeds.values()) == list(range(1, 8))


def test_fr046_deleting_round_1_keeps_the_seeds_of_a_tournament_without_a_late_entry(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    create: Callable[..., str],
    start: Callable[[str], Json],
    get: Callable[[str, str], Json],
) -> None:
    tournament_id = create(6)
    base = f"/api/v1/leagues/{league_id}/tournaments/{tournament_id}"
    entry_ids = [e["id"] for e in get(tournament_id, "/setup")["entries"]]
    by_hand = list(reversed(entry_ids))  # the organizer reorders the seeds (FR-034)
    ordered = client.put(
        f"{base}/setup/seed-order", json={"entry_ids": by_hand}, headers=headers
    )
    assert ordered.status_code == 200, ordered.text
    started = start(tournament_id)

    deleted = client.delete(
        f"{base}/rounds/{_round(started, 1)['id']}", headers=headers
    )

    assert deleted.status_code == 204
    entries = get(tournament_id, "/setup")["entries"]
    assert [e["id"] for e in sorted(entries, key=lambda e: e["seed"])] == by_hand


def test_fr047_deleting_a_later_round_after_a_late_join_leaves_the_player_joining_it(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    create: Callable[..., str],
    start: Callable[[str], Json],
    play_round: Callable[[str, int], None],
    add_round: Callable[[str, int], Json],
    late: Callable[..., tuple[int, Json]],
    get: Callable[[str, str], Json],
    participants: Callable[[str], list[Json]],
    players: list[str],
    session: Session,
) -> None:
    tournament_id = create(6)
    start(tournament_id)
    play_round(tournament_id, 1)
    round_2 = add_round(tournament_id, 2)
    status, body = late(tournament_id, players[6], 3)
    assert status == 201
    entry_id = body["entry_id"]
    assert _statuses(session, tournament_id, entry_id) == {
        1: "not_joined",
        2: "not_joined",
    }

    deleted = client.delete(
        f"/api/v1/leagues/{league_id}/tournaments/{tournament_id}"
        f"/rounds/{round_2['id']}",
        headers=headers,
    )

    assert deleted.status_code == 204
    session.expire_all()
    assert _statuses(session, tournament_id, entry_id) == {1: "not_joined"}
    shown = {p["entry_id"]: p for p in participants(tournament_id)}
    assert shown[entry_id]["joined_round"] == 2
    again = add_round(tournament_id, 2)
    assert players[6] in _in_play(again)
    assert _entry_of(get(tournament_id, ""), players[6])["id"] == entry_id


def test_d5_one_participation_row_per_main_entry_per_group_round(
    create: Callable[..., str],
    start: Callable[[str], Json],
    play_round: Callable[[str, int], None],
    add_round: Callable[[str, int], Json],
    late: Callable[..., tuple[int, Json]],
    players: list[str],
    session: Session,
) -> None:
    tournament_id = create(6)
    start(tournament_id)
    play_round(tournament_id, 1)
    late(tournament_id, players[6], 2)
    add_round(tournament_id, 2)
    play_round(tournament_id, 2)
    late(tournament_id, players[7], 3)
    add_round(tournament_id, 3)

    counts = session.execute(
        select(Round.round_no, func.count())
        .join(RoundParticipation, RoundParticipation.round_id == Round.id)
        .join(TournamentPhase, Round.phase_id == TournamentPhase.id)
        .where(TournamentPhase.tournament_id == UUID(tournament_id))
        .group_by(Round.round_no)
    ).all()

    assert sorted(counts) == [(1, 8), (2, 8), (3, 8)]


# ------------------------------------------------------------ refusals


def test_fr047_an_unknown_player_and_one_of_another_league_are_404(
    create: Callable[..., str],
    start: Callable[[str], Json],
    late: Callable[..., tuple[int, Json]],
    make_league: Callable[..., League],
    make_player: Callable[..., Player],
) -> None:
    tournament_id = create(4)
    start(tournament_id)
    foreign = make_player(league=make_league(), name="Elsewhere")

    unknown = late(tournament_id, uuid7(), 2)
    other_league = late(tournament_id, foreign.id, 2)

    assert unknown[0] == other_league[0] == 404
    assert unknown[1]["code"] == other_league[1]["code"] == "player_not_found"


def test_br002_a_removed_player_is_409(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    create: Callable[..., str],
    start: Callable[[str], Json],
    late: Callable[..., tuple[int, Json]],
    players: list[str],
) -> None:
    tournament_id = create(4)
    start(tournament_id)
    client.put(
        f"/api/v1/leagues/{league_id}/players/{players[6]}/removed",
        json={"removed": True},
        headers=headers,
    )

    status, body = late(tournament_id, players[6], 2)

    assert (status, body["code"]) == (409, "player_removed")
    assert body["detail"] == {"player_id": players[6]}


def test_br011_a_closed_season_is_409(
    session: Session,
    now: datetime,
    create: Callable[..., str],
    start: Callable[[str], Json],
    get: Callable[[str, str], Json],
    late: Callable[..., tuple[int, Json]],
    players: list[str],
) -> None:
    tournament_id = create(4)
    start(tournament_id)
    season = session.get_one(Season, UUID(get(tournament_id, "")["season_id"]))
    season.state, season.closed_at = SeasonState.CLOSED, now
    session.flush()  # season 1 closes before season 2 becomes the active one
    session.add(
        Season(
            league_id=season.league_id,
            number=2,
            state=SeasonState.ACTIVE,
            placement_points=season.placement_points,
            started_at=now,
            created_at=now,
        )
    )

    status, body = late(tournament_id, players[6], 2)

    assert (status, body["code"]) == (409, "season_closed")


def test_fr047_a_tournament_in_setup_and_a_finished_one_are_409(
    create: Callable[..., str],
    start: Callable[[str], Json],
    play_round: Callable[[str, int], None],
    post: Callable[[str, str, Json], Json],
    late: Callable[..., tuple[int, Json]],
    players: list[str],
) -> None:
    in_setup = create(4)
    finished = create(4)
    start(finished)
    play_round(finished, 1)
    post(finished, "/finish", {"expected_state": "in_progress"})

    setup_result = late(in_setup, players[6], 1)
    finished_result = late(finished, players[6], 2)

    assert setup_result[0] == finished_result[0] == 409
    assert setup_result[1]["code"] == "tournament_not_in_progress"
    assert finished_result[1]["code"] == "tournament_not_in_progress"


def test_fr047_a_round_robin_takes_no_late_player(
    create: Callable[..., str],
    start: Callable[[str], Json],
    late: Callable[..., tuple[int, Json]],
    players: list[str],
) -> None:
    tournament_id = create(4, group_phase="round_robin", round_robin_legs=1)
    start(tournament_id)

    status, body = late(tournament_id, players[6], 2)

    assert (status, body["code"]) == (422, "format_not_supported")


def test_br086_a_started_knockout_after_the_group_phase_takes_no_late_player(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    create: Callable[..., str],
    start: Callable[[str], Json],
    play_round: Callable[[str, int], None],
    get: Callable[[str, str], Json],
    late: Callable[..., tuple[int, Json]],
    players: list[str],
) -> None:
    tournament_id = create(4)
    start(tournament_id)
    play_round(tournament_id, 1)
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

    status, body = late(tournament_id, players[6], 2)

    assert (status, body["code"]) == (422, "group_phase_locked")


@pytest.mark.parametrize(
    "values",
    [
        pytest.param({"type": "doubles"}, id="doubles"),
        pytest.param({"type": "dyp"}, id="dyp"),
    ],
)
def test_fr047_a_dyp_and_doubles_take_no_late_player(
    client: TestClient,
    league_id: UUID,
    headers: dict[str, str],
    create: Callable[..., str],
    start: Callable[[str], Json],
    late: Callable[..., tuple[int, Json]],
    players: list[str],
    values: Json,
) -> None:
    tournament_id = create(6, **values)
    if values["type"] == "doubles":
        paired = client.put(
            f"/api/v1/leagues/{league_id}/tournaments/{tournament_id}/setup/pairs",
            json={"pairs": [[players[n], players[n + 1]] for n in range(0, 6, 2)]},
            headers=headers,
        )
        assert paired.status_code == 200, paired.text
    start(tournament_id)

    status, body = late(tournament_id, players[7], 2)

    assert (status, body["code"]) == (422, "late_entry_not_allowed")


def test_fr047_a_player_who_is_already_picked_is_422(
    create: Callable[..., str],
    start: Callable[[str], Json],
    late: Callable[..., tuple[int, Json]],
    players: list[str],
) -> None:
    tournament_id = create(6)
    start(tournament_id)
    first = late(tournament_id, players[6], 2)

    picked = late(tournament_id, players[0], 2)
    repeat = late(tournament_id, players[6], 2)

    assert first[0] == 201
    assert picked[0] == repeat[0] == 422
    assert picked[1]["code"] == repeat[1]["code"] == "player_already_in_tournament"


def test_adr008_a_stale_round_number_is_409_with_the_current_round(
    create: Callable[..., str],
    start: Callable[[str], Json],
    play_round: Callable[[str, int], None],
    add_round: Callable[[str, int], Json],
    late: Callable[..., tuple[int, Json]],
    players: list[str],
) -> None:
    tournament_id = create(6)
    start(tournament_id)
    play_round(tournament_id, 1)
    add_round(tournament_id, 2)

    old = late(tournament_id, players[6], 2)
    ahead = late(tournament_id, players[6], 4)

    for status, body in (old, ahead):
        assert (status, body["code"]) == (409, "round_number_changed")
        assert body["detail"] == {"current_round_no": 2}


def test_adr008_a_late_player_of_another_organizers_league_is_404(
    client: TestClient,
    league_id: UUID,
    make_league: Callable[..., League],
    auth_header: Callable[..., dict[str, str]],
    create: Callable[..., str],
    start: Callable[[str], Json],
    players: list[str],
) -> None:
    tournament_id = create(4)
    start(tournament_id)
    other = auth_header(make_league().owner_user_id)

    response = client.post(
        f"/api/v1/leagues/{league_id}/tournaments/{tournament_id}/entries",
        json={"player_id": players[6], "from_round_no": 2},
        headers=other,
    )

    assert (response.status_code, response.json()["code"]) == (404, "league_not_found")
