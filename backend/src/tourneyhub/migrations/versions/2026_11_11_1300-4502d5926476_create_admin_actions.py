"""create admin_actions and index live refresh-token families

DATA-MODEL §4.1: the record of admin actions from the web and the CLI (ADR-007).
The two CHECKs work in one direction only, so that ON DELETE SET NULL can clear
the reference of a deleted account. The sign-up code is never stored here.
Every authenticated request asks whether its token's family still has an
unrevoked row (ADR-006); a partial index on family_id answers that.

Revision ID: 4502d5926476
Revises: e4fa05f967f8
Create Date: 2026-11-11 01:04:15.553347
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4502d5926476"
down_revision: str | None = "e4fa05f967f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "source",
            sa.Enum(
                "web",
                "cli",
                name="admin_action_source",
                native_enum=False,
                create_constraint=True,
                length=None,
            ),
            nullable=False,
        ),
        sa.Column("admin_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "action",
            sa.Enum(
                "set_signup_code",
                "reset_password",
                "create_admin",
                "grant_admin",
                "revoke_admin",
                name="admin_action_kind",
                native_enum=False,
                create_constraint=True,
                length=None,
            ),
            nullable=False,
        ),
        sa.Column("target_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action <> 'set_signup_code' OR target_user_id IS NULL",
            name=op.f("ck_admin_actions_signup_code_has_no_target"),
        ),
        sa.CheckConstraint(
            "source = 'web' OR admin_user_id IS NULL",
            name=op.f("ck_admin_actions_cli_action_has_no_admin"),
        ),
        sa.ForeignKeyConstraint(
            ["admin_user_id"],
            ["users.id"],
            name=op.f("fk_admin_actions_admin_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["target_user_id"],
            ["users.id"],
            name=op.f("fk_admin_actions_target_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_actions")),
    )
    op.create_index(
        "ix_refresh_tokens_live_family_id",
        "refresh_tokens",
        ["family_id"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_refresh_tokens_live_family_id",
        table_name="refresh_tokens",
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.drop_table("admin_actions")
