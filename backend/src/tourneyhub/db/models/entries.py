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
from tourneyhub.engine.dyp import DypHalf
from tourneyhub.engine.tournaments import EntryKind, EntryStage


class Entry(Base):
    """Whoever takes a place in a phase: one player or a pair (DATA-MODEL §4.4)."""

    __tablename__ = "entries"
    __table_args__ = (
        # Seeds can be swapped in one transaction (FR-034).
        UniqueConstraint(
            "tournament_id",
            "stage",
            "seed",
            deferrable=True,
            initially="DEFERRED",
        ),
        # The target of entry_members' composite reference; stage never changes.
        UniqueConstraint("id", "tournament_id", "stage"),
        CheckConstraint("seed IS NULL OR seed >= 1", name="seed"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    tournament_id: Mapped[UUID] = mapped_column(
        ForeignKey("tournaments.id", ondelete="CASCADE")
    )
    stage: Mapped[EntryStage] = mapped_column(str_enum(EntryStage, name="entry_stage"))
    kind: Mapped[EntryKind] = mapped_column(str_enum(EntryKind, name="entry_kind"))
    seed: Mapped[int | None]  # None until seeded, and always in Monster DYP
    # A knockout entry that continues one group-phase entry (BR-082, BR-085).
    source_entry_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("entries.id", ondelete="CASCADE")
    )
    is_top_player: Mapped[bool] = mapped_column(server_default=false())  # FR-041
    is_disabled: Mapped[bool] = mapped_column(server_default=false())  # FR-044
    created_at: Mapped[datetime]

    members: Mapped[list[EntryMember]] = relationship(
        lazy="raise", cascade="all, delete-orphan", passive_deletes=True
    )


class EntryMember(Base):
    """One of the one or two players of an entry (DATA-MODEL §4.4).

    `tournament_id` and `stage` are copied from the entry, so that a player is in
    at most one entry per stage (BR-003).
    """

    __tablename__ = "entry_members"
    __table_args__ = (
        ForeignKeyConstraint(
            ["entry_id", "tournament_id", "stage"],
            ["entries.id", "entries.tournament_id", "entries.stage"],
            name="fk_entry_members_entry_id_entries",
            ondelete="CASCADE",
        ),
        # The deferred reference of DATA-MODEL §2.
        ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
            name="fk_entry_members_player_id_players",
            deferrable=True,
            initially="DEFERRED",
        ),
        UniqueConstraint("tournament_id", "stage", "player_id"),
    )

    entry_id: Mapped[UUID] = mapped_column(primary_key=True)
    player_id: Mapped[UUID] = mapped_column(primary_key=True, index=True)
    tournament_id: Mapped[UUID]
    stage: Mapped[EntryStage] = mapped_column(
        str_enum(EntryStage, name="entry_member_stage")
    )
    created_at: Mapped[datetime]


class PlayerHalf(Base):
    """A DYP player's half before the pairs are drawn (DATA-MODEL `dyp_halves`).

    Only picked players have one: the row goes with the pick (BR-031 to BR-033).
    """

    __tablename__ = "dyp_halves"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tournament_id", "player_id"],
            ["tournament_players.tournament_id", "tournament_players.player_id"],
            name="fk_dyp_halves_tournament_id_tournament_players",
            ondelete="CASCADE",
        ),
        # The deferred reference of DATA-MODEL §2.
        ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
            name="fk_dyp_halves_player_id_players",
            deferrable=True,
            initially="DEFERRED",
        ),
    )

    tournament_id: Mapped[UUID] = mapped_column(primary_key=True)
    player_id: Mapped[UUID] = mapped_column(primary_key=True)
    half: Mapped[DypHalf] = mapped_column(str_enum(DypHalf, name="dyp_half"))
    created_at: Mapped[datetime]
