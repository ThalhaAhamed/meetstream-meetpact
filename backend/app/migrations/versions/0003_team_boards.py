"""team boards: native or Trello per team; Trello member mapping; card fields

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

COLUMNS = {
    "teams": [
        sa.Column("board_source", sa.String(20), nullable=False, server_default="native"),
        sa.Column("board_id", sa.String(64), nullable=True),
        sa.Column("board_name", sa.String(255), nullable=True),
        sa.Column("board_url", sa.Text(), nullable=True),
        sa.Column("board_lists", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("board_synced_at", sa.DateTime(timezone=True), nullable=True),
    ],
    "employees": [sa.Column("trello_member_id", sa.String(64), nullable=True)],
    "work_items": [
        sa.Column("external_board_id", sa.String(64), nullable=True),
        sa.Column("external_list_id", sa.String(64), nullable=True),
        sa.Column("external_members", sa.JSON(), nullable=False, server_default="[]"),
    ],
}


def upgrade() -> None:
    bind = op.get_bind()
    for table, cols in COLUMNS.items():
        present = {c["name"] for c in sa.inspect(bind).get_columns(table)}
        with op.batch_alter_table(table) as batch:
            for col in cols:
                if col.name not in present:  # databases adopted from create_all already have them
                    batch.add_column(col)
            if table == "work_items" and "external_board_id" not in present:
                batch.create_index("ix_work_items_external_board_id", ["external_board_id"])


def downgrade() -> None:
    with op.batch_alter_table("work_items") as batch:
        batch.drop_index("ix_work_items_external_board_id")
        for c in ("external_members", "external_list_id", "external_board_id"):
            batch.drop_column(c)
    with op.batch_alter_table("employees") as batch:
        batch.drop_column("trello_member_id")
    with op.batch_alter_table("teams") as batch:
        for c in ("board_synced_at", "board_lists", "board_name", "board_url", "board_id", "board_source"):
            batch.drop_column(c)
