"""add vote_messages table and extra_vote_channel_ids to guild_settings

Revision ID: 006_vote_messages
Revises: 005_veto_level
Create Date: 2026-09-19
"""
from alembic import op
import sqlalchemy as sa

revision = "006_vote_messages"
down_revision = "005_veto_level"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "guild_settings",
        sa.Column("extra_vote_channel_ids", sa.JSON(), nullable=True),
    )
    op.create_table(
        "vote_messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "vote_id",
            sa.Integer(),
            sa.ForeignKey("votes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("guild_id", sa.BigInteger(), nullable=False),
        sa.Column("channel_id", sa.BigInteger(), nullable=True),
        sa.Column("message_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_vote_messages_vote_id", "vote_messages", ["vote_id"])
    op.create_index("ix_vote_messages_guild_id", "vote_messages", ["guild_id"])

    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT id, guild_id, channel_id, message_id FROM votes "
            "WHERE channel_id IS NOT NULL AND message_id IS NOT NULL"
        )
    )
    rows = result.fetchall()
    for row in rows:
        conn.execute(
            sa.text(
                "INSERT INTO vote_messages (vote_id, guild_id, channel_id, message_id) "
                "VALUES (:vote_id, :guild_id, :channel_id, :message_id)"
            ),
            {
                "vote_id": row[0],
                "guild_id": row[1],
                "channel_id": row[2],
                "message_id": row[3],
            },
        )


def downgrade() -> None:
    op.drop_index("ix_vote_messages_guild_id", table_name="vote_messages")
    op.drop_index("ix_vote_messages_vote_id", table_name="vote_messages")
    op.drop_table("vote_messages")
    op.drop_column("guild_settings", "extra_vote_channel_ids")