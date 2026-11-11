from datetime import datetime
from uuid import UUID, uuid7

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    UniqueConstraint,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tourneyhub.db.base import Base, str_enum
from tourneyhub.engine.tournaments import MatchKind, Outcome, Participation

MAX_GAMES = 5
"""BO5 plays at most five games (BR-121)."""


class Round(Base):
    """A round of a group phase, or a round of a bracket (DATA-MODEL §4.5)."""

    __tablename__ = "rounds"
    __table_args__ = (
        UniqueConstraint("phase_id", "round_no"),
        CheckConstraint("round_no >= 1", name="round_no"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    phase_id: Mapped[UUID] = mapped_column(
        ForeignKey("tournament_phases.id", ondelete="CASCADE")
    )
    round_no: Mapped[int]
    created_at: Mapped[datetime]

    matches: Mapped[list[Match]] = relationship(
        lazy="raise",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Match.kind, Match.position",
    )
    participation: Mapped[list[RoundParticipation]] = relationship(
        lazy="raise", cascade="all, delete-orphan", passive_deletes=True
    )


class RoundParticipation(Base):
    """Whether an entry played a group-phase round, and why not (D5).

    Every round of a group phase has one row for every main entry.
    """

    __tablename__ = "round_participation"

    round_id: Mapped[UUID] = mapped_column(
        ForeignKey("rounds.id", ondelete="CASCADE"), primary_key=True
    )
    entry_id: Mapped[UUID] = mapped_column(
        ForeignKey("entries.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    status: Mapped[Participation] = mapped_column(
        str_enum(Participation, name="participation")
    )
    created_at: Mapped[datetime]


class Match(Base):
    """A match of a round; its result is the outcome plus its games (D11).

    The CHECKs keep a result consistent within the row (BR-093, BR-124); the
    games and the format are the application's.
    """

    __tablename__ = "matches"
    __table_args__ = (
        UniqueConstraint("round_id", "kind", "position"),
        CheckConstraint("position >= 1", name="position"),
        # No result, no walkover; a walkover has a winner (FR-052, BR-124).
        CheckConstraint(
            "NOT is_walkover OR (outcome IS NOT NULL AND outcome <> 'draw')",
            name="walkover",
        ),
        # The time of the result is set exactly when there is a result (D7).
        CheckConstraint(
            "(outcome IS NULL) = (result_entered_at IS NULL)",
            name="result_entered_at",
        ),
        # A match with a result is not waiting for a field (BR-132, FR-094).
        CheckConstraint("outcome IS NULL OR requeued_at IS NULL", name="requeued_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    round_id: Mapped[UUID] = mapped_column(ForeignKey("rounds.id", ondelete="CASCADE"))
    position: Mapped[int]
    kind: Mapped[MatchKind] = mapped_column(str_enum(MatchKind, name="match_kind"))
    outcome: Mapped[Outcome | None] = mapped_column(
        str_enum(Outcome, name="match_outcome")
    )
    is_walkover: Mapped[bool] = mapped_column(server_default=false())
    result_entered_at: Mapped[datetime | None]
    requeued_at: Mapped[datetime | None]
    created_at: Mapped[datetime]

    sides: Mapped[list[MatchSide]] = relationship(
        lazy="raise",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="MatchSide.side",
    )
    games: Mapped[list[MatchGame]] = relationship(
        lazy="raise",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="MatchGame.game_no",
    )


class MatchGame(Base):
    """One game of a result, with its winner and, if entered, its score (D11).

    The CHECKs keep a game consistent within the row (BR-092): both scores or
    neither, a winner that agrees with them, and a draw only in game 1, since
    only a BO1 game can be drawn (BR-090, BR-121).
    """

    __tablename__ = "match_games"
    __table_args__ = (
        CheckConstraint(f"game_no >= 1 AND game_no <= {MAX_GAMES}", name="game_no"),
        CheckConstraint("score_1 >= 0 AND score_2 >= 0", name="scores_not_negative"),
        CheckConstraint("(score_1 IS NULL) = (score_2 IS NULL)", name="both_scores"),
        CheckConstraint(
            "score_1 IS NULL"
            " OR (winner = 'side_1' AND score_1 > score_2)"
            " OR (winner = 'side_2' AND score_2 > score_1)"
            " OR (winner = 'draw' AND score_1 = score_2)",
            name="winner_scores",
        ),
        CheckConstraint("winner <> 'draw' OR game_no = 1", name="draw_game_no"),
    )

    match_id: Mapped[UUID] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True
    )
    game_no: Mapped[int] = mapped_column(primary_key=True)
    winner: Mapped[Outcome] = mapped_column(str_enum(Outcome, name="game_winner"))
    score_1: Mapped[int | None]
    score_2: Mapped[int | None]
    created_at: Mapped[datetime]


class MatchSide(Base):
    """One of a match's two sides: an entry, a Monster DYP team or a bye (D2)."""

    __tablename__ = "match_sides"
    __table_args__ = (
        CheckConstraint("side IN (1, 2)", name="side"),
        # A bye side has no entry (BR-041); that it has no players is checked by
        # the application and an invariant query.
        CheckConstraint("NOT is_bye OR entry_id IS NULL", name="bye_entry"),
        # The deferred reference of DATA-MODEL §2: an entry with matches is not
        # deleted on its own.
        ForeignKeyConstraint(
            ["entry_id"],
            ["entries.id"],
            name="fk_match_sides_entry_id_entries",
            deferrable=True,
            initially="DEFERRED",
        ),
    )

    match_id: Mapped[UUID] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True
    )
    side: Mapped[int] = mapped_column(primary_key=True)
    entry_id: Mapped[UUID | None] = mapped_column(index=True)
    is_bye: Mapped[bool] = mapped_column(server_default=false())
    created_at: Mapped[datetime]

    players: Mapped[list[MatchSidePlayer]] = relationship(
        lazy="raise",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="MatchSidePlayer.player_id",
    )


class MatchSidePlayer(Base):
    """A player on a side, listed for every stored side (DATA-MODEL §4.5)."""

    __tablename__ = "match_side_players"
    __table_args__ = (
        ForeignKeyConstraint(
            ["match_id", "side"],
            ["match_sides.match_id", "match_sides.side"],
            name="fk_match_side_players_match_id_match_sides",
            ondelete="CASCADE",
        ),
        # The deferred reference of DATA-MODEL §2.
        ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
            name="fk_match_side_players_player_id_players",
            deferrable=True,
            initially="DEFERRED",
        ),
        # Nobody plays on both sides.
        UniqueConstraint("match_id", "player_id"),
    )

    match_id: Mapped[UUID] = mapped_column(primary_key=True)
    side: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[UUID] = mapped_column(primary_key=True, index=True)
    created_at: Mapped[datetime]
