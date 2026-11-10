from datetime import datetime
from uuid import UUID, uuid7

from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
    false,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tourneyhub.db.base import Base, str_enum
from tourneyhub.engine.leagues import (
    MAX_FIELD_COUNT,
    MAX_GOALS_PER_GAME,
    DefaultMatchFormat,
    SeasonState,
)


class League(Base):
    """A league and its settings (DATA-MODEL §4.2, FR-011)."""

    __tablename__ = "leagues"
    __table_args__ = (
        CheckConstraint(
            f"default_field_count >= 1 AND default_field_count <= {MAX_FIELD_COUNT}",
            name="default_field_count",
        ),
        CheckConstraint(
            "default_goals_per_game >= 1"
            f" AND default_goals_per_game <= {MAX_GOALS_PER_GAME}",
            name="default_goals_per_game",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)  # supplied by the client
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str]
    draws_allowed: Mapped[bool] = mapped_column(server_default=false())
    default_field_count: Mapped[int] = mapped_column(server_default=text("1"))
    default_match_format: Mapped[DefaultMatchFormat] = mapped_column(
        str_enum(DefaultMatchFormat, name="default_match_format"),
        server_default=DefaultMatchFormat.BO1.value,
    )
    default_goals_per_game: Mapped[int] = mapped_column(server_default=text("10"))
    # The share link's secret (FR-071, ADR-008); never logged.
    share_token: Mapped[str] = mapped_column(unique=True)
    created_at: Mapped[datetime]  # the service's `now`, like updated_at
    updated_at: Mapped[datetime | None]

    seasons: Mapped[list[Season]] = relationship(
        back_populates="league",
        lazy="raise",
        cascade="all, delete-orphan",
        passive_deletes=True,  # ON DELETE CASCADE removes the rows not loaded
        order_by="Season.number",
    )


class Season(Base):
    """A season of a league with its placement points table (DATA-MODEL §4.2)."""

    __tablename__ = "seasons"
    __table_args__ = (
        UniqueConstraint("league_id", "number"),
        # At most one active season per league (ADR-002).
        Index(
            "uq_seasons_league_id_active",
            "league_id",
            unique=True,
            postgresql_where=text("state = 'active'"),
        ),
        CheckConstraint("number >= 1", name="number"),
        CheckConstraint(
            "(state = 'closed') = (closed_at IS NOT NULL)", name="closed_at"
        ),
        # The helper is created by the migration; FR-011's rule, see
        # engine.leagues.first_increase.
        CheckConstraint(
            "placement_points_valid(placement_points)", name="placement_points"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    league_id: Mapped[UUID] = mapped_column(
        ForeignKey("leagues.id", ondelete="CASCADE")
    )
    number: Mapped[int]
    name: Mapped[str | None]  # None: "Season <number>" in the UI language (FR-020)
    state: Mapped[SeasonState] = mapped_column(
        str_enum(SeasonState, name="season_state")
    )
    placement_points: Mapped[list[int]] = mapped_column(ARRAY(Integer))
    started_at: Mapped[datetime]
    closed_at: Mapped[datetime | None]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime | None]

    league: Mapped[League] = relationship(back_populates="seasons", lazy="raise")


class Player(Base):
    """A name on a league's player list (DATA-MODEL §4.2, FR-012).

    Players belong to the league, not to a season. A removed player keeps the
    row and its history (BR-002); the row goes only with its league (D6).
    """

    __tablename__ = "players"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    league_id: Mapped[UUID] = mapped_column(
        ForeignKey("leagues.id", ondelete="CASCADE")
    )
    name: Mapped[str]
    removed_at: Mapped[datetime | None]  # None while the player is on the list
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime | None]


# Unique on (league_id, lower(name)), removed players included (BR-001, ADR-002).
# Named here, like uq_users_lower_email, because the naming convention cannot name
# an expression index. A lookup by name compares func.lower(Player.name) with
# func.lower() of the input, so that it uses this index and folds as it does.
Index(
    "uq_players_league_id_lower_name",
    Player.league_id,
    func.lower(Player.name),
    unique=True,
)
