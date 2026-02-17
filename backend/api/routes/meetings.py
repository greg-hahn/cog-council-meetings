"""
API routes for council meeting data.

Endpoints:
  GET  /api/{slug}/meetings/today      - All meetings for today
  GET  /api/{slug}/meetings/now-next   - Current + next agenda item
  GET  /api/{slug}/meetings/recent     - Recent meetings
  GET  /api/{slug}/meetings/search     - Search agenda items
  GET  /api/{slug}/tags                - All tags with counts
  GET  /api/{slug}/items/{item_id}     - Full agenda item detail
  POST /admin/ingest                   - Trigger ingestion for a URL
  POST /admin/discover                 - Discover and ingest new meetings
"""
import logging
from datetime import datetime, time, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pytz import timezone as pytz_timezone
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from backend.db.models import (
    AgendaItem,
    AgendaItemTag,
    Meeting,
    MeetingStatus,
    Municipality,
    Tag,
)
from backend.db.session import get_db
from backend.ingestion.guelph import ingest_meeting_from_url

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_municipality(db: Session, slug: str) -> Municipality:
    muni = db.query(Municipality).filter_by(slug=slug).first()
    if not muni:
        raise HTTPException(status_code=404, detail=f"Municipality '{slug}' not found")
    return muni


def _serialize_item(item: AgendaItem, meeting_start: datetime | None) -> dict:
    estimated_start = None
    if meeting_start and item.estimated_start_offset_minutes is not None:
        estimated_start = (
            meeting_start + timedelta(minutes=item.estimated_start_offset_minutes)
        ).isoformat()

    return {
        "id": item.id,
        "item_number": item.item_number,
        "title": item.title,
        "summary": item.summary_text,
        "section": item.section,
        "tags": [t.name for t in item.tags],
        "status": item.status.value if item.status else "pending",
        "estimated_start_time": estimated_start,
    }


def _serialize_meeting(meeting: Meeting, include_items: bool = True) -> dict:
    result = {
        "id": meeting.id,
        "title": meeting.title,
        "type": meeting.type,
        "start_datetime": meeting.start_datetime.isoformat() if meeting.start_datetime else None,
        "end_datetime": meeting.end_datetime.isoformat() if meeting.end_datetime else None,
        "location": meeting.location,
        "status": meeting.status.value if meeting.status else "scheduled",
        "livestream_url": meeting.livestream_url,
        "agenda_url": meeting.agenda_url,
    }
    if include_items:
        result["items"] = [
            _serialize_item(item, meeting.start_datetime)
            for item in meeting.agenda_items
        ]
    return result


def _estimate_current_next(
    meeting: Meeting, now: datetime
) -> tuple[AgendaItem | None, AgendaItem | None]:
    """
    Approximate the current and next agenda items based on time offsets.

    This is a placeholder that uses estimated_start_offset_minutes.
    When real update_events are wired in, replace this function body
    with logic that reads the latest update_event for the meeting.
    """
    items = sorted(meeting.agenda_items, key=lambda i: i.item_number)
    if not items:
        return None, None

    if not meeting.start_datetime:
        return items[0], items[1] if len(items) > 1 else None

    elapsed = (now - meeting.start_datetime).total_seconds() / 60.0

    current = None
    next_item = None

    for i, item in enumerate(items):
        offset = item.estimated_start_offset_minutes or 0
        if elapsed >= offset:
            current = item
            next_item = items[i + 1] if i + 1 < len(items) else None
        else:
            if current is None:
                # Meeting hasn't started yet or we're before the first item
                next_item = item
            break

    return current, next_item


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/api/{slug}/meetings/today")
def meetings_today(
    slug: str,
    type: Optional[str] = Query(None, description="Filter by meeting type"),
    include_past: bool = Query(True, description="Include meetings that already started today"),
    db: Session = Depends(get_db),
):
    muni = _get_municipality(db, slug)
    tz = pytz_timezone(muni.timezone)
    now = datetime.now(tz)
    day_start = tz.localize(datetime.combine(now.date(), time.min))
    day_end = tz.localize(datetime.combine(now.date(), time.max))

    query = (
        db.query(Meeting)
        .options(joinedload(Meeting.agenda_items).joinedload(AgendaItem.tags))
        .filter(
            Meeting.municipality_id == muni.id,
            Meeting.start_datetime >= day_start,
            Meeting.start_datetime <= day_end,
        )
    )

    if type:
        query = query.filter(Meeting.type == type)

    if not include_past:
        query = query.filter(Meeting.start_datetime >= now)

    # Use unique() because joinedload with collections causes row duplication
    meetings = query.order_by(Meeting.start_datetime).all()
    # Deduplicate due to joinedload
    seen_ids = set()
    unique_meetings = []
    for m in meetings:
        if m.id not in seen_ids:
            seen_ids.add(m.id)
            unique_meetings.append(m)

    return {
        "municipality": slug,
        "date": now.strftime("%Y-%m-%d"),
        "meetings": [_serialize_meeting(m) for m in unique_meetings],
    }


@router.get("/api/{slug}/meetings/now-next")
def meetings_now_next(
    slug: str,
    db: Session = Depends(get_db),
):
    muni = _get_municipality(db, slug)
    tz = pytz_timezone(muni.timezone)
    now = datetime.now(tz)
    day_start = tz.localize(datetime.combine(now.date(), time.min))
    day_end = tz.localize(datetime.combine(now.date(), time.max))

    # Find in-progress meeting first, then fall back to next upcoming today
    meeting = (
        db.query(Meeting)
        .options(joinedload(Meeting.agenda_items).joinedload(AgendaItem.tags))
        .filter(
            Meeting.municipality_id == muni.id,
            Meeting.status == MeetingStatus.in_progress,
            Meeting.start_datetime >= day_start,
            Meeting.start_datetime <= day_end,
        )
        .first()
    )

    if not meeting:
        # Fall back to next upcoming meeting today
        meeting = (
            db.query(Meeting)
            .options(joinedload(Meeting.agenda_items).joinedload(AgendaItem.tags))
            .filter(
                Meeting.municipality_id == muni.id,
                Meeting.start_datetime >= day_start,
                Meeting.start_datetime <= day_end,
            )
            .order_by(Meeting.start_datetime)
            .first()
        )

    if not meeting:
        return {
            "municipality": slug,
            "meeting": None,
            "current_item": None,
            "next_item": None,
            "last_update": now.isoformat(),
        }

    current, next_item = _estimate_current_next(meeting, now)

    return {
        "municipality": slug,
        "meeting": _serialize_meeting(meeting, include_items=False),
        "current_item": _serialize_item(current, meeting.start_datetime) if current else None,
        "next_item": _serialize_item(next_item, meeting.start_datetime) if next_item else None,
        "last_update": now.isoformat(),
    }


@router.get("/api/{slug}/meetings/recent")
def meetings_recent(
    slug: str,
    limit: int = Query(5, ge=1, le=20, description="Max meetings to return"),
    db: Session = Depends(get_db),
):
    """Return the most recent meetings (past and upcoming), regardless of date."""
    muni = _get_municipality(db, slug)

    meetings = (
        db.query(Meeting)
        .options(joinedload(Meeting.agenda_items).joinedload(AgendaItem.tags))
        .filter(Meeting.municipality_id == muni.id)
        .order_by(Meeting.start_datetime.desc())
        .all()
    )

    # Deduplicate due to joinedload
    seen_ids = set()
    unique_meetings = []
    for m in meetings:
        if m.id not in seen_ids:
            seen_ids.add(m.id)
            unique_meetings.append(m)
        if len(unique_meetings) >= limit:
            break

    return {
        "municipality": slug,
        "meetings": [_serialize_meeting(m) for m in unique_meetings],
    }


@router.get("/api/{slug}/items/{item_id}")
def item_detail(
    slug: str,
    item_id: int,
    db: Session = Depends(get_db),
):
    """Return the full detail for a single agenda item."""
    muni = _get_municipality(db, slug)

    item = (
        db.query(AgendaItem)
        .options(joinedload(AgendaItem.tags))
        .join(Meeting)
        .filter(
            AgendaItem.id == item_id,
            Meeting.municipality_id == muni.id,
        )
        .first()
    )

    if not item:
        raise HTTPException(status_code=404, detail="Agenda item not found")

    meeting = item.meeting

    return {
        "id": item.id,
        "item_number": item.item_number,
        "title": item.title,
        "summary": item.summary_text,
        "raw_text": item.raw_text,
        "section": item.section,
        "tags": [t.name for t in item.tags],
        "status": item.status.value if item.status else "pending",
        "meeting_id": meeting.id,
        "meeting_title": meeting.title,
        "meeting_date": meeting.start_datetime.isoformat() if meeting.start_datetime else None,
    }


@router.get("/api/{slug}/meetings/search")
def search_items(
    slug: str,
    q: Optional[str] = Query(None, description="Search keyword"),
    tag: Optional[str] = Query(None, description="Filter by tag name"),
    limit: int = Query(20, ge=1, le=50, description="Max results"),
    db: Session = Depends(get_db),
):
    """Search agenda items by keyword and/or tag across all meetings."""
    muni = _get_municipality(db, slug)

    if not q and not tag:
        return {"municipality": slug, "query": q, "tag": tag, "results": []}

    query = (
        db.query(AgendaItem)
        .join(Meeting)
        .options(joinedload(AgendaItem.tags), joinedload(AgendaItem.meeting))
        .filter(Meeting.municipality_id == muni.id)
    )

    if q:
        pattern = f"%{q}%"
        query = query.filter(
            AgendaItem.title.ilike(pattern) | AgendaItem.summary_text.ilike(pattern)
        )

    if tag:
        query = query.filter(
            AgendaItem.tags.any(Tag.name == tag)
        )

    items = query.order_by(Meeting.start_datetime.desc(), AgendaItem.item_number).limit(limit).all()

    results = []
    for item in items:
        meeting = item.meeting
        results.append({
            "id": item.id,
            "item_number": item.item_number,
            "title": item.title,
            "summary": item.summary_text,
            "tags": [t.name for t in item.tags],
            "section": item.section,
            "meeting_title": meeting.title,
            "meeting_date": meeting.start_datetime.isoformat() if meeting.start_datetime else None,
            "meeting_id": meeting.id,
        })

    return {
        "municipality": slug,
        "query": q,
        "tag": tag,
        "results": results,
    }


@router.get("/api/{slug}/tags")
def list_tags(
    slug: str,
    db: Session = Depends(get_db),
):
    """Return all tags with their agenda item counts for a municipality."""
    muni = _get_municipality(db, slug)

    ait = AgendaItemTag.__table__
    results = (
        db.query(Tag.name, func.count(ait.c.agenda_item_id))
        .join(ait, Tag.id == ait.c.tag_id)
        .join(AgendaItem, AgendaItem.id == ait.c.agenda_item_id)
        .join(Meeting, Meeting.id == AgendaItem.meeting_id)
        .filter(Meeting.municipality_id == muni.id)
        .group_by(Tag.name)
        .order_by(func.count(ait.c.agenda_item_id).desc())
        .all()
    )

    return {
        "municipality": slug,
        "tags": [{"name": name, "count": count} for name, count in results],
    }


# ---------------------------------------------------------------------------
# Admin / ingestion endpoints
# ---------------------------------------------------------------------------


@router.post("/admin/ingest")
def admin_ingest(
    url: str = Query(..., description="eScribe Meeting.aspx URL to ingest"),
    municipality_slug: str = Query("guelph", description="Municipality slug"),
    db: Session = Depends(get_db),
):
    """Ingest a single meeting from its eScribe agenda URL."""
    try:
        meeting = ingest_meeting_from_url(url, municipality_slug, db)
        return {
            "status": "ok",
            "meeting_id": meeting.id,
            "title": meeting.title,
            "items_count": len(meeting.agenda_items),
        }
    except Exception as e:
        logger.exception("Ingestion failed for %s", url)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/discover")
def admin_discover(
    municipality_slug: str = Query("guelph", description="Municipality slug"),
    year: Optional[int] = Query(None, description="Year to discover (default: current)"),
    db: Session = Depends(get_db),
):
    """Discover and ingest new meetings from eScribe."""
    from backend.ingestion.guelph import discover_and_ingest

    try:
        meetings = discover_and_ingest(db, municipality_slug, year)
        return {
            "status": "ok",
            "new_meetings": len(meetings),
            "meetings": [
                {
                    "id": m.id,
                    "title": m.title,
                    "date": m.start_datetime.isoformat() if m.start_datetime else None,
                }
                for m in meetings
            ],
        }
    except Exception as e:
        logger.exception("Discovery failed")
        raise HTTPException(status_code=500, detail=str(e))
