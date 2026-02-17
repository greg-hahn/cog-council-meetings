"""
CLI entry point for ingestion tasks.

Usage:
    python -m backend.cli ingest "https://pub-guelph.escribemeetings.com/Meeting.aspx?Id=...&Agenda=Agenda&lang=English"
    python -m backend.cli ingest URL --slug guelph
    python -m backend.cli discover
    python -m backend.cli discover --year 2026
"""
import argparse
import logging
import sys

from backend.db.session import SessionLocal
from backend.db.seed import seed_guelph
from backend.ingestion.guelph import ingest_meeting_from_url, discover_and_ingest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)


def cmd_ingest(args):
    db = SessionLocal()
    try:
        seed_guelph(db)
        meeting = ingest_meeting_from_url(args.url, args.slug, db)
        print(f"Ingested: {meeting.title}")
        print(f"  ID: {meeting.id}")
        print(f"  External ID: {meeting.external_id}")
        print(f"  Start: {meeting.start_datetime}")
        print(f"  Items: {len(meeting.agenda_items)}")
        for item in meeting.agenda_items:
            tags = ", ".join(t.name for t in item.tags)
            print(f"    {item.item_number}: {item.title[:60]}  [{tags}]")
    finally:
        db.close()


def cmd_discover(args):
    db = SessionLocal()
    try:
        seed_guelph(db)
        meetings = discover_and_ingest(db, args.slug, args.year)
        if meetings:
            print(f"Discovered and ingested {len(meetings)} new meeting(s):")
            for m in meetings:
                print(f"  {m.title} — {m.start_datetime} ({len(m.agenda_items)} items)")
        else:
            print("No new meetings found.")
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Council Meetings CLI")
    sub = parser.add_subparsers(dest="command")

    ingest_p = sub.add_parser("ingest", help="Ingest a single meeting from URL")
    ingest_p.add_argument("url", help="eScribe Meeting.aspx URL")
    ingest_p.add_argument("--slug", default="guelph", help="Municipality slug")

    discover_p = sub.add_parser("discover", help="Discover and ingest new meetings")
    discover_p.add_argument("--slug", default="guelph", help="Municipality slug")
    discover_p.add_argument("--year", type=int, default=None, help="Year to discover (default: current)")

    args = parser.parse_args()
    if args.command == "ingest":
        cmd_ingest(args)
    elif args.command == "discover":
        cmd_discover(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
