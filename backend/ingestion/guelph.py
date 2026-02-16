"""
Ingestion module for City of Guelph council agendas from eScribe.

Scrapes the eScribe Meeting.aspx pages, parses agenda items, and upserts
them into the database.
"""
import logging
import re
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup, Tag as BsTag
from dateutil import parser as dateutil_parser
from pytz import timezone as pytz_timezone
from sqlalchemy.orm import Session

from backend.config import GUELPH_ESCRIBE_BASE, GUELPH_LIVESTREAM_URL
from backend.db.models import (
    AgendaItem,
    AgendaItemStatus,
    Meeting,
    MeetingStatus,
    Municipality,
    Tag,
)
from backend.services.summarization import summarize_and_tag

logger = logging.getLogger(__name__)

# Section mapping based on Guelph's typical agenda structure.
# Top-level item numbers map to logical sections. This can be adjusted
# as patterns change across meetings.
SECTION_MAP: dict[int, str] = {
    1: "opening",
    2: "closed_meeting",
    3: "closed_summary",
    4: "open_meeting",
    5: "confirmation_of_minutes",
    6: "consent",
    7: "items_for_discussion",
    8: "bylaws",
    9: "announcements",
    10: "adjournment",
}

MEETING_TYPE_KEYWORDS: dict[str, str] = {
    "committee of the whole": "committee",
    "city council": "council",
    "planning": "planning",
    "public services": "committee",
    "governance": "committee",
    "audit": "committee",
}

HTTP_TIMEOUT = 30.0
USER_AGENT = "CouncilMeetingsBot/1.0 (civic engagement tool)"


def _extract_guid_from_url(url: str) -> str:
    """Pull the Id query parameter (GUID) from an eScribe URL."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    ids = params.get("Id") or params.get("id")
    if not ids:
        raise ValueError(f"No Id parameter found in URL: {url}")
    return ids[0]


def _infer_meeting_type(title: str) -> str:
    title_lower = title.lower()
    for keyword, mtype in MEETING_TYPE_KEYWORDS.items():
        if keyword in title_lower:
            return mtype
    return "council"


def _infer_section(item_number: str) -> str:
    """Map item_number like '6.1' to a section name."""
    try:
        major = int(item_number.split(".")[0])
    except (ValueError, IndexError):
        return "other"
    return SECTION_MAP.get(major, "other")


def _get_or_create_tag(db: Session, tag_name: str) -> Tag:
    tag = db.query(Tag).filter_by(name=tag_name).first()
    if not tag:
        tag = Tag(name=tag_name)
        db.add(tag)
        db.flush()
    return tag


def _fetch_html(url: str) -> str:
    """Fetch page HTML with sensible defaults."""
    with httpx.Client(
        timeout=HTTP_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
        verify=False,  # eScribe cert issues from some environments
        follow_redirects=True,
    ) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.text


def _parse_meeting_header(soup: BeautifulSoup, tz_name: str) -> dict:
    """Extract meeting title, start/end datetime, and location from the header."""
    tz = pytz_timezone(tz_name)

    # Title: H1 with class AgendaHeaderTitle
    title_el = soup.find("h1", class_="AgendaHeaderTitle")
    raw_title = title_el.get_text(separator=" ", strip=True) if title_el else "Meeting"
    # Clean up — e.g. "City Council Meeting Agenda" → "City Council"
    title = raw_title.replace("Meeting Agenda", "").replace("Agenda", "").strip()

    # Start time: <TIME> inside span.AgendaMeetingTimeStart
    start_dt = None
    start_el = soup.find("span", class_="AgendaMeetingTimeStart")
    if start_el:
        time_tag = start_el.find("time")
        if time_tag and time_tag.get("datetime"):
            raw_dt = time_tag["datetime"]  # e.g. "2025-05-27 16:00"
            start_dt = dateutil_parser.parse(raw_dt)
            start_dt = tz.localize(start_dt)

    # End time: <TIME> inside span.AgendaMeetingTimeEnd
    end_dt = None
    end_el = soup.find("span", class_="AgendaMeetingTimeEnd")
    if end_el:
        time_tag = end_el.find("time")
        if time_tag and time_tag.get("datetime"):
            raw_end = time_tag["datetime"]  # e.g. "22:00"
            try:
                end_time = dateutil_parser.parse(raw_end)
                if start_dt:
                    end_dt = start_dt.replace(
                        hour=end_time.hour, minute=end_time.minute, second=0
                    )
            except Exception:
                pass

    # Location
    location_parts = []
    loc_el = soup.find("div", class_="Location")
    if loc_el:
        location_parts.append(loc_el.get_text(strip=True))
    addr_el = soup.find("div", class_="Address1")
    if addr_el:
        location_parts.append(addr_el.get_text(strip=True))
    location = ", ".join(location_parts) if location_parts else None

    return {
        "title": title,
        "start_datetime": start_dt,
        "end_datetime": end_dt,
        "location": location,
    }


def _parse_agenda_items(soup: BeautifulSoup) -> list[dict]:
    """
    Extract agenda items from the parsed eScribe HTML.

    Each eScribe agenda item lives inside a div.AgendaItemContainer with:
      - div.AgendaItemCounter for the item number (e.g. "6.1")
      - div.AgendaItemTitle > a for the title text
      - div.MotionText.RichText for recommendation/motion text
      - div.AgendaItemDescription.RichText for description text

    We skip closed-meeting items (ClosedAgendaItemCounter) since those
    aren't publicly relevant.
    """
    items: list[dict] = []

    # Find all open (non-closed) item counters
    counters = soup.find_all("div", class_="AgendaItemCounter")

    for counter_el in counters:
        item_number_raw = counter_el.get_text(strip=True).rstrip(".")
        if not item_number_raw:
            continue

        # Navigate up to the parent AgendaItem container
        agenda_item_div = counter_el.find_parent("div", class_=re.compile(r"^AgendaItem\b"))
        if not agenda_item_div:
            continue

        # Title
        title_el = agenda_item_div.find("div", class_="AgendaItemTitle")
        if title_el:
            link = title_el.find("a")
            title = link.get_text(strip=True) if link else title_el.get_text(strip=True)
        else:
            title = ""

        if not title:
            continue

        # Collect raw text from this item's container
        raw_parts = [f"{item_number_raw} {title}"]

        # Find the parent container that holds content rows
        parent_container = counter_el.find_parent("div", class_="AgendaItemContainer")

        if parent_container:
            # Motion/recommendation text
            motions = parent_container.find_all("div", class_="MotionText")
            for mot in motions:
                mot_text = mot.get_text(separator="\n", strip=True)
                if mot_text:
                    raw_parts.append(f"Recommendation: {mot_text}")

            # Description text
            descriptions = parent_container.find_all(
                "div", class_="AgendaItemDescription"
            )
            for desc in descriptions:
                desc_text = desc.get_text(separator="\n", strip=True)
                if desc_text:
                    raw_parts.append(desc_text)

        raw_text = "\n".join(raw_parts)

        items.append(
            {
                "item_number": item_number_raw,
                "title": title,
                "raw_text": raw_text,
                "section": _infer_section(item_number_raw),
            }
        )

    return items


def ingest_meeting_from_url(
    url: str, municipality_slug: str, db: Session
) -> Meeting:
    """
    Fetch and parse an eScribe agenda URL, upserting the meeting and its
    agenda items into the database.

    Args:
        url: Full eScribe Meeting.aspx URL with Id parameter.
        municipality_slug: e.g. "guelph"
        db: SQLAlchemy session

    Returns:
        The upserted Meeting object.
    """
    muni = db.query(Municipality).filter_by(slug=municipality_slug).first()
    if not muni:
        raise ValueError(f"Municipality '{municipality_slug}' not found in database")

    external_id = _extract_guid_from_url(url)

    logger.info("Fetching agenda from %s", url)
    html = _fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")

    header = _parse_meeting_header(soup, muni.timezone)
    meeting_type = _infer_meeting_type(header["title"])

    # Upsert meeting
    meeting = db.query(Meeting).filter_by(external_id=external_id).first()
    if meeting:
        meeting.title = header["title"]
        meeting.type = meeting_type
        meeting.start_datetime = header["start_datetime"]
        meeting.end_datetime = header["end_datetime"]
        meeting.location = header["location"]
        meeting.agenda_url = url
        meeting.livestream_url = GUELPH_LIVESTREAM_URL
    else:
        meeting = Meeting(
            municipality_id=muni.id,
            external_id=external_id,
            title=header["title"],
            type=meeting_type,
            start_datetime=header["start_datetime"],
            end_datetime=header["end_datetime"],
            location=header["location"],
            status=MeetingStatus.scheduled,
            agenda_url=url,
            livestream_url=GUELPH_LIVESTREAM_URL,
        )
        db.add(meeting)

    db.flush()  # Ensure meeting.id is available

    # Parse agenda items
    raw_items = _parse_agenda_items(soup)
    logger.info("Found %d agenda items", len(raw_items))

    offset_minutes = 0
    for idx, item_data in enumerate(raw_items):
        summary, tags = summarize_and_tag(item_data["raw_text"])

        # Estimate start offset: ~5 min for procedural items, ~15 for substantive
        section = item_data["section"]
        if section in ("opening", "closed_meeting", "closed_summary", "adjournment", "announcements"):
            increment = 5
        else:
            increment = 15

        # Upsert agenda item
        agenda_item = (
            db.query(AgendaItem)
            .filter_by(meeting_id=meeting.id, item_number=item_data["item_number"])
            .first()
        )
        if agenda_item:
            agenda_item.title = item_data["title"]
            agenda_item.raw_text = item_data["raw_text"]
            agenda_item.summary_text = summary
            agenda_item.section = section
            agenda_item.estimated_start_offset_minutes = offset_minutes
        else:
            agenda_item = AgendaItem(
                meeting_id=meeting.id,
                item_number=item_data["item_number"],
                title=item_data["title"],
                raw_text=item_data["raw_text"],
                summary_text=summary,
                section=section,
                estimated_start_offset_minutes=offset_minutes,
                status=AgendaItemStatus.pending,
            )
            db.add(agenda_item)

        db.flush()

        # Link tags
        agenda_item.tags.clear()
        for tag_name in tags:
            tag_obj = _get_or_create_tag(db, tag_name)
            agenda_item.tags.append(tag_obj)

        offset_minutes += increment

    db.commit()
    db.refresh(meeting)
    logger.info(
        "Ingested meeting '%s' (id=%s) with %d items",
        meeting.title,
        meeting.id,
        len(raw_items),
    )
    return meeting


def discover_upcoming_meeting_urls() -> list[dict]:
    """
    Discover upcoming Guelph council meeting URLs from the eScribe portal.

    The eScribe calendar page loads meetings via AJAX, so we POST to the
    MeetingsContent.aspx/PastMeetings endpoint. For upcoming meetings
    the panel-body is initially empty — they are rendered client-side.

    As a practical fallback, this function tries the AJAX endpoint and,
    if that fails, returns a hardcoded set or empty list.

    Returns:
        List of dicts with keys: url, title (if available)
    """
    # TODO: The eScribe calendar page loads meetings via client-side JS.
    # A more robust approach would be to use a headless browser or to
    # discover an API endpoint that returns upcoming meetings as JSON.
    # For now, this is a placeholder that logs a warning.
    logger.warning(
        "discover_upcoming_meeting_urls is a stub — eScribe loads meetings "
        "via client-side JS. Pass meeting URLs directly to ingest_meeting_from_url "
        "or implement headless browser scraping."
    )
    return []
