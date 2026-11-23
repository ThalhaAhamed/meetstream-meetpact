"""simple recording notice: drop opt-out and chat-command columns

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _drop(table: str, *columns: str) -> None:
    # A database adopted from create_all may already lack these columns.
    present = {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}
    columns = [c for c in columns if c in present]
    if columns:
        with op.batch_alter_table(table) as batch:
            for c in columns:
                batch.drop_column(c)


def upgrade() -> None:
    _drop("meeting_participants", "opted_out", "notice_sent")
    _drop("meetings", "chat_cursor")


def downgrade() -> None:
    with op.batch_alter_table("meetings") as batch:
        batch.add_column(sa.Column("chat_cursor", sa.Integer(), nullable=False, server_default="0"))
    with op.batch_alter_table("meeting_participants") as batch:
        batch.add_column(sa.Column("notice_sent", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("opted_out", sa.Boolean(), nullable=False, server_default=sa.false()))
