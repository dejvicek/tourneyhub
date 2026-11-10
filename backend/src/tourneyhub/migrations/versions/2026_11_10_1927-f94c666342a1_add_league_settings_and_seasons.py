"""add league settings and seasons

DATA-MODEL §4.2: leagues gets draws_allowed, the defaults for new tournaments
and share_token; seasons holds each league's seasons with their placement
points table, checked by the SQL helper placement_points_valid().

Leagues that exist already keep draws off and the defaults of FR-011, get a
random share token and an active Season 1 with the default table, started when
the league was created (FR-010).

Revision ID: f94c666342a1
Revises: 83247262de46
Create Date: 2026-11-10 19:27:53.958132
"""

import secrets
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f94c666342a1"
down_revision: str | None = "83247262de46"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# FR-011: one-dimensional, not empty, no NULL, no negative value, and no place
# worth more than the place above it. CASE, because array_ndims() is NULL for an
# empty array and SQL does not promise to evaluate AND from left to right.
_CREATE_PLACEMENT_POINTS_VALID = """
CREATE FUNCTION placement_points_valid(points integer[]) RETURNS boolean
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    RETURN CASE
        WHEN array_ndims(points) IS DISTINCT FROM 1 THEN false
        ELSE NOT EXISTS (
            SELECT FROM generate_subscripts(points, 1) AS i
            WHERE points[i] IS NULL
                OR points[i] < 0
                OR (i > array_lower(points, 1) AND points[i] > points[i - 1])
        )
    END
"""

# Stubs as of this revision; the app's models will change, this must not (§7).
_leagues = sa.table(
    "leagues",
    sa.column("id", sa.Uuid()),
    sa.column("share_token", sa.String()),
    sa.column("created_at", sa.DateTime(timezone=True)),
)
_seasons = sa.table(
    "seasons",
    sa.column("id", sa.Uuid()),
    sa.column("league_id", sa.Uuid()),
    sa.column("number", sa.Integer()),
    sa.column("state", sa.String()),
    sa.column("placement_points", postgresql.ARRAY(sa.Integer())),
    sa.column("started_at", sa.DateTime(timezone=True)),
    sa.column("created_at", sa.DateTime(timezone=True)),
)


def upgrade() -> None:
    op.execute(_CREATE_PLACEMENT_POINTS_VALID)
    op.create_table(
        "seasons",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("league_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column(
            "state",
            sa.Enum(
                "active",
                "closed",
                name="season_state",
                native_enum=False,
                create_constraint=True,
                length=None,
            ),
            nullable=False,
        ),
        sa.Column("placement_points", sa.ARRAY(sa.Integer()), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(state = 'closed') = (closed_at IS NOT NULL)",
            name=op.f("ck_seasons_closed_at"),
        ),
        sa.CheckConstraint("number >= 1", name=op.f("ck_seasons_number")),
        sa.CheckConstraint(
            "placement_points_valid(placement_points)",
            name=op.f("ck_seasons_placement_points"),
        ),
        sa.ForeignKeyConstraint(
            ["league_id"],
            ["leagues.id"],
            name=op.f("fk_seasons_league_id_leagues"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_seasons")),
        sa.UniqueConstraint(
            "league_id", "number", name=op.f("uq_seasons_league_id_number")
        ),
    )
    # At most one active season per league (ADR-002); named here, like the
    # expression index on users.
    op.create_index(
        "uq_seasons_league_id_active",
        "seasons",
        ["league_id"],
        unique=True,
        postgresql_where=sa.text("state = 'active'"),
    )
    op.add_column(
        "leagues",
        sa.Column(
            "draws_allowed",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "leagues",
        sa.Column(
            "default_field_count",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
    )
    op.add_column(
        "leagues",
        sa.Column(
            "default_match_format",
            sa.Enum(
                "bo1",
                "bo3",
                "bo5",
                name="default_match_format",
                native_enum=False,
                create_constraint=True,
                length=None,
            ),
            server_default="bo1",
            nullable=False,
        ),
    )
    op.add_column(
        "leagues",
        sa.Column(
            "default_goals_per_game",
            sa.Integer(),
            server_default=sa.text("10"),
            nullable=False,
        ),
    )
    # Autogenerate misses CHECKs added to an existing table.
    op.create_check_constraint(
        op.f("ck_leagues_default_field_count"), "leagues", "default_field_count >= 1"
    )
    op.create_check_constraint(
        op.f("ck_leagues_default_goals_per_game"),
        "leagues",
        "default_goals_per_game > 0",
    )
    op.add_column("leagues", sa.Column("share_token", sa.String(), nullable=True))
    _backfill_leagues()
    op.alter_column("leagues", "share_token", nullable=False)
    op.create_unique_constraint(
        op.f("uq_leagues_share_token"), "leagues", ["share_token"]
    )


def _backfill_leagues() -> None:
    """Give each existing league a share token and an active Season 1."""
    connection = op.get_bind()
    leagues = connection.execute(sa.select(_leagues.c.id, _leagues.c.created_at))
    for league_id, created_at in leagues.all():
        connection.execute(
            _leagues.update()
            .where(_leagues.c.id == league_id)
            .values(share_token=secrets.token_urlsafe(16))  # FR-071: 128 bits
        )
        connection.execute(
            _seasons.insert().values(
                id=uuid.uuid7(),
                league_id=league_id,
                number=1,
                state="active",
                placement_points=[10, 8, 6, 4, 2],  # FR-011
                started_at=created_at,
                created_at=created_at,
            )
        )


def downgrade() -> None:
    op.drop_constraint(op.f("uq_leagues_share_token"), "leagues", type_="unique")
    op.drop_column("leagues", "share_token")
    op.drop_constraint(
        op.f("ck_leagues_default_goals_per_game"), "leagues", type_="check"
    )
    op.drop_constraint(op.f("ck_leagues_default_field_count"), "leagues", type_="check")
    op.drop_column("leagues", "default_goals_per_game")
    op.drop_column("leagues", "default_match_format")
    op.drop_column("leagues", "default_field_count")
    op.drop_column("leagues", "draws_allowed")
    op.drop_index(
        "uq_seasons_league_id_active",
        table_name="seasons",
        postgresql_where=sa.text("state = 'active'"),
    )
    op.drop_table("seasons")
    op.execute("DROP FUNCTION placement_points_valid(integer[])")
