from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship
import enum


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class MeetingStatus(str, enum.Enum):
    scheduled = "scheduled"
    in_progress = "in_progress"
    recess = "recess"
    completed = "completed"
    cancelled = "cancelled"


class AgendaItemStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    deferred = "deferred"
    withdrawn = "withdrawn"


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


class Municipality(Base):
    __tablename__ = "municipality"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    timezone = Column(String(100), nullable=False, default="America/Toronto")
    website_url = Column(String(500))
    agenda_base_url = Column(String(500))

    meetings = relationship("Meeting", back_populates="municipality")


class Meeting(Base):
    __tablename__ = "meeting"

    id = Column(Integer, primary_key=True, autoincrement=True)
    municipality_id = Column(Integer, ForeignKey("municipality.id"), nullable=False)
    external_id = Column(String(255), unique=True, nullable=False)
    title = Column(String(500), nullable=False)
    type = Column(String(50))  # council, committee, planning, etc.
    start_datetime = Column(DateTime(timezone=True), nullable=False)
    end_datetime = Column(DateTime(timezone=True))
    location = Column(String(500))
    status = Column(
        Enum(MeetingStatus), nullable=False, default=MeetingStatus.scheduled
    )
    agenda_url = Column(String(1000))
    livestream_url = Column(String(1000))

    municipality = relationship("Municipality", back_populates="meetings")
    agenda_items = relationship(
        "AgendaItem", back_populates="meeting", order_by="AgendaItem.item_number"
    )
    update_events = relationship("UpdateEvent", back_populates="meeting")


class AgendaItem(Base):
    __tablename__ = "agenda_item"

    id = Column(Integer, primary_key=True, autoincrement=True)
    meeting_id = Column(Integer, ForeignKey("meeting.id"), nullable=False)
    item_number = Column(String(20), nullable=False)
    title = Column(String(1000), nullable=False)
    raw_text = Column(Text)
    summary_text = Column(Text)
    section = Column(String(100))
    estimated_start_offset_minutes = Column(Integer)
    actual_start_datetime = Column(DateTime(timezone=True))
    actual_end_datetime = Column(DateTime(timezone=True))
    status = Column(
        Enum(AgendaItemStatus),
        nullable=False,
        default=AgendaItemStatus.pending,
    )

    __table_args__ = (
        UniqueConstraint("meeting_id", "item_number", name="uq_meeting_item"),
    )

    meeting = relationship("Meeting", back_populates="agenda_items")
    tags = relationship("Tag", secondary="agenda_item_tag", back_populates="agenda_items")
    update_events = relationship("UpdateEvent", back_populates="agenda_item")


class Tag(Base):
    __tablename__ = "tag"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)

    agenda_items = relationship(
        "AgendaItem", secondary="agenda_item_tag", back_populates="tags"
    )


class AgendaItemTag(Base):
    __tablename__ = "agenda_item_tag"

    agenda_item_id = Column(
        Integer, ForeignKey("agenda_item.id"), primary_key=True
    )
    tag_id = Column(Integer, ForeignKey("tag.id"), primary_key=True)


class UpdateEvent(Base):
    __tablename__ = "update_event"

    id = Column(Integer, primary_key=True, autoincrement=True)
    meeting_id = Column(Integer, ForeignKey("meeting.id"), nullable=False)
    agenda_item_id = Column(Integer, ForeignKey("agenda_item.id"), nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    event_type = Column(String(50), nullable=False)
    source = Column(String(50), nullable=False, default="system")

    meeting = relationship("Meeting", back_populates="update_events")
    agenda_item = relationship("AgendaItem", back_populates="update_events")
