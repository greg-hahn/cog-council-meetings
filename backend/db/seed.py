"""Seed the database with initial municipality data."""
from sqlalchemy.orm import Session

from backend.db.models import Municipality


def seed_guelph(db: Session) -> Municipality:
    """Insert or return the City of Guelph municipality row."""
    muni = db.query(Municipality).filter_by(slug="guelph").first()
    if muni:
        return muni

    muni = Municipality(
        name="City of Guelph",
        slug="guelph",
        timezone="America/Toronto",
        website_url="https://guelph.ca",
        agenda_base_url="https://pub-guelph.escribemeetings.com",
    )
    db.add(muni)
    db.commit()
    db.refresh(muni)
    return muni
