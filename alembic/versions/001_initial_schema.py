"""Initial schema — all tables

Revision ID: 001
Revises:
Create Date: 2025-02-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Municipality
    op.create_table(
        "municipality",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("timezone", sa.String(100), nullable=False, server_default="America/Toronto"),
        sa.Column("website_url", sa.String(500)),
        sa.Column("agenda_base_url", sa.String(500)),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )

    # Meeting status enum
    meetingstatus = sa.Enum(
        "scheduled", "in_progress", "recess", "completed", "cancelled",
        name="meetingstatus",
    )

    op.create_table(
        "meeting",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("municipality_id", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("type", sa.String(50)),
        sa.Column("start_datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_datetime", sa.DateTime(timezone=True)),
        sa.Column("location", sa.String(500)),
        sa.Column("status", meetingstatus, nullable=False, server_default="scheduled"),
        sa.Column("agenda_url", sa.String(1000)),
        sa.Column("livestream_url", sa.String(1000)),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["municipality_id"], ["municipality.id"]),
        sa.UniqueConstraint("external_id"),
    )

    # Agenda item status enum
    agendaitemstatus = sa.Enum(
        "pending", "in_progress", "completed", "deferred", "withdrawn",
        name="agendaitemstatus",
    )

    op.create_table(
        "agenda_item",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("meeting_id", sa.Integer(), nullable=False),
        sa.Column("item_number", sa.String(20), nullable=False),
        sa.Column("title", sa.String(1000), nullable=False),
        sa.Column("raw_text", sa.Text()),
        sa.Column("summary_text", sa.Text()),
        sa.Column("section", sa.String(100)),
        sa.Column("estimated_start_offset_minutes", sa.Integer()),
        sa.Column("actual_start_datetime", sa.DateTime(timezone=True)),
        sa.Column("actual_end_datetime", sa.DateTime(timezone=True)),
        sa.Column("status", agendaitemstatus, nullable=False, server_default="pending"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["meeting_id"], ["meeting.id"]),
        sa.UniqueConstraint("meeting_id", "item_number", name="uq_meeting_item"),
    )

    op.create_table(
        "tag",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "agenda_item_tag",
        sa.Column("agenda_item_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("agenda_item_id", "tag_id"),
        sa.ForeignKeyConstraint(["agenda_item_id"], ["agenda_item.id"]),
        sa.ForeignKeyConstraint(["tag_id"], ["tag.id"]),
    )

    op.create_table(
        "update_event",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("meeting_id", sa.Integer(), nullable=False),
        sa.Column("agenda_item_id", sa.Integer()),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("source", sa.String(50), nullable=False, server_default="system"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["meeting_id"], ["meeting.id"]),
        sa.ForeignKeyConstraint(["agenda_item_id"], ["agenda_item.id"]),
    )


def downgrade() -> None:
    op.drop_table("update_event")
    op.drop_table("agenda_item_tag")
    op.drop_table("tag")
    op.drop_table("agenda_item")
    op.drop_table("meeting")
    op.drop_table("municipality")
    sa.Enum(name="meetingstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="agendaitemstatus").drop(op.get_bind(), checkfirst=True)
