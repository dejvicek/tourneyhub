"""create tournaments in setup

DATA-MODEL §4.3, §4.4 and §4.6: tournaments with their ordered phases (D9),
their fields, the players picked for them, their entries and entry members,
and the DYP halves. The references to players (picks and entry members) and an
entry member's reference to its pick are NO ACTION DEFERRABLE INITIALLY
DEFERRED (§2); the tie-breakers are checked by the SQL helper
tiebreakers_valid(). A field's match arrives with the matches.

Revision ID: 2df115cf6eb5
Revises: f85d43721969
Create Date: 2026-11-11 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2df115cf6eb5"
down_revision: str | None = "f85d43721969"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# FR-043: a subset of the three tie-breakers in the organizer's order, none twice;
# all three may be off. CASE, because array_ndims() is NULL for an empty array.
_CREATE_TIEBREAKERS_VALID = """
CREATE FUNCTION tiebreakers_valid(tiebreakers text[]) RETURNS boolean
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    RETURN CASE
        WHEN cardinality(tiebreakers) = 0 THEN true
        WHEN array_ndims(tiebreakers) IS DISTINCT FROM 1 THEN false
        ELSE tiebreakers <@ ARRAY['score_difference', 'bh1', 'bh2']::text[]
            AND array_position(tiebreakers, NULL) IS NULL
            AND cardinality(tiebreakers) = (
                SELECT count(DISTINCT t) FROM unnest(tiebreakers) AS t
            )
    END
"""


def _enum(*values: str, name: str) -> sa.Enum:
    return sa.Enum(
        *values, name=name, native_enum=False, create_constraint=True, length=None
    )


def _deferred_player_fk(table: str) -> sa.ForeignKeyConstraint:
    """The reference to players of DATA-MODEL §2, checked at commit."""
    return sa.ForeignKeyConstraint(
        ["player_id"],
        ["players.id"],
        name=f"fk_{table}_player_id_players",
        deferrable=True,
        initially="DEFERRED",
    )


def upgrade() -> None:
    op.execute(_CREATE_TIEBREAKERS_VALID)
    op.create_table(
        "tournaments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("season_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column(
            "type",
            _enum("singles", "doubles", "dyp", "monster_dyp", name="tournament_type"),
            nullable=False,
        ),
        sa.Column(
            "state",
            _enum("setup", "in_progress", "finished", name="tournament_state"),
            nullable=False,
        ),
        sa.Column(
            "seeding_method",
            _enum("ranking", "random", name="seeding_method"),
            nullable=False,
        ),
        sa.Column(
            "halves_method",
            _enum("ranking", "by_hand", name="halves_method"),
            nullable=False,
        ),
        sa.Column("rng_seed", sa.LargeBinary(), nullable=False),
        sa.Column("draw_counter", sa.Integer(), nullable=False),
        sa.Column("goals_per_game", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "draw_counter >= 0", name=op.f("ck_tournaments_draw_counter")
        ),
        sa.CheckConstraint(
            "goals_per_game >= 1 AND goals_per_game <= 99",
            name=op.f("ck_tournaments_goals_per_game"),
        ),
        sa.CheckConstraint(
            "octet_length(rng_seed) = 16", name=op.f("ck_tournaments_rng_seed")
        ),
        # Halves are used by DYP only (FR-033); every other type keeps 'ranking'.
        sa.CheckConstraint(
            "halves_method = 'ranking' OR type = 'dyp'",
            name=op.f("ck_tournaments_halves_method_type"),
        ),
        sa.ForeignKeyConstraint(
            ["season_id"],
            ["seasons.id"],
            name=op.f("fk_tournaments_season_id_seasons"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tournaments")),
    )
    op.create_index(
        op.f("ix_tournaments_season_id"), "tournaments", ["season_id"], unique=False
    )
    op.create_table(
        "tournament_phases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tournament_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "kind", _enum("group", "knockout", name="phase_kind"), nullable=False
        ),
        sa.Column(
            "format",
            _enum(
                "round_robin",
                "swiss",
                "monster_dyp",
                "single_elimination",
                name="phase_format",
            ),
            nullable=False,
        ),
        sa.Column("round_robin_legs", sa.Integer(), nullable=True),
        sa.Column("sit_out_points", sa.Integer(), nullable=True),
        sa.Column("tiebreakers", sa.ARRAY(sa.String()), nullable=True),
        sa.Column("qualifiers", sa.Integer(), nullable=True),
        sa.Column("third_place_match", sa.Boolean(), nullable=True),
        sa.Column(
            "monster_knockout_mode",
            _enum(
                "seeded_pairs",
                "singles",
                "a_little_mercy",
                "lord_have_mercy",
                name="monster_knockout_mode",
            ),
            nullable=True,
        ),
        sa.Column(
            "match_format",
            _enum("bo1", "bo2", "bo3", "bo5", name="match_format"),
            nullable=False,
        ),
        sa.Column(
            "final_match_format",
            _enum("bo1", "bo3", "bo5", name="final_match_format"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(kind = 'group' AND position = 1)"
            " OR (kind = 'knockout' AND position IN (1, 2))",
            name=op.f("ck_tournament_phases_position"),
        ),
        sa.CheckConstraint(
            "(kind = 'group') = (format IN ('round_robin', 'swiss', 'monster_dyp'))",
            name=op.f("ck_tournament_phases_format_kind"),
        ),
        sa.CheckConstraint(
            "(format = 'round_robin') = (round_robin_legs IS NOT NULL)"
            " AND (round_robin_legs IS NULL OR round_robin_legs IN (1, 2))",
            name=op.f("ck_tournament_phases_round_robin_legs"),
        ),
        sa.CheckConstraint(
            "(kind = 'group') = (sit_out_points IS NOT NULL)"
            " AND (sit_out_points IS NULL OR sit_out_points IN (0, 1))",
            name=op.f("ck_tournament_phases_sit_out_points"),
        ),
        sa.CheckConstraint(
            "(format IN ('swiss', 'monster_dyp')) = (tiebreakers IS NOT NULL)"
            " AND (tiebreakers IS NULL OR tiebreakers_valid(tiebreakers))",
            name=op.f("ck_tournament_phases_tiebreakers"),
        ),
        sa.CheckConstraint(
            "(kind = 'knockout') = (third_place_match IS NOT NULL)",
            name=op.f("ck_tournament_phases_third_place_match"),
        ),
        sa.CheckConstraint(
            "qualifiers IS NULL OR (kind = 'knockout' AND qualifiers >= 2)",
            name=op.f("ck_tournament_phases_qualifiers"),
        ),
        sa.CheckConstraint(
            "monster_knockout_mode IS NULL OR kind = 'knockout'",
            name=op.f("ck_tournament_phases_monster_knockout_mode_kind"),
        ),
        sa.CheckConstraint(
            "final_match_format IS NULL OR kind = 'knockout'",
            name=op.f("ck_tournament_phases_final_match_format_kind"),
        ),
        sa.CheckConstraint(
            "match_format <> 'bo2' OR kind = 'group'",
            name=op.f("ck_tournament_phases_bo2"),
        ),
        sa.ForeignKeyConstraint(
            ["tournament_id"],
            ["tournaments.id"],
            name=op.f("fk_tournament_phases_tournament_id_tournaments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tournament_phases")),
        sa.UniqueConstraint(
            "tournament_id",
            "position",
            name=op.f("uq_tournament_phases_tournament_id_position"),
        ),
    )
    # At most one group phase and one knockout (FR-031, D9); named here, like the
    # other partial index.
    op.create_index(
        "uq_tournament_phases_tournament_id_kind",
        "tournament_phases",
        ["tournament_id", "kind"],
        unique=True,
        postgresql_where=sa.text("kind IN ('group', 'knockout')"),
    )
    op.create_table(
        "fields",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tournament_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "number >= 1 AND number <= 32", name=op.f("ck_fields_number")
        ),
        sa.ForeignKeyConstraint(
            ["tournament_id"],
            ["tournaments.id"],
            name=op.f("fk_fields_tournament_id_tournaments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fields")),
        sa.UniqueConstraint(
            "tournament_id", "number", name=op.f("uq_fields_tournament_id_number")
        ),
    )
    op.create_table(
        "tournament_players",
        sa.Column("tournament_id", sa.Uuid(), nullable=False),
        sa.Column("player_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        _deferred_player_fk("tournament_players"),
        sa.ForeignKeyConstraint(
            ["tournament_id"],
            ["tournaments.id"],
            name=op.f("fk_tournament_players_tournament_id_tournaments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "tournament_id", "player_id", name=op.f("pk_tournament_players")
        ),
    )
    op.create_index(
        op.f("ix_tournament_players_player_id"),
        "tournament_players",
        ["player_id"],
        unique=False,
    )
    op.create_table(
        "entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tournament_id", sa.Uuid(), nullable=False),
        sa.Column(
            "stage", _enum("main", "knockout", name="entry_stage"), nullable=False
        ),
        sa.Column("kind", _enum("player", "pair", name="entry_kind"), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column("source_entry_id", sa.Uuid(), nullable=True),
        sa.Column(
            "is_top_player",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "is_disabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("seed IS NULL OR seed >= 1", name=op.f("ck_entries_seed")),
        # Only a knockout entry continues another entry (BR-082, BR-085).
        sa.CheckConstraint(
            "source_entry_id IS NULL OR stage = 'knockout'",
            name=op.f("ck_entries_source_entry_stage"),
        ),
        sa.ForeignKeyConstraint(
            ["source_entry_id"],
            ["entries.id"],
            name=op.f("fk_entries_source_entry_id_entries"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tournament_id"],
            ["tournaments.id"],
            name=op.f("fk_entries_tournament_id_tournaments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_entries")),
        sa.UniqueConstraint(
            "id",
            "tournament_id",
            "stage",
            name=op.f("uq_entries_id_tournament_id_stage"),
        ),
        # Seeds can be swapped in one transaction (FR-034).
        sa.UniqueConstraint(
            "tournament_id",
            "stage",
            "seed",
            name=op.f("uq_entries_tournament_id_stage_seed"),
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    # The cascade from a deleted source entry finds its knockout entries here.
    op.create_index(
        op.f("ix_entries_source_entry_id"),
        "entries",
        ["source_entry_id"],
        unique=False,
        postgresql_where=sa.text("source_entry_id IS NOT NULL"),
    )
    op.create_table(
        "entry_members",
        sa.Column("entry_id", sa.Uuid(), nullable=False),
        sa.Column("player_id", sa.Uuid(), nullable=False),
        sa.Column("tournament_id", sa.Uuid(), nullable=False),
        sa.Column(
            "stage",
            _enum("main", "knockout", name="entry_member_stage"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["entry_id", "tournament_id", "stage"],
            ["entries.id", "entries.tournament_id", "entries.stage"],
            name="fk_entry_members_entry_id_entries",
            ondelete="CASCADE",
        ),
        _deferred_player_fk("entry_members"),
        # A member is a picked player. Deferred, because setup removes the picks
        # before it makes the entries again (ADR-010).
        sa.ForeignKeyConstraint(
            ["tournament_id", "player_id"],
            ["tournament_players.tournament_id", "tournament_players.player_id"],
            name=op.f("fk_entry_members_tournament_id_tournament_players"),
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.PrimaryKeyConstraint("entry_id", "player_id", name=op.f("pk_entry_members")),
        # BR-003: a player is in at most one entry per stage.
        sa.UniqueConstraint(
            "tournament_id",
            "stage",
            "player_id",
            name=op.f("uq_entry_members_tournament_id_stage_player_id"),
        ),
    )
    op.create_index(
        op.f("ix_entry_members_player_id"), "entry_members", ["player_id"], unique=False
    )
    op.create_table(
        "dyp_halves",
        sa.Column("tournament_id", sa.Uuid(), nullable=False),
        sa.Column("player_id", sa.Uuid(), nullable=False),
        sa.Column(
            "half", _enum("top", "bottom", "left_out", name="dyp_half"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        # No reference to players of its own: the pick has one.
        sa.ForeignKeyConstraint(
            ["tournament_id", "player_id"],
            ["tournament_players.tournament_id", "tournament_players.player_id"],
            name="fk_dyp_halves_tournament_id_tournament_players",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "tournament_id", "player_id", name=op.f("pk_dyp_halves")
        ),
    )


def downgrade() -> None:
    op.drop_table("dyp_halves")
    op.drop_index(op.f("ix_entry_members_player_id"), table_name="entry_members")
    op.drop_table("entry_members")
    op.drop_index(op.f("ix_entries_source_entry_id"), table_name="entries")
    op.drop_table("entries")
    op.drop_index(
        op.f("ix_tournament_players_player_id"), table_name="tournament_players"
    )
    op.drop_table("tournament_players")
    op.drop_table("fields")
    op.drop_index(
        "uq_tournament_phases_tournament_id_kind", table_name="tournament_phases"
    )
    op.drop_table("tournament_phases")
    op.drop_index(op.f("ix_tournaments_season_id"), table_name="tournaments")
    op.drop_table("tournaments")
    op.execute("DROP FUNCTION tiebreakers_valid(text[])")
