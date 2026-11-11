"""create rounds, matches, sides and games

DATA-MODEL §4.5 and §4.6: the rounds of a phase, who played or sat out each
group round (D5), matches with the result columns of D11 and their games, the
two sides of a match and their players, and the match on a field (D10). A
side's references to its entry and to players are NO ACTION DEFERRABLE
INITIALLY DEFERRED (§2); a field's match is ON DELETE SET NULL, so deleting
rounds frees their fields.

Revision ID: e4fa05f967f8
Revises: 2df115cf6eb5
Create Date: 2026-11-11 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e4fa05f967f8"
down_revision: str | None = "2df115cf6eb5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rounds",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("phase_id", sa.Uuid(), nullable=False),
        sa.Column("round_no", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("round_no >= 1", name=op.f("ck_rounds_round_no")),
        sa.ForeignKeyConstraint(
            ["phase_id"],
            ["tournament_phases.id"],
            name=op.f("fk_rounds_phase_id_tournament_phases"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rounds")),
        sa.UniqueConstraint(
            "phase_id", "round_no", name=op.f("uq_rounds_phase_id_round_no")
        ),
    )
    op.create_table(
        "matches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("round_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "standard",
                "third_place",
                name="match_kind",
                native_enum=False,
                create_constraint=True,
                length=None,
            ),
            nullable=False,
        ),
        sa.Column(
            "outcome",
            sa.Enum(
                "side_1",
                "side_2",
                "draw",
                name="match_outcome",
                native_enum=False,
                create_constraint=True,
                length=None,
            ),
            nullable=True,
        ),
        sa.Column(
            "is_walkover", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("result_entered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requeued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "NOT is_walkover OR (outcome IS NOT NULL AND outcome <> 'draw')",
            name=op.f("ck_matches_walkover"),
        ),
        sa.CheckConstraint(
            "(outcome IS NULL) = (result_entered_at IS NULL)",
            name=op.f("ck_matches_result_entered_at"),
        ),
        sa.CheckConstraint(
            "outcome IS NULL OR requeued_at IS NULL",
            name=op.f("ck_matches_requeued_at"),
        ),
        sa.CheckConstraint("position >= 1", name=op.f("ck_matches_position")),
        sa.ForeignKeyConstraint(
            ["round_id"],
            ["rounds.id"],
            name=op.f("fk_matches_round_id_rounds"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_matches")),
        sa.UniqueConstraint(
            "round_id",
            "kind",
            "position",
            name=op.f("uq_matches_round_id_kind_position"),
        ),
    )
    op.create_table(
        "round_participation",
        sa.Column("round_id", sa.Uuid(), nullable=False),
        sa.Column("entry_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "played",
                "sat_out",
                "disabled",
                "not_joined",
                name="participation",
                native_enum=False,
                create_constraint=True,
                length=None,
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["entry_id"],
            ["entries.id"],
            name=op.f("fk_round_participation_entry_id_entries"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["round_id"],
            ["rounds.id"],
            name=op.f("fk_round_participation_round_id_rounds"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "round_id", "entry_id", name=op.f("pk_round_participation")
        ),
    )
    op.create_index(
        op.f("ix_round_participation_entry_id"),
        "round_participation",
        ["entry_id"],
        unique=False,
    )
    op.create_table(
        "match_games",
        sa.Column("match_id", sa.Uuid(), nullable=False),
        sa.Column("game_no", sa.Integer(), nullable=False),
        sa.Column(
            "winner",
            sa.Enum(
                "side_1",
                "side_2",
                "draw",
                name="game_winner",
                native_enum=False,
                create_constraint=True,
                length=None,
            ),
            nullable=False,
        ),
        sa.Column("score_1", sa.Integer(), nullable=True),
        sa.Column("score_2", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "score_1 IS NULL"
            " OR (winner = 'side_1' AND score_1 > score_2)"
            " OR (winner = 'side_2' AND score_2 > score_1)"
            " OR (winner = 'draw' AND score_1 = score_2)",
            name=op.f("ck_match_games_winner_scores"),
        ),
        sa.CheckConstraint(
            "winner <> 'draw' OR game_no = 1", name=op.f("ck_match_games_draw_game_no")
        ),
        sa.CheckConstraint(
            "(score_1 IS NULL) = (score_2 IS NULL)",
            name=op.f("ck_match_games_both_scores"),
        ),
        sa.CheckConstraint(
            "game_no >= 1 AND game_no <= 5", name=op.f("ck_match_games_game_no")
        ),
        sa.CheckConstraint(
            "score_1 >= 0 AND score_2 >= 0",
            name=op.f("ck_match_games_scores_not_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["match_id"],
            ["matches.id"],
            name=op.f("fk_match_games_match_id_matches"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("match_id", "game_no", name=op.f("pk_match_games")),
    )
    op.create_table(
        "match_sides",
        sa.Column("match_id", sa.Uuid(), nullable=False),
        sa.Column("side", sa.Integer(), nullable=False),
        sa.Column("entry_id", sa.Uuid(), nullable=True),
        sa.Column(
            "is_bye", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "NOT is_bye OR entry_id IS NULL", name=op.f("ck_match_sides_bye_entry")
        ),
        sa.CheckConstraint("side IN (1, 2)", name=op.f("ck_match_sides_side")),
        sa.ForeignKeyConstraint(
            ["entry_id"],
            ["entries.id"],
            name="fk_match_sides_entry_id_entries",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.ForeignKeyConstraint(
            ["match_id"],
            ["matches.id"],
            name=op.f("fk_match_sides_match_id_matches"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("match_id", "side", name=op.f("pk_match_sides")),
    )
    op.create_index(
        op.f("ix_match_sides_entry_id"), "match_sides", ["entry_id"], unique=False
    )
    op.create_table(
        "match_side_players",
        sa.Column("match_id", sa.Uuid(), nullable=False),
        sa.Column("side", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["match_id", "side"],
            ["match_sides.match_id", "match_sides.side"],
            name="fk_match_side_players_match_id_match_sides",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
            name="fk_match_side_players_player_id_players",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.PrimaryKeyConstraint(
            "match_id", "side", "player_id", name=op.f("pk_match_side_players")
        ),
        sa.UniqueConstraint(
            "match_id",
            "player_id",
            name=op.f("uq_match_side_players_match_id_player_id"),
        ),
    )
    op.create_index(
        op.f("ix_match_side_players_player_id"),
        "match_side_players",
        ["player_id"],
        unique=False,
    )
    op.add_column("fields", sa.Column("match_id", sa.Uuid(), nullable=True))
    op.create_unique_constraint(op.f("uq_fields_match_id"), "fields", ["match_id"])
    op.create_foreign_key(
        op.f("fk_fields_match_id_matches"),
        "fields",
        "matches",
        ["match_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_fields_match_id_matches"), "fields", type_="foreignkey")
    op.drop_constraint(op.f("uq_fields_match_id"), "fields", type_="unique")
    op.drop_column("fields", "match_id")
    op.drop_index(
        op.f("ix_match_side_players_player_id"), table_name="match_side_players"
    )
    op.drop_table("match_side_players")
    op.drop_index(op.f("ix_match_sides_entry_id"), table_name="match_sides")
    op.drop_table("match_sides")
    op.drop_table("match_games")
    op.drop_index(
        op.f("ix_round_participation_entry_id"), table_name="round_participation"
    )
    op.drop_table("round_participation")
    op.drop_table("matches")
    op.drop_table("rounds")
