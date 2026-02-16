import os


DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/council_meetings",
)

# For SQLAlchemy async compatibility, strip "postgresql+asyncpg://" etc.
# We use synchronous psycopg2 for simplicity.
SQLALCHEMY_DATABASE_URL = DATABASE_URL

GUELPH_ESCRIBE_BASE = "https://pub-guelph.escribemeetings.com"
GUELPH_AGENDA_HUB = (
    "https://guelph.ca/city-hall/mayor-and-council/city-council/agendas-and-minutes/"
)
GUELPH_LIVESTREAM_URL = "https://guelph.ca/news/live/"
