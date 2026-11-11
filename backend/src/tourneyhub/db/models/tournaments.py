from datetime import date, datetime
from uuid import UUID, uuid7

from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    LargeBinary,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tourneyhub.db.base import Base, str_enum
from tourneyhub.db.models.entries import Entry, PlayerHalf
from tourneyhub.engine.leagues import MAX_FIELD_COUNT, MAX_GOALS_PER_GAME
from tourneyhub.engine.lots import RNG_SEED_SIZE
from tourneyhub.engine.tournaments import (
    HalvesMethod,
    KnockoutMatchFormat,
    MatchFormat,
    MonsterKnockoutMode,
    PhaseFormat,
    PhaseKind,
    SeedingMethod,
    TournamentState,
    TournamentType,
)


class Tournament(Base):
    """A tournament of a season with its settings and state (DATA-MODEL §4.3)."""

    __tablename__ = "tournaments"
    __table_args__ = (
        CheckConstraint(f"octet_length(rng_seed) = {RNG_SEED_SIZE}", name="rng_seed"),
        CheckConstraint("draw_counter >= 0", name="draw_counter"),
        # Halves are used by DYP only (FR-033); every other type keeps 'ranking'.
        CheckConstraint(
            "halves_method = 'ranking' OR type = 'dyp'", name="halves_method_type"
        ),
        CheckConstraint(
            f"goals_per_game >= 1 AND goals_per_game <= {MAX_GOALS_PER_GAME}",
            name="goals_per_game",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)  # supplied by the client
    season_id: Mapped[UUID] = mapped_column(
        ForeignKey("seasons.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str]
    # The organizer's calendar date, sent by the client (FR-030); never from UTC.
    date: Mapped[date]
    type: Mapped[TournamentType] = mapped_column(
        str_enum(TournamentType, name="tournament_type")
    )
    state: Mapped[TournamentState] = mapped_column(
        str_enum(TournamentState, name="tournament_state")
    )
    # Not used by Monster DYP, which has no seeds (FR-034).
    seeding_method: Mapped[SeedingMethod] = mapped_column(
        str_enum(SeedingMethod, name="seeding_method")
    )
    # Used only by DYP (FR-033, BR-032).
    halves_method: Mapped[HalvesMethod] = mapped_column(
        str_enum(HalvesMethod, name="halves_method")
    )
    rng_seed: Mapped[bytes] = mapped_column(LargeBinary)  # immutable (ADR-010)
    draw_counter: Mapped[int]
    goals_per_game: Mapped[int]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime | None]

    phases: Mapped[list[TournamentPhase]] = relationship(
        lazy="raise",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="TournamentPhase.position",
    )
    fields: Mapped[list[Field]] = relationship(
        lazy="raise",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Field.number",
    )
    players: Mapped[list[TournamentPlayer]] = relationship(
        lazy="raise", cascade="all, delete-orphan", passive_deletes=True
    )
    # dyp_halves references the tournament through tournament_players.
    halves: Mapped[list[PlayerHalf]] = relationship(
        primaryjoin="Tournament.id == foreign(PlayerHalf.tournament_id)",
        lazy="raise",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    entries: Mapped[list[Entry]] = relationship(
        lazy="raise",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Entry.created_at, Entry.id",
    )


class TournamentPhase(Base):
    """One phase of a tournament, in order (DATA-MODEL §4.3, D9).

    The CHECKs tie the columns to `kind` and `format`; rules that need another
    row, the tournament type or the league are the application's.
    """

    __tablename__ = "tournament_phases"
    __table_args__ = (
        UniqueConstraint("tournament_id", "position"),
        # At most one group phase and one knockout (FR-031), as a partial index so
        # that later formats can add kinds of their own (D9).
        Index(
            "uq_tournament_phases_tournament_id_kind",
            "tournament_id",
            "kind",
            unique=True,
            postgresql_where=text("kind IN ('group', 'knockout')"),
        ),
        CheckConstraint(
            "(kind = 'group' AND position = 1)"
            " OR (kind = 'knockout' AND position IN (1, 2))",
            name="position",
        ),
        CheckConstraint(
            "(kind = 'group') = (format IN ('round_robin', 'swiss', 'monster_dyp'))",
            name="format_kind",
        ),
        CheckConstraint(
            "(format = 'round_robin') = (round_robin_legs IS NOT NULL)"
            " AND (round_robin_legs IS NULL OR round_robin_legs IN (1, 2))",
            name="round_robin_legs",
        ),
        CheckConstraint(
            "(kind = 'group') = (sit_out_points IS NOT NULL)"
            " AND (sit_out_points IS NULL OR sit_out_points IN (0, 1))",
            name="sit_out_points",
        ),
        # The helper is created by the migration: a subset of the three, no repeat.
        CheckConstraint(
            "(format IN ('swiss', 'monster_dyp')) = (tiebreakers IS NOT NULL)"
            " AND (tiebreakers IS NULL OR tiebreakers_valid(tiebreakers))",
            name="tiebreakers",
        ),
        CheckConstraint(
            "(kind = 'knockout') = (third_place_match IS NOT NULL)",
            name="third_place_match",
        ),
        CheckConstraint(
            "qualifiers IS NULL OR (kind = 'knockout' AND qualifiers >= 2)",
            name="qualifiers",
        ),
        CheckConstraint(
            "monster_knockout_mode IS NULL OR kind = 'knockout'",
            name="monster_knockout_mode_kind",
        ),
        CheckConstraint(
            "final_match_format IS NULL OR kind = 'knockout'",
            name="final_match_format_kind",
        ),
        # BR-121: BO2 only in a group phase.
        CheckConstraint("match_format <> 'bo2' OR kind = 'group'", name="bo2"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    tournament_id: Mapped[UUID] = mapped_column(
        ForeignKey("tournaments.id", ondelete="CASCADE")
    )
    position: Mapped[int]
    kind: Mapped[PhaseKind] = mapped_column(str_enum(PhaseKind, name="phase_kind"))
    format: Mapped[PhaseFormat] = mapped_column(
        str_enum(PhaseFormat, name="phase_format")
    )
    round_robin_legs: Mapped[int | None]
    sit_out_points: Mapped[int | None]
    tiebreakers: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    qualifiers: Mapped[int | None]
    third_place_match: Mapped[bool | None]
    monster_knockout_mode: Mapped[MonsterKnockoutMode | None] = mapped_column(
        str_enum(MonsterKnockoutMode, name="monster_knockout_mode")
    )
    match_format: Mapped[MatchFormat] = mapped_column(
        str_enum(MatchFormat, name="match_format")
    )
    final_match_format: Mapped[KnockoutMatchFormat | None] = mapped_column(
        str_enum(KnockoutMatchFormat, name="final_match_format")
    )
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime | None]


class Field(Base):
    """A field of a tournament, shown as "Field" and its number (DATA-MODEL §4.6).

    The match being played on it (`match_id`) arrives with the matches.
    """

    __tablename__ = "fields"
    __table_args__ = (
        UniqueConstraint("tournament_id", "number"),
        CheckConstraint(f"number >= 1 AND number <= {MAX_FIELD_COUNT}", name="number"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    tournament_id: Mapped[UUID] = mapped_column(
        ForeignKey("tournaments.id", ondelete="CASCADE")
    )
    number: Mapped[int]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime | None]


class TournamentPlayer(Base):
    """A player the organizer picked for a tournament (FR-032).

    The picked players are the setup's input: entries, Doubles pairs and DYP
    halves are made from them (ADR-010). A Doubles player without a partner, or
    a DYP player without a half yet, has only this row.
    """

    __tablename__ = "tournament_players"
    __table_args__ = (
        # The deferred reference of DATA-MODEL §2: a player is never deleted while
        # a tournament names them, except with the league.
        ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
            name="fk_tournament_players_player_id_players",
            deferrable=True,
            initially="DEFERRED",
        ),
    )

    tournament_id: Mapped[UUID] = mapped_column(
        ForeignKey("tournaments.id", ondelete="CASCADE"), primary_key=True
    )
    player_id: Mapped[UUID] = mapped_column(primary_key=True, index=True)
    created_at: Mapped[datetime]
