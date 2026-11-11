from collections.abc import Callable
from datetime import datetime
from uuid import uuid7

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tourneyhub.db.models.entries import Entry, EntryMember
from tourneyhub.db.models.leagues import League, Player
from tourneyhub.db.models.matches import (
    Match,
    MatchGame,
    MatchSide,
    MatchSidePlayer,
    Round,
    RoundParticipation,
)
from tourneyhub.db.models.tournaments import Field, Tournament, TournamentPlayer
from tourneyhub.engine.tournaments import (
    EntryKind,
    EntryStage,
    MatchKind,
    Outcome,
    Participation,
    TournamentState,
)


def _check_now(session: Session) -> None:
    """Run the deferred checks, as a commit would (DATA-MODEL §2)."""
    session.flush()
    session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    session.execute(text("SET CONSTRAINTS ALL DEFERRED"))


def _execute(session: Session, statement: str, **params: object) -> None:
    session.execute(text(statement), params)
    _check_now(session)


@pytest.fixture
def match(
    session: Session,
    make_league: Callable[..., League],
    make_tournament: Callable[..., Tournament],
    make_player: Callable[..., Player],
    now: datetime,
) -> Match:
    """Round 1 of a running round robin: player 1 against player 2 on field 1."""
    league = make_league()
    tournament = make_tournament(league=league, state=TournamentState.IN_PROGRESS)
    entries = []
    for seed in (1, 2):
        player = make_player(league=league)
        session.add(
            TournamentPlayer(
                tournament_id=tournament.id, player_id=player.id, created_at=now
            )
        )
        entry = Entry(
            id=uuid7(),
            tournament_id=tournament.id,
            stage=EntryStage.MAIN,
            kind=EntryKind.PLAYER,
            seed=seed,
            created_at=now,
            members=[],
        )
        entry.members.append(
            EntryMember(
                entry_id=entry.id,
                player_id=player.id,
                tournament_id=tournament.id,
                stage=EntryStage.MAIN,
                created_at=now,
            )
        )
        session.add(entry)
        entries.append((entry, player))
    round_id, match_id = uuid7(), uuid7()
    session.add(
        Round(
            id=round_id,
            phase_id=tournament.phases[0].id,
            round_no=1,
            created_at=now,
            participation=[
                RoundParticipation(
                    round_id=round_id,
                    entry_id=entry.id,
                    status=Participation.PLAYED,
                    created_at=now,
                )
                for entry, _ in entries
            ],
            matches=[
                Match(
                    id=match_id,
                    round_id=round_id,
                    position=1,
                    kind=MatchKind.STANDARD,
                    is_walkover=False,
                    created_at=now,
                    games=[],
                    sides=[
                        MatchSide(
                            match_id=match_id,
                            side=side,
                            entry_id=entry.id,
                            is_bye=False,
                            created_at=now,
                            players=[
                                MatchSidePlayer(
                                    match_id=match_id,
                                    side=side,
                                    player_id=player.id,
                                    created_at=now,
                                )
                            ],
                        )
                        for side, (entry, player) in enumerate(entries, start=1)
                    ],
                )
            ],
        )
    )
    session.flush()
    tournament.fields[0].match_id = match_id
    session.flush()
    return session.get_one(Match, match_id)


@pytest.mark.parametrize(
    ("assignments", "constraint"),
    [
        pytest.param(
            "is_walkover = true", "ck_matches_walkover", id="BR-093-no-winner"
        ),
        pytest.param(
            "is_walkover = true, outcome = 'draw', result_entered_at = now()",
            "ck_matches_walkover",
            id="BR-124-drawn-walkover",
        ),
        pytest.param(
            "outcome = 'side_1'", "ck_matches_result_entered_at", id="D7-result-time"
        ),
        pytest.param(
            "outcome = 'side_1', result_entered_at = now(), requeued_at = now()",
            "ck_matches_requeued_at",
            id="BR-132-requeued-result",
        ),
        pytest.param("position = 0", "ck_matches_position", id="position"),
        pytest.param("kind = 'final'", "ck_matches_match_kind", id="kind"),
    ],
)
def test_d11_the_checks_keep_a_result_consistent(
    session: Session, match: Match, assignments: str, constraint: str
) -> None:
    with pytest.raises(IntegrityError, match=constraint), session.begin_nested():
        _execute(
            session,
            f"UPDATE matches SET {assignments} WHERE id = :id",  # noqa: S608
            id=match.id,
        )


@pytest.mark.parametrize(
    ("values", "constraint"),
    [
        pytest.param("0, 'side_1', NULL, NULL", "ck_match_games_game_no", id="game-0"),
        pytest.param("6, 'side_1', NULL, NULL", "ck_match_games_game_no", id="game-6"),
        pytest.param(
            "1, 'side_1', 3, NULL", "ck_match_games_both_scores", id="one-score"
        ),
        pytest.param(
            "1, 'side_1', -1, -2", "ck_match_games_scores_not_negative", id="negative"
        ),
        pytest.param(
            "1, 'side_1', 3, 10", "ck_match_games_winner_scores", id="BR-092-winner"
        ),
        pytest.param(
            "1, 'draw', 3, 4", "ck_match_games_winner_scores", id="BR-092-draw"
        ),
        pytest.param(
            "2, 'draw', NULL, NULL", "ck_match_games_draw_game_no", id="BR-121-draw"
        ),
    ],
)
def test_br092_the_checks_keep_a_game_consistent(
    session: Session, match: Match, values: str, constraint: str
) -> None:
    with pytest.raises(IntegrityError, match=constraint), session.begin_nested():
        _execute(
            session,
            "INSERT INTO match_games (match_id, game_no, winner, score_1, score_2,"  # noqa: S608
            f" created_at) VALUES (:id, {values}, now())",
            id=match.id,
        )


def test_br092_a_game_may_have_no_score_or_one_that_fits(
    session: Session, match: Match, now: datetime
) -> None:
    session.add_all(
        [
            MatchGame(
                match_id=match.id, game_no=1, winner=Outcome.DRAW, created_at=now
            ),
            MatchGame(
                match_id=match.id,
                game_no=2,
                winner=Outcome.SIDE_2,
                score_1=8,
                score_2=10,
                created_at=now,
            ),
        ]
    )
    session.flush()
    session.execute(
        text("DELETE FROM match_games WHERE match_id = :id"), {"id": match.id}
    )


@pytest.mark.parametrize(
    ("statement", "constraint"),
    [
        pytest.param(
            "UPDATE match_sides SET is_bye = true WHERE match_id = :id AND side = 1",
            "ck_match_sides_bye_entry",
            id="BR-041-bye-with-entry",
        ),
        pytest.param(
            "UPDATE match_sides SET side = 3 WHERE match_id = :id AND side = 2",
            "ck_match_sides_side",
            id="side-3",
        ),
        pytest.param(
            "INSERT INTO match_side_players (match_id, side, player_id, created_at)"
            " SELECT match_id, 2, player_id, now() FROM match_side_players"
            " WHERE match_id = :id AND side = 1",
            "uq_match_side_players_match_id_player_id",
            id="D2-player-on-both-sides",
        ),
        pytest.param(
            "INSERT INTO rounds (id, phase_id, round_no, created_at)"
            " SELECT gen_random_uuid(), phase_id, 1, now() FROM rounds r"
            " JOIN matches m ON m.round_id = r.id WHERE m.id = :id",
            "uq_rounds_phase_id_round_no",
            id="round-twice",
        ),
        pytest.param(
            "INSERT INTO fields (id, tournament_id, number, match_id, created_at)"
            " SELECT gen_random_uuid(), tournament_id, 2, match_id, now()"
            " FROM fields WHERE match_id = :id",
            "uq_fields_match_id",
            id="D10-match-on-two-fields",
        ),
    ],
)
def test_d2_the_checks_keep_sides_rounds_and_fields_consistent(
    session: Session, match: Match, statement: str, constraint: str
) -> None:
    with pytest.raises(IntegrityError, match=constraint), session.begin_nested():
        _execute(session, statement, id=match.id)


def test_d6_an_entry_with_a_match_is_not_deleted_on_its_own(
    session: Session, match: Match
) -> None:
    with (
        pytest.raises(IntegrityError, match="fk_match_sides_entry_id_entries"),
        session.begin_nested(),
    ):
        _execute(
            session,
            "DELETE FROM entries WHERE id IN"
            " (SELECT entry_id FROM match_sides WHERE match_id = :id)",
            id=match.id,
        )


def test_d6_a_player_on_a_side_is_not_deleted_on_their_own(
    session: Session, match: Match
) -> None:
    with (
        pytest.raises(IntegrityError, match=r"fk_\w+_player_id_players"),
        session.begin_nested(),
    ):
        _execute(
            session,
            "DELETE FROM players WHERE id IN"
            " (SELECT player_id FROM match_side_players WHERE match_id = :id)",
            id=match.id,
        )


def test_d10_deleting_the_rounds_frees_the_field(
    session: Session, match: Match
) -> None:
    _execute(session, "DELETE FROM rounds WHERE id = :id", id=match.round_id)

    assert (
        session.scalars(select(Field.match_id).where(Field.match_id.is_not(None))).all()
        == []
    )
    assert session.scalar(text("SELECT count(*) FROM match_side_players")) == 0
    assert session.scalar(text("SELECT count(*) FROM round_participation")) == 0


def test_fr038_deleting_a_running_tournament_removes_its_schedule(
    session: Session, match: Match
) -> None:
    _execute(
        session,
        "DELETE FROM tournaments WHERE id IN (SELECT tournament_id FROM fields"
        " WHERE match_id = :id)",
        id=match.id,
    )

    assert session.scalar(text("SELECT count(*) FROM matches")) == 0
    assert session.scalar(text("SELECT count(*) FROM players")) == 2
